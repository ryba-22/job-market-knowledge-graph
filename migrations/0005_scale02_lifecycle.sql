alter table ingestion_item drop constraint if exists ingestion_item_status_check;
alter table ingestion_item add constraint ingestion_item_status_check check (status in ('PROCESSING','SUCCEEDED','FAILED','SOURCE_GONE'));
alter table ingestion_attempt drop constraint if exists ingestion_attempt_outcome_check;
alter table ingestion_attempt add constraint ingestion_attempt_outcome_check check (outcome in ('SUCCESS','RETRYABLE_FAILURE','TERMINAL_FAILURE','SOURCE_GONE'));
