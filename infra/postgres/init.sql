create table if not exists tasks (
  task_id varchar(64) primary key,
  project_id varchar(64) not null,
  task_type varchar(64) not null,
  state varchar(64) not null,
  input_json jsonb not null,
  result_ref varchar(255),
  approval_required boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists task_events (
  event_id varchar(64) primary key,
  task_id varchar(64) not null,
  event_type varchar(128) not null,
  payload jsonb not null,
  created_at timestamptz default now()
);

create index if not exists idx_task_events_task_created_at on task_events (task_id, created_at);

create table if not exists approvals (
  approval_id varchar(64) primary key,
  task_id varchar(64) not null,
  actor varchar(255) not null,
  decision varchar(32) not null,
  comment text,
  created_at timestamptz default now()
);

create table if not exists results (
  result_id varchar(64) primary key,
  task_id varchar(64) not null,
  schema_name varchar(128) not null,
  content_json jsonb not null,
  created_at timestamptz default now()
);

create index if not exists idx_results_task_id on results (task_id);


create table if not exists knowledge_documents (
  document_id varchar(64) primary key,
  project_id varchar(64) not null default 'default-project',
  service_name varchar(255),
  title varchar(500) not null,
  doc_type varchar(64) not null,
  source varchar(255),
  tags jsonb not null default '[]'::jsonb,
  raw_content text not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists knowledge_chunks (
  chunk_id varchar(64) primary key,
  document_id varchar(64) not null,
  chunk_index integer not null,
  content text not null,
  token_estimate integer default 0,
  metadata jsonb not null default '{}'::jsonb,
  search_vector tsvector generated always as (to_tsvector('english', coalesce(content, ''))) stored,
  created_at timestamptz default now()
);

create index if not exists idx_knowledge_documents_project on knowledge_documents (project_id);
create index if not exists idx_knowledge_documents_service on knowledge_documents (service_name);
create index if not exists idx_knowledge_documents_type on knowledge_documents (doc_type);
create index if not exists idx_knowledge_chunks_document on knowledge_chunks (document_id, chunk_index);
create index if not exists idx_knowledge_chunks_search_vector on knowledge_chunks using gin (search_vector);
