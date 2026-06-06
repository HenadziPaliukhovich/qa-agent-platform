from typing import Any, Optional
from uuid import uuid4
import json
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg

app = FastAPI(title="qa-rag-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qa:qa@127.0.0.1:5432/qa_agent")


def get_conn():
    return psycopg.connect(DATABASE_URL)


class KnowledgeDocumentCreate(BaseModel):
    project_id: str = "default-project"
    service_name: Optional[str] = None
    title: str
    doc_type: str = "general"
    source: Optional[str] = "qa-console"
    tags: list[str] = Field(default_factory=list)
    content: str


class KnowledgeSearchRequest(BaseModel):
    project_id: str = "default-project"
    query: str
    service_name: Optional[str] = None
    doc_types: list[str] = Field(default_factory=list)
    limit: int = 5


def normalize_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1400, overlap: int = 200) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'qa-rag-service'}


@app.post('/api/knowledge/documents')
def create_document(payload: KnowledgeDocumentCreate):
    document_id = f"doc-{uuid4().hex[:12]}"
    chunks = chunk_text(payload.content)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into knowledge_documents (
                  document_id, project_id, service_name, title, doc_type, source, tags, raw_content
                ) values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    document_id,
                    payload.project_id,
                    payload.service_name,
                    payload.title,
                    payload.doc_type,
                    payload.source,
                    json.dumps(payload.tags),
                    payload.content,
                ),
            )

            for idx, chunk in enumerate(chunks):
                cur.execute(
                    """
                    insert into knowledge_chunks (
                      chunk_id, document_id, chunk_index, content, token_estimate, metadata
                    ) values (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        f"chunk-{uuid4().hex[:12]}",
                        document_id,
                        idx,
                        chunk,
                        estimate_tokens(chunk),
                        json.dumps({
                            'service_name': payload.service_name,
                            'doc_type': payload.doc_type,
                            'title': payload.title,
                        }),
                    ),
                )
        conn.commit()

    return {
        'status': 'stored',
        'document_id': document_id,
        'chunk_count': len(chunks),
    }


@app.get('/api/knowledge/documents')
def list_documents(project_id: str = 'default-project'):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select document_id, project_id, service_name, title, doc_type, source, tags, created_at
                from knowledge_documents
                where project_id = %s
                order by created_at desc
                limit 200
                """,
                (project_id,),
            )
            rows = cur.fetchall()

    return {
        'documents': [
            {
                'document_id': row[0],
                'project_id': row[1],
                'service_name': row[2],
                'title': row[3],
                'doc_type': row[4],
                'source': row[5],
                'tags': row[6] or [],
                'created_at': row[7].isoformat() if row[7] else None,
            }
            for row in rows
        ]
    }


@app.get('/api/knowledge/documents/{document_id}')
def get_document(document_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select document_id, project_id, service_name, title, doc_type, source, tags, raw_content, created_at
                from knowledge_documents
                where document_id = %s
                """,
                (document_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={'error': 'document_not_found', 'document_id': document_id})

    return {
        'document': {
            'document_id': row[0],
            'project_id': row[1],
            'service_name': row[2],
            'title': row[3],
            'doc_type': row[4],
            'source': row[5],
            'tags': row[6] or [],
            'content': row[7],
            'created_at': row[8].isoformat() if row[8] else None,
        }
    }


@app.delete('/api/knowledge/documents/{document_id}')
def delete_document(document_id: str, project_id: str = 'default-project'):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select document_id, project_id, title
                from knowledge_documents
                where document_id = %s and project_id = %s
                """,
                (document_id, project_id),
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(
                    status_code=404,
                    detail={
                        'error': 'document_not_found',
                        'document_id': document_id,
                        'project_id': project_id,
                    },
                )

            cur.execute(
                """
                delete from knowledge_chunks
                where document_id = %s
                """,
                (document_id,),
            )
            deleted_chunks = cur.rowcount or 0

            cur.execute(
                """
                delete from knowledge_documents
                where document_id = %s and project_id = %s
                """,
                (document_id, project_id),
            )
            deleted_documents = cur.rowcount or 0

        conn.commit()

    return {
        'status': 'deleted',
        'document_id': document_id,
        'project_id': project_id,
        'title': row[2],
        'deleted_documents': deleted_documents,
        'deleted_chunks': deleted_chunks,
    }


@app.post('/api/knowledge/search')
def search_documents(payload: KnowledgeSearchRequest):
    limit = max(1, min(payload.limit, 20))
    query = normalize_text(payload.query)
    if not query:
        raise HTTPException(status_code=400, detail={'error': 'empty_query'})

    filters = ["d.project_id = %s"]
    params: list[Any] = [payload.project_id]

    if payload.service_name:
        filters.append("coalesce(d.service_name, '') = %s")
        params.append(payload.service_name)

    if payload.doc_types:
        filters.append("d.doc_type = any(%s)")
        params.append(payload.doc_types)

    where_sql = " and ".join(filters)

    tokens = [t.strip(".,:;!?()[]{}\"'").strip() for t in query.split() if t.strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail={'error': 'empty_query_tokens'})

    like_clauses = []
    for token in tokens:
        like_clauses.append("c.content ilike %s")
        params.append(f"%{token}%")

    like_sql = " or ".join(like_clauses)
    params.append(limit)

    sql = f"""
        select
          c.chunk_id,
          c.document_id,
          d.title,
          d.doc_type,
          d.service_name,
          c.chunk_index,
          c.content,
          0.0 as rank
        from knowledge_chunks c
        join knowledge_documents d on d.document_id = c.document_id
        where {where_sql}
          and ({like_sql})
        order by d.created_at desc, c.chunk_index asc
        limit %s
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return {
        'query': query,
        'results': [
            {
                'chunk_id': row[0],
                'document_id': row[1],
                'title': row[2],
                'doc_type': row[3],
                'service_name': row[4],
                'chunk_index': row[5],
                'content': row[6],
                'score': float(row[7] or 0.0),
            }
            for row in rows
        ]
    }