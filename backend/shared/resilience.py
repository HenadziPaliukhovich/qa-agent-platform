"""
backend/shared/resilience.py

Lightweight retry + circuit breaker for outbound HTTP calls.
No external dependencies — stdlib only.

Usage:
    from backend.shared.resilience import retry_with_backoff, CircuitBreaker

    breaker = CircuitBreaker(name="ollama", failure_threshold=3, recovery_timeout=30)

    def call():
        return requests.post(...)

    result = retry_with_backoff(call, retries=3, breaker=breaker)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CircuitOpenError(Exception):
    """Raised when a CircuitBreaker rejects a call because the circuit is OPEN."""


class MaxRetriesExceeded(Exception):
    """Raised when all retry attempts are exhausted."""
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"Failed after {attempts} attempt(s): {last_error}")
        self.last_error = last_error
        self.attempts = attempts


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Three-state circuit breaker: CLOSED → OPEN → HALF-OPEN → CLOSED.

    CLOSED   — calls pass through normally.
    OPEN     — calls are rejected immediately (CircuitOpenError).
                After `recovery_timeout` seconds the breaker moves to HALF-OPEN.
    HALF-OPEN — one probe call is allowed:
                  success → CLOSED (counters reset)
                  failure → back to OPEN

    Thread-safe via a simple Lock.
    """

    _CLOSED    = "CLOSED"
    _OPEN      = "OPEN"
    _HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout

        self._state        = self._CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._lock         = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._current_state()

    def call(self, fn: Callable[[], T]) -> T:
        """Execute *fn* protected by the circuit breaker."""
        with self._lock:
            state = self._current_state()

            if state == self._OPEN:
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN — "
                    f"retry after {self.recovery_timeout}s"
                )

            if state == self._HALF_OPEN:
                log.info("[%s] Circuit HALF-OPEN: probing", self.name)

        # Execute outside the lock so we don't hold it during the HTTP call
        try:
            result = fn()
        except Exception as exc:
            self._on_failure(exc)
            raise

        self._on_success()
        return result

    def record_success(self) -> None:
        self._on_success()

    def record_failure(self, exc: Exception | None = None) -> None:
        self._on_failure(exc)

    def reset(self) -> None:
        """Manually reset to CLOSED (useful in tests)."""
        with self._lock:
            self._state         = self._CLOSED
            self._failure_count = 0
            self._opened_at     = None
        log.info("[%s] Circuit manually RESET to CLOSED", self.name)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _current_state(self) -> str:
        """Must be called while holding self._lock."""
        if self._state == self._OPEN:
            elapsed = time.monotonic() - (self._opened_at or 0.0)
            if elapsed >= self.recovery_timeout:
                log.info(
                    "[%s] Circuit moving OPEN → HALF-OPEN (%.1fs elapsed)",
                    self.name, elapsed,
                )
                self._state = self._HALF_OPEN
        return self._state

    def _on_success(self) -> None:
        with self._lock:
            prev = self._state
            self._state         = self._CLOSED
            self._failure_count = 0
            self._opened_at     = None
        if prev != self._CLOSED:
            log.info("[%s] Circuit → CLOSED (success)", self.name)

    def _on_failure(self, exc: Exception | None) -> None:
        with self._lock:
            self._failure_count += 1
            log.warning(
                "[%s] Failure #%d/%d: %s",
                self.name, self._failure_count, self.failure_threshold, exc,
            )
            if self._failure_count >= self.failure_threshold:
                self._state      = self._OPEN
                self._opened_at  = time.monotonic()
                log.error(
                    "[%s] Circuit → OPEN after %d failures",
                    self.name, self._failure_count,
                )

    def __repr__(self) -> str:
        return f"CircuitBreaker(name={self.name!r}, state={self.state})"


# ---------------------------------------------------------------------------
# Retry with exponential back-off
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    breaker: CircuitBreaker | None = None,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Call *fn* up to *retries* times with exponential back-off.

    Back-off formula:  delay = min(base_delay * backoff_factor ** attempt, max_delay)

    Parameters
    ----------
    fn                   Callable to invoke (no arguments).
    retries              Maximum total attempts (1 = no retry).
    base_delay           Initial wait in seconds between attempts.
    max_delay            Upper cap on wait time.
    backoff_factor       Multiplier applied each attempt.
    breaker              Optional CircuitBreaker to wrap the call.
    retryable_exceptions Only retry if the raised exception is one of these types.
                         Defaults to (Exception,) — retry on anything.

    Returns the value returned by *fn* on success.
    Raises MaxRetriesExceeded if all attempts fail.
    Raises CircuitOpenError immediately if the breaker is OPEN.
    """
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            if breaker is not None:
                return breaker.call(fn)
            return fn()

        except CircuitOpenError:
            # Don't retry — circuit is open, fail fast
            raise

        except retryable_exceptions as exc:  # type: ignore[misc]
            last_exc = exc

            # Check if HTTP status is retryable (requests.HTTPError exposes .response)
            response = getattr(exc, "response", None)
            if response is not None:
                status = getattr(response, "status_code", None)
                if status is not None and status not in _RETRYABLE_STATUS_CODES:
                    log.warning(
                        "[retry] Non-retryable HTTP %s on attempt %d — giving up",
                        status, attempt,
                    )
                    raise MaxRetriesExceeded(attempt, exc) from exc

            if attempt < retries:
                delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                log.warning(
                    "[retry] Attempt %d/%d failed (%s). Retrying in %.1fs…",
                    attempt, retries, exc, delay,
                )
                time.sleep(delay)
            else:
                log.error(
                    "[retry] All %d attempts failed. Last error: %s",
                    retries, exc,
                )

    raise MaxRetriesExceeded(retries, last_exc)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Module-level singleton breakers (one per upstream service)
# ---------------------------------------------------------------------------

#: Circuit breaker for Ollama.  Tripped after 3 consecutive failures;
#: recovers after 30 s.  Import and use directly:
#:   from backend.shared.resilience import OLLAMA_BREAKER
OLLAMA_BREAKER = CircuitBreaker(
    name="ollama",
    failure_threshold=3,
    recovery_timeout=30.0,
)

#: Circuit breaker for OpenAI API.
OPENAI_BREAKER = CircuitBreaker(
    name="openai",
    failure_threshold=5,
    recovery_timeout=60.0,
)
