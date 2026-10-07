create table if not exists opportunity_evidence (
    id bigserial primary key,
    er_eval_pair_id bigint not null references er_eval_pair(id),
    posting_id bigint not null references job_posting(id),
    evidence_type text not null,
    direction text not null check (direction in ('SUPPORTS_SAME','SUPPORTS_DISTINCT','NEUTRAL')),
    strength text not null check (strength in ('DECISIVE','STRONG','MEDIUM','WEAK')),
    epistemic_class text not null check (epistemic_class in ('FACT','INFERENCE','HYPOTHESIS','DECISION')),
    value_json jsonb not null default '{}'::jsonb,
    provenance_json jsonb not null default '{}'::jsonb,
    extractor_version text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_opportunity_evidence
    on opportunity_evidence(
        er_eval_pair_id,
        posting_id,
        evidence_type,
        md5(value_json::text),
        extractor_version
    );

create table if not exists er_adjudication_decision (
    id bigserial primary key,
    er_eval_pair_id bigint not null references er_eval_pair(id),
    label text not null check (label in ('SAME_OPPORTUNITY','DISTINCT_OPPORTUNITY','UNRESOLVED')),
    basis text not null check (basis in ('AUTO_DECISIVE','AUTO_COUNTER','REVIEWER','INSUFFICIENT_EVIDENCE')),
    rationale text not null,
    evidence_snapshot_json jsonb not null default '[]'::jsonb,
    adjudicator_version text not null,
    supersedes_decision_id bigint references er_adjudication_decision(id),
    created_at timestamptz not null default now()
);

create index if not exists ix_opportunity_evidence_pair
    on opportunity_evidence(er_eval_pair_id, strength, direction);
create index if not exists ix_er_adjudication_pair
    on er_adjudication_decision(er_eval_pair_id, created_at desc);
