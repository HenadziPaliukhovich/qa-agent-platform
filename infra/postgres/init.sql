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
