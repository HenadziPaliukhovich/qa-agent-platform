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


class DomainContextFileCreate(BaseModel):
    title: str
    file_name: Optional[str] = None
    content_type: str = "text/plain"
    source: Optional[str] = "qa-console"
    tags: list[str] = Field(default_factory=list)
    raw_content: str


class DomainContextFileUpdate(BaseModel):
    title: str
    file_name: Optional[str] = None
    content_type: str = "text/plain"
    source: Optional[str] = "qa-console"
    tags: list[str] = Field(default_factory=list)
    raw_content: str


class DomainContextSearchRequest(BaseModel):
    domain_id: str
    query: str
    selected_context_ids: list[str] = Field(default_factory=list)
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


def normalize_tags(tags: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def serialize_domain_context_file_row(row) -> dict:
    return {
        'context_file_id': row[0],
        'domain_id': row[1],
        'title': row[2],
        'file_name': row[3],
        'content_type': row[4],
        'source': row[5],
        'tags': row[6] or [],
        'version': row[7],
        'status': row[8],
        'created_at': row[9].isoformat() if row[9] else None,
        'updated_at': row[10].isoformat() if row[10] else None,
    }


def get_domain_or_404(cur, domain_id: str):
    cur.execute(
        "select domain_id, status from domains where domain_id = %s",
        (domain_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail={'error': {'code': 'domain_not_found', 'message': 'Domain was not found', 'details': {'domain_id': domain_id}}})
    return row


def get_domain_context_file_or_404(cur, domain_id: str, context_file_id: str):
    cur.execute(
        """
        select context_file_id, domain_id, title, file_name, content_type, source, tags, version, status, created_at, updated_at, raw_content
        from domain_context_files
        where domain_id = %s and context_file_id = %s
        """,
        (domain_id, context_file_id),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail={'error': {'code': 'context_file_not_found', 'message': 'Context file was not found', 'details': {'domain_id': domain_id, 'context_file_id': context_file_id}}})
    return row


def replace_domain_context_chunks(cur, domain_id: str, context_file_id: str, title: str, content_type: str, raw_content: str) -> int:
    cur.execute('delete from domain_context_chunks where context_file_id = %s', (context_file_id,))
    chunks = chunk_text(raw_content)
    for idx, chunk in enumerate(chunks):
        cur.execute(
            """
            insert into domain_context_chunks (
              chunk_id, context_file_id, domain_id, chunk_index, content, token_estimate, metadata
            ) values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                f"chunk-{uuid4().hex[:12]}",
                context_file_id,
                domain_id,
                idx,
                chunk,
                estimate_tokens(chunk),
                json.dumps({
                    'title': title,
                    'content_type': content_type,
                }),
            ),
        )
    return len(chunks)




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

@app.post('/api/domains/{domain_id}/context-files')
def create_domain_context_file(domain_id: str, payload: DomainContextFileCreate):
    context_file_id = f"ctx-{uuid4().hex[:12]}"
    tags = normalize_tags(payload.tags)

    with get_conn() as conn:
        with conn.cursor() as cur:
            get_domain_or_404(cur, domain_id)
            cur.execute(
                """
                insert into domain_context_files (
                  context_file_id, domain_id, title, file_name, content_type, source, tags, raw_content, version, status
                ) values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, 1, 'active')
                returning context_file_id, domain_id, title, file_name, content_type, source, tags, version, status, created_at, updated_at
                """,
                (
                    context_file_id,
                    domain_id,
                    payload.title,
                    payload.file_name,
                    payload.content_type,
                    payload.source,
                    json.dumps(tags),
                    payload.raw_content,
                ),
            )
            row = cur.fetchone()
            chunk_count = replace_domain_context_chunks(cur, domain_id, context_file_id, payload.title, payload.content_type, payload.raw_content)
        conn.commit()

    response = serialize_domain_context_file_row(row)
    response['chunk_count'] = chunk_count
    return response


@app.get('/api/domains/{domain_id}/context-files')
def list_domain_context_files(domain_id: str, status: Optional[str] = None, q: Optional[str] = None):
    search = f"%{q.strip()}%" if q and q.strip() else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            get_domain_or_404(cur, domain_id)
            cur.execute(
                """
                select
                  f.context_file_id,
                  f.domain_id,
                  f.title,
                  f.file_name,
                  f.content_type,
                  f.source,
                  f.tags,
                  f.version,
                  f.status,
                  f.created_at,
                  f.updated_at,
                  coalesce(count(c.chunk_id), 0) as chunk_count
                from domain_context_files f
                left join domain_context_chunks c on c.context_file_id = f.context_file_id
                where f.domain_id = %s
                  and (%s is null or f.status = %s)
                  and (
                    %s is null
                    or f.title ilike %s
                    or coalesce(f.file_name, '') ilike %s
                    or coalesce(f.raw_content, '') ilike %s
                  )
                group by f.context_file_id, f.domain_id, f.title, f.file_name, f.content_type, f.source, f.tags, f.version, f.status, f.created_at, f.updated_at
                order by f.created_at desc
                """,
                (domain_id, status, status, search, search, search, search),
            )
            rows = cur.fetchall()

    items = []
    for row in rows:
        item = serialize_domain_context_file_row(row[:11])
        item['chunk_count'] = row[11]
        items.append(item)
    return {'context_files': items}


@app.get('/api/domains/{domain_id}/context-files/{context_file_id}')
def get_domain_context_file(domain_id: str, context_file_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            get_domain_or_404(cur, domain_id)
            row = get_domain_context_file_or_404(cur, domain_id, context_file_id)
            cur.execute('select count(*) from domain_context_chunks where context_file_id = %s', (context_file_id,))
            chunk_count = cur.fetchone()[0]

    response = serialize_domain_context_file_row(row[:11])
    response['raw_content'] = row[11]
    response['chunk_count'] = chunk_count
    return response


@app.put('/api/domains/{domain_id}/context-files/{context_file_id}')
def update_domain_context_file(domain_id: str, context_file_id: str, payload: DomainContextFileUpdate):
    tags = normalize_tags(payload.tags)

    with get_conn() as conn:
        with conn.cursor() as cur:
            get_domain_or_404(cur, domain_id)
            get_domain_context_file_or_404(cur, domain_id, context_file_id)
            cur.execute(
                """
                update domain_context_files
                set title = %s,
                    file_name = %s,
                    content_type = %s,
                    source = %s,
                    tags = %s::jsonb,
                    raw_content = %s,
                    version = version + 1,
                    updated_at = now()
                where domain_id = %s and context_file_id = %s
                returning context_file_id, domain_id, title, file_name, content_type, source, tags, version, status, created_at, updated_at
                """,
                (
                    payload.title,
                    payload.file_name,
                    payload.content_type,
                    payload.source,
                    json.dumps(tags),
                    payload.raw_content,
                    domain_id,
                    context_file_id,
                ),
            )
            row = cur.fetchone()
            chunk_count = replace_domain_context_chunks(cur, domain_id, context_file_id, payload.title, payload.content_type, payload.raw_content)
        conn.commit()

    response = serialize_domain_context_file_row(row)
    response['chunk_count'] = chunk_count
    return response


@app.delete('/api/domains/{domain_id}/context-files/{context_file_id}')
def delete_domain_context_file(domain_id: str, context_file_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            get_domain_or_404(cur, domain_id)
            get_domain_context_file_or_404(cur, domain_id, context_file_id)
            cur.execute(
                """
                update domain_context_files
                set status = 'deleted', updated_at = now()
                where domain_id = %s and context_file_id = %s
                returning context_file_id, domain_id, status, updated_at
                """,
                (domain_id, context_file_id),
            )
            row = cur.fetchone()
        conn.commit()

    return {
        'context_file_id': row[0],
        'domain_id': row[1],
        'status': row[2],
        'updated_at': row[3].isoformat() if row[3] else None,
    }

@app.post('/api/domains/context-search')
def search_domain_context(payload: DomainContextSearchRequest):
    search_limit = min(max(payload.limit, 1), 20)
    query_text = normalize_text(payload.query)
    if not query_text:
        raise HTTPException(status_code=400, detail={'error': {'code': 'invalid_query', 'message': 'Query must not be empty'}})

    with get_conn() as conn:
        with conn.cursor() as cur:
            get_domain_or_404(cur, payload.domain_id)
            cur.execute(
                """
                select
                  c.chunk_id,
                  c.context_file_id,
                  c.chunk_index,
                  c.content,
                  c.token_estimate,
                  f.title,
                  f.file_name,
                  f.tags,
                  ts_rank(c.search_vector, plainto_tsquery('english', %s)) as rank
                from domain_context_chunks c
                join domain_context_files f on f.context_file_id = c.context_file_id
                where c.domain_id = %s
                  and f.status = 'active'
                  and (
                    %s::jsonb = '[]'::jsonb
                    or c.context_file_id in (
                      select jsonb_array_elements_text(%s::jsonb)
                    )
                  )
                  and c.search_vector @@ plainto_tsquery('english', %s)
                order by rank desc, c.created_at desc
                limit %s
                """,
                (query_text, payload.domain_id, json.dumps(payload.selected_context_ids), json.dumps(payload.selected_context_ids), query_text, search_limit),
            )
            rows = cur.fetchall()

    items = []
    for row in rows:
        items.append({
            'chunk_id': row[0],
            'context_file_id': row[1],
            'chunk_index': row[2],
            'content': row[3],
            'token_estimate': row[4],
            'title': row[5],
            'file_name': row[6],
            'tags': row[7] or [],
            'rank': float(row[8]) if row[8] is not None else 0.0,
        })

    return {'items': items}

