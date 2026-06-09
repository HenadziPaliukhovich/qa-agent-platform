-- Thin-slice schema draft for domain-first model
-- This file is a design draft and should be converted into the project's migration flow.
-- It is intentionally additive-first to preserve compatibility with the current schema.

-- =========================================================
-- 1. Domains
-- =========================================================

create table if not exists domains (
  domain_id varchar(64) primary key,
  name varchar(255) not null,
  slug varchar(255) not null unique,
  description text,
  status varchar(32) not null default 'active',
  tags jsonb not null default '[]'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint chk_domains_status check (status in ('active', 'archived'))
);

create index if not exists idx_domains_status on domains (status);
create index if not exists idx_domains_created_at on domains (created_at desc);

-- =========================================================
-- 2. Domain profiles
-- =========================================================

create table if not exists domain_profiles (
  domain_id varchar(64) primary key,
  business_scope text,
  prompt_policy jsonb not null default '{}'::jsonb,
  retrieval_policy jsonb not null default '{}'::jsonb,
  supported_artifacts jsonb not null default '[]'::jsonb,
  event_source_settings jsonb not null default '{}'::jsonb,
  integration_bindings jsonb not null default '[]'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint fk_domain_profiles_domain
    foreign key (domain_id) references domains(domain_id)
    on delete cascade
);

-- =========================================================
-- 3. Domain context files
-- =========================================================

create table if not exists domain_context_files (
  context_file_id varchar(64) primary key,
  domain_id varchar(64) not null,
  title varchar(500) not null,
  file_name varchar(500),
  content_type varchar(255) not null default 'text/plain',
  source varchar(255) default 'qa-console',
  tags jsonb not null default '[]'::jsonb,
  raw_content text not null,
  version integer not null default 1,
  status varchar(32) not null default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint fk_domain_context_files_domain
    foreign key (domain_id) references domains(domain_id)
    on delete restrict,
  constraint chk_domain_context_files_status check (status in ('active', 'deleted')),
  constraint chk_domain_context_files_version check (version >= 1)
);

create index if not exists idx_domain_context_files_domain on domain_context_files (domain_id);
create index if not exists idx_domain_context_files_domain_status on domain_context_files (domain_id, status);
create index if not exists idx_domain_context_files_created_at on domain_context_files (created_at desc);

-- =========================================================
-- 4. Domain context chunks
-- =========================================================

create table if not exists domain_context_chunks (
  chunk_id varchar(64) primary key,
  context_file_id varchar(64) not null,
  domain_id varchar(64) not null,
  chunk_index integer not null,
  content text not null,
  token_estimate integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  search_vector tsvector generated always as (to_tsvector('english', coalesce(content, ''))) stored,
  created_at timestamptz default now(),
  constraint fk_domain_context_chunks_context_file
    foreign key (context_file_id) references domain_context_files(context_file_id)
    on delete cascade,
  constraint fk_domain_context_chunks_domain
    foreign key (domain_id) references domains(domain_id)
    on delete restrict,
  constraint uq_domain_context_chunks_file_chunk unique (context_file_id, chunk_index),
  constraint chk_domain_context_chunks_token_estimate check (token_estimate >= 0)
);

create index if not exists idx_domain_context_chunks_domain on domain_context_chunks (domain_id);
create index if not exists idx_domain_context_chunks_file on domain_context_chunks (context_file_id, chunk_index);
create index if not exists idx_domain_context_chunks_search_vector on domain_context_chunks using gin (search_vector);

-- =========================================================
-- 5. Task schema extensions
-- additive-first approach: extend existing tasks table
-- =========================================================

alter table tasks
  add column if not exists domain_id varchar(64),
  add column if not exists context_scope varchar(32),
  add column if not exists selected_context_ids jsonb not null default '[]'::jsonb;

alter table tasks
  add constraint fk_tasks_domain
    foreign key (domain_id) references domains(domain_id)
    on delete restrict;

alter table tasks
  add constraint chk_tasks_context_scope
    check (context_scope in ('domain_default', 'manual_selection') or context_scope is null);

create index if not exists idx_tasks_domain on tasks (domain_id);
create index if not exists idx_tasks_domain_created_at on tasks (domain_id, created_at desc);

-- =========================================================
-- 6. Optional explicit task-to-context links
-- useful for explainability and manual selection traceability
-- =========================================================

create table if not exists task_context_links (
  task_id varchar(64) not null,
  context_file_id varchar(64) not null,
  relation_type varchar(32) not null default 'selected',
  created_at timestamptz default now(),
  primary key (task_id, context_file_id, relation_type),
  constraint fk_task_context_links_task
    foreign key (task_id) references tasks(task_id)
    on delete cascade,
  constraint fk_task_context_links_context_file
    foreign key (context_file_id) references domain_context_files(context_file_id)
    on delete restrict,
  constraint chk_task_context_links_relation_type
    check (relation_type in ('selected', 'used'))
);

create index if not exists idx_task_context_links_task on task_context_links (task_id);
create index if not exists idx_task_context_links_context_file on task_context_links (context_file_id);

-- =========================================================
-- 7. Result schema extensions for explainability
-- =========================================================

alter table results
  add column if not exists domain_id varchar(64),
  add column if not exists used_context jsonb not null default '[]'::jsonb;

alter table results
  add constraint fk_results_domain
    foreign key (domain_id) references domains(domain_id)
    on delete restrict;

create index if not exists idx_results_domain_id on results (domain_id);

-- =========================================================
-- Notes
-- =========================================================
-- 1. This draft intentionally keeps legacy tables knowledge_documents and knowledge_chunks intact.
-- 2. Legacy project_id/service_name flow can continue during migration.
-- 3. New domain-aware flow should prefer domains + domain_profiles + domain_context_* tables.
-- 4. Automatic updated_at trigger logic can be added in a later migration if desired.
