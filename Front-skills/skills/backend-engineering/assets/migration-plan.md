# Migration plan

Change and invariant:
Engine/version, runner/version and target environment:
Current schema, row count/distribution and concurrent readers/writers:
SQL reviewed; transaction boundaries and lock/scan/rewrite behavior:

| Stage | Schema/data action | Compatible app/worker versions | Verification | Stop/recovery condition |
|---|---|---|---|---|

Backfill batching, progress identity and restart/catch-up strategy:
Concurrent-write correctness and reconciliation:
Expected lock duration/load and configured time/size limits:
Partial failure / invalid index / migration-history recovery:
Application rollback window and point of no return:
Data recovery/restore procedure and verified backup scope, if destructive:
Isolation and evidence from rehearsal with representative data:
Exact execution and verification commands (secrets referenced, not embedded):
Required production authorization and existing authorization, if applicable:
