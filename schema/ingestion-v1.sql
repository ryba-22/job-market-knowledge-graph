create table if not exists raw_observation (
    id bigserial primary key,
    source_code text not null,
    requested_url text not null,
    final_url text not null,
    fetched_at timestamptz not null default now(),
    http_status integer not null,
    content_type text,
    payload_sha256 text not null,
    payload_text text not null
);

create table if not exists job_posting (
    id bigserial primary key,
    source_code text not null,
    source_posting_id text not null,
    canonical_source_url text not null,
    first_observed_at timestamptz not null default now(),
    last_observed_at timestamptz not null default now(),
    current_revision_id bigint,
    unique(source_code, source_posting_id)
);

create table if not exists job_posting_revision (
    id bigserial primary key,
    job_posting_id bigint not null references job_posting(id),
    revision_no integer not null,
    observed_at timestamptz not null default now(),
    normalized_content_hash text not null,
    title_source text not null,
    source_projection_json jsonb not null default '{}'::jsonb,
    normalized_projection_json jsonb not null default '{}'::jsonb,
    raw_observation_id bigint not null references raw_observation(id),
    unique(job_posting_id, revision_no),
    unique(job_posting_id, normalized_content_hash)
);

do $$ begin
    alter table job_posting
      add constraint job_posting_current_revision_fk
      foreign key (current_revision_id) references job_posting_revision(id);
exception when duplicate_object then null;
end $$;

create table if not exists posting_lifecycle_observation (
    id bigserial primary key,
    job_posting_id bigint not null references job_posting(id),
    raw_observation_id bigint not null references raw_observation(id),
    state text not null check (state in ('OBSERVED','CHANGED','UNCHANGED','SOURCE_EXPIRED','SOURCE_REMOVED','FETCH_FAILED','PARSER_DRIFT')),
    observed_at timestamptz not null default now()
);

create table if not exists organization_mention (
    id bigserial primary key,
    job_posting_revision_id bigint not null references job_posting_revision(id),
    mention_text text not null,
    normalized_mention text not null
);

create table if not exists organization (
    id bigserial primary key,
    canonical_name text not null,
    normalized_name text not null unique,
    status text not null check (status in ('CANDIDATE','RESOLVED','REJECTED'))
);

create table if not exists organization_candidate (
    id bigserial primary key,
    organization_mention_id bigint not null references organization_mention(id),
    organization_id bigint not null references organization(id),
    confidence_band text not null,
    status text not null,
    evidence_json jsonb not null default '{}'::jsonb,
    unique(organization_mention_id, organization_id)
);

create table if not exists organization_participation (
    id bigserial primary key,
    organization_id bigint not null references organization(id),
    job_posting_revision_id bigint not null references job_posting_revision(id),
    role text not null,
    epistemic_class text not null,
    confidence_band text not null,
    unique(organization_id, job_posting_revision_id, role)
);

create table if not exists match_candidate (
    id bigserial primary key,
    posting_a_id bigint not null references job_posting(id),
    posting_b_id bigint not null references job_posting(id),
    reason_json jsonb not null,
    status text not null,
    check (posting_a_id < posting_b_id),
    unique(posting_a_id, posting_b_id)
);

create index if not exists ix_raw_source_time on raw_observation(source_code, fetched_at desc);
create index if not exists ix_revision_posting on job_posting_revision(job_posting_id, revision_no desc);
create index if not exists ix_org_mention_norm on organization_mention(normalized_mention);
create index if not exists ix_participation_revision on organization_participation(job_posting_revision_id, role);
