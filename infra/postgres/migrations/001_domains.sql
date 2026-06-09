-- Domain schema bootstrap for qa_agent

create table if not exists domains (
    domain_id      uuid primary key default gen_random_uuid(),
    name           text not null,
    slug           text not null unique,
    description    text,
    status         text not null default 'active',
    tags           jsonb not null default '[]'::jsonb,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create table if not exists domain_profiles (
    profile_id     uuid primary key default gen_random_uuid(),
    domain_id      uuid not null references domains(domain_id) on delete cascade,
    name           text not null,
    description    text,
    settings       jsonb not null default '{}'::jsonb,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create table if not exists domain_context_files (
    context_file_id uuid primary key default gen_random_uuid(),
    domain_id       uuid not null references domains(domain_id) on delete cascade,
    filename        text not null,
    storage_path    text not null,
    mime_type       text,
    size_bytes      bigint,
    status          text not null default 'active',
    tags            jsonb not null default '[]'::jsonb,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create table if not exists domain_context_chunks (
    chunk_id        uuid primary key default gen_random_uuid(),
    context_file_id uuid not null references domain_context_files(context_file_id) on delete cascade,
    domain_id       uuid not null references domains(domain_id) on delete cascade,
    chunk_index     integer not null,
    content         text not null,
    metadata        jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists idx_domains_slug on domains(slug);
create index if not exists idx_domains_status on domains(status);
create index if not exists idx_domain_context_files_domain on domain_context_files(domain_id);
create index if not exists idx_domain_context_files_status on domain_context_files(status);
create index if not exists idx_domain_context_chunks_domain on domain_context_chunks(domain_id);
create index if not exists idx_domain_context_chunks_file on domain_context_chunks(context_file_id);
