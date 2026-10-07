create table if not exists organization_evidence (
    id bigserial primary key,
    organization_mention_id bigint not null references organization_mention(id),
    organization_id bigint references organization(id),
    evidence_type text not null,
    direction text not null check (direction in ('SUPPORTS_IDENTITY','SUPPORTS_DISTINCT','NEUTRAL')),
    strength text not null check (strength in ('DECISIVE','STRONG','MEDIUM','WEAK')),
    epistemic_class text not null check (epistemic_class in ('FACT','INFERENCE','HYPOTHESIS','DECISION')),
    value_json jsonb not null default '{}'::jsonb,
    provenance_json jsonb not null default '{}'::jsonb,
    resolver_version text not null,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_org_evidence_fact
    on organization_evidence(
        organization_mention_id,
        evidence_type,
        md5(value_json::text),
        resolver_version
    );

create table if not exists organization_domain_candidate (
    id bigserial primary key,
    organization_id bigint not null references organization(id),
    domain text not null,
    status text not null check (status in ('CANDIDATE','VERIFIED','REJECTED','SHARED','UNKNOWN')),
    confidence_band text not null,
    evidence_id bigint not null references organization_evidence(id),
    resolver_version text not null,
    created_at timestamptz not null default now(),
    unique(organization_id, domain, evidence_id)
);

create table if not exists er_eval_pair (
    id bigserial primary key,
    posting_a_id bigint not null references job_posting(id),
    posting_b_id bigint not null references job_posting(id),
    stratum text not null,
    features_json jsonb not null,
    evidence_json jsonb not null default '[]'::jsonb,
    proposed_label text not null check (
        proposed_label in ('SAME_OPPORTUNITY','DISTINCT_OPPORTUNITY','UNRESOLVED')
    ),
    label_basis text not null check (
        label_basis in ('AUTO_DECISIVE','AUTO_COUNTER','HUMAN','PENDING')
    ),
    review_status text not null check (
        review_status in ('PENDING','REVIEWED','EXCLUDED')
    ) default 'PENDING',
    generator_version text not null,
    created_at timestamptz not null default now(),
    unique(posting_a_id, posting_b_id, generator_version),
    check (posting_a_id < posting_b_id)
);

create index if not exists ix_org_evidence_mention
    on organization_evidence(organization_mention_id, strength);
create index if not exists ix_org_domain
    on organization_domain_candidate(domain, status);
create index if not exists ix_er_eval_stratum
    on er_eval_pair(stratum, proposed_label, review_status);
