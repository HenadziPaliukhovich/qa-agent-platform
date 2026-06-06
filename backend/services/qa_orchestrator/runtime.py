import json
import logging
import threading
from uuid import uuid4

import psycopg
from kafka import KafkaConsumer, KafkaProducer

logger = logging.getLogger("qa-orchestrator")


class OrchestratorRuntime:
    def __init__(
        self,
        *,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        task_created_topic: str,
        task_status_topic: str,
        database_url: str,
        process_task_event,
    ):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.task_created_topic = task_created_topic
        self.task_status_topic = task_status_topic
        self.database_url = database_url
        self.process_task_event = process_task_event

        self.consumer_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.producer: KafkaProducer | None = None

    def get_conn(self):
        return psycopg.connect(self.database_url)

    def create_producer(self) -> KafkaProducer | None:
        try:
            return KafkaProducer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda v: v.encode("utf-8") if v else None,
                api_version_auto_timeout_ms=5000,
            )
        except Exception as exc:
            logger.exception("Failed to create Kafka producer: %s", exc)
            return None

    def publish_status(self, task_id: str, state: str, event_type: str, extra: dict | None = None):
        payload = {"task_id": task_id, "state": state}
        if extra:
            payload.update(extra)

        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update tasks set state = %s, updated_at = now() where task_id = %s",
                    (state, task_id),
                )
                cur.execute(
                    """
                    insert into task_events (event_id, task_id, event_type, payload)
                    values (%s, %s, %s, %s::jsonb)
                    """,
                    (f"evt-{uuid4().hex[:12]}", task_id, event_type, json.dumps(payload)),
                )
            conn.commit()

        if self.producer is not None:
            try:
                self.producer.send(event_type, key=task_id, value=payload)
                self.producer.flush()
            except Exception as exc:
                logger.exception("Failed to publish Kafka status event for %s: %s", task_id, exc)

    def consume_loop(self):
        logger.info("Starting Kafka consumer loop")

        consumer = KafkaConsumer(
            self.task_created_topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            group_id=self.consumer_group,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            key_deserializer=lambda m: m.decode("utf-8") if m else None,
            consumer_timeout_ms=1000,
            api_version_auto_timeout_ms=5000,
        )

        try:
            while not self.stop_event.is_set():
                for message in consumer:
                    if self.stop_event.is_set():
                        break
                    event = message.value
                    logger.info("Received task event: %s", event)
                    self.process_task_event(event)
        finally:
            consumer.close()
            logger.info("Kafka consumer loop stopped")

    def startup(self):
        self.producer = self.create_producer()
        self.stop_event.clear()

        if self.consumer_thread is None or not self.consumer_thread.is_alive():
            self.consumer_thread = threading.Thread(target=self.consume_loop, daemon=True)
            self.consumer_thread.start()

    def shutdown(self):
        self.stop_event.set()

        if self.consumer_thread and self.consumer_thread.is_alive():
            self.consumer_thread.join(timeout=5)

        if self.producer is not None:
            try:
                self.producer.flush(timeout=5)
                self.producer.close()
            except Exception:
                logger.exception("Failed to close Kafka producer cleanly")
            finally:
                self.producer = None
