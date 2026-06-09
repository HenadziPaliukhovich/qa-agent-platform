-- Domain-first thin-slice migration
-- Additive-first migration aligned with ADR 0001-0006

-- =========================================================
-- Domains
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
-- Domain profiles
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

alter table domain_profiles add column if not exists business_scope text;
alter table domain_profiles add column if not exists prompt_policy jsonb not null default '{}'::jsonb;
alter table domain_profiles add column if not exists retrieval_policy jsonb not null default '{}'::jsonb;
alter table domain_profiles add column if not exists supported_artifacts jsonb not null default '[]'::jsonb;
alter table domain_profiles add column if not exists event_source_settings jsonb not null default '{}'::jsonb;
alter table domain_profiles add column if not exists integration_bindings jsonb not null default '[]'::jsonb;
alter table domain_profiles add column if not exists created_at timestamptz default now();
alter table domain_profiles add column if not exists updated_at timestamptz default now();

-- =========================================================
-- Domain context files
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
-- Domain context chunks
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

alter table domain_context_chunks add column if not exists context_file_id varchar(64);
alter table domain_context_chunks add column if not exists domain_id varchar(64);
alter table domain_context_chunks add column if not exists chunk_index integer;
alter table domain_context_chunks add column if not exists content text;
alter table domain_context_chunks add column if not exists token_estimate integer not null default 0;
alter table domain_context_chunks add column if not exists metadata jsonb not null default '{}'::jsonb;
alter table domain_context_chunks add column if not exists created_at timestamptz default now();

create index if not exists idx_domain_context_chunks_domain on domain_context_chunks (domain_id);
create index if not exists idx_domain_context_chunks_file on domain_context_chunks (context_file_id, chunk_index);
create index if not exists idx_domain_context_chunks_search_content on domain_context_chunks using gin (to_tsvector('english', coalesce(content, '')));

-- =========================================================
-- Tasks extension
-- =========================================================

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'tasks'
      and column_name = 'domain_id'
      and udt_name = 'uuid'
  ) then
    alter table tasks drop constraint if exists fk_tasks_domain;
    alter table tasks rename column domain_id to legacy_domain_id_uuid;
  elsif exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'tasks'
      and column_name = 'domain_id'
      and udt_name <> 'varchar'
  ) then
    alter table tasks drop constraint if exists fk_tasks_domain;
    alter table tasks rename column domain_id to legacy_domain_id;
  end if;
end $$;

alter table tasks
  add column if not exists domain_id varchar(64),
  add column if not exists context_scope varchar(32),
  add column if not exists selected_context_ids jsonb not null default '[]'::jsonb;

alter table tasks
  drop constraint if exists fk_tasks_domain;

alter table tasks
  add constraint fk_tasks_domain
    foreign key (domain_id) references domains(domain_id)
    on delete restrict;

alter table tasks
  drop constraint if exists chk_tasks_context_scope;

alter table tasks
  add constraint chk_tasks_context_scope
    check (context_scope in ('domain_default', 'manual_selection') or context_scope is null);

create index if not exists idx_tasks_domain on tasks (domain_id);
create index if not exists idx_tasks_domain_created_at on tasks (domain_id, created_at desc);

-- =========================================================
-- Optional explicit task-to-context links
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

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'task_context_links'
      and column_name = 'context_file_id'
      and udt_name <> 'varchar'
  ) then
    alter table task_context_links drop constraint if exists fk_task_context_links_context_file;
    alter table task_context_links rename column context_file_id to legacy_context_file_id;
  end if;
end $$;

alter table task_context_links
  add column if not exists context_file_id varchar(64),
  add column if not exists relation_type varchar(32),
  add column if not exists created_at timestamptz default now();

alter table task_context_links
  alter column relation_type set default 'selected';

update task_context_links
set relation_type = 'selected'
where relation_type is null;

alter table task_context_links
  alter column relation_type set not null;

alter table task_context_links
  drop constraint if exists fk_task_context_links_context_file;

alter table task_context_links
  add constraint fk_task_context_links_context_file
    foreign key (context_file_id) references domain_context_files(context_file_id)
    on delete restrict;

alter table task_context_links
  drop constraint if exists chk_task_context_links_relation_type;

alter table task_context_links
  add constraint chk_task_context_links_relation_type
    check (relation_type in ('selected', 'used'));

create index if not exists idx_task_context_links_task on task_context_links (task_id);
create index if not exists idx_task_context_links_context_file on task_context_links (context_file_id);

-- =========================================================
-- Results extension
-- =========================================================

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'results'
      and column_name = 'domain_id'
      and udt_name <> 'varchar'
  ) then
    alter table results drop constraint if exists fk_results_domain;
    alter table results rename column domain_id to legacy_domain_id;
  end if;
end $$;

alter table results
  add column if not exists domain_id varchar(64),
  add column if not exists used_context jsonb not null default '[]'::jsonb;

alter table results
  drop constraint if exists fk_results_domain;

alter table results
  add constraint fk_results_domain
    foreign key (domain_id) references domains(domain_id)
    on delete restrict;

create index if not exists idx_results_domain_id on results (domain_id);
