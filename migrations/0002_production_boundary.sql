create table if not exists ingestion_run (
    id text primary key,
    trigger_kind text not null,
    status text not null check (status in ('STARTED','COMPLETED','FAILED','PARTIAL')),
    source_scope text not null,
    parser_bundle_version text not null,
    normalizer_version text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    summary_json jsonb not null default '{}'::jsonb
);

alter table raw_observation
    add column if not exists run_id text references ingestion_run(id),
    add column if not exists source_posting_id text,
    add column if not exists parser_version text,
    add column if not exists transport_version text,
    add column if not exists archive_key text;

create unique index if not exists uq_raw_observation_run_payload
    on raw_observation(run_id, source_code, source_posting_id, payload_sha256)
    where run_id is not null and source_posting_id is not null;

alter table job_posting_revision
    add column if not exists parser_version text,
    add column if not exists normalizer_version text;

alter table organization_candidate
    add column if not exists resolver_version text;

alter table match_candidate
    add column if not exists candidate_generator_version text;

create table if not exists ingestion_item (
    id bigserial primary key,
    run_id text not null references ingestion_run(id),
    source_code text not null,
    source_posting_id text not null,
    status text not null check (status in ('PROCESSING','SUCCEEDED','FAILED')),
    raw_observation_id bigint references raw_observation(id),
    job_posting_id bigint references job_posting(id),
    error_message text,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    unique(run_id, source_code, source_posting_id)
);

create table if not exists ingestion_attempt (
    id bigserial primary key,
    run_id text not null references ingestion_run(id),
    source_code text not null,
    source_posting_id text,
    requested_url text,
    attempt_no integer not null,
    outcome text not null check (outcome in ('SUCCESS','RETRYABLE_FAILURE','TERMINAL_FAILURE')),
    failure_type text,
    http_status integer,
    error_message text,
    started_at timestamptz not null default now(),
    finished_at timestamptz not null default now(),
    unique(run_id, source_code, source_posting_id, attempt_no)
);

create index if not exists ix_ingestion_attempt_run_outcome
    on ingestion_attempt(run_id, outcome);
create index if not exists ix_raw_observation_archive_key
    on raw_observation(archive_key) where archive_key is not null;
