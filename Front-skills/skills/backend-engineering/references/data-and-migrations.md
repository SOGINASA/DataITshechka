# Data correctness and migrations

## Invariants and concurrency

Start with constraints that express domain rules: uniqueness at the correct tenant scope, foreign keys, nullability, checks and allowed transitions. An application pre-check helps error messages but cannot replace a database constraint under concurrent writes. An upsert is only correct if the conflict target and update semantics match the domain.

For inventory/balances, use a conditional atomic update or appropriate locking and verify affected rows; do not read a value and blindly write a computed replacement. For cross-row invariants, choose the transaction boundary and isolation deliberately. Keep transactions short and avoid holding locks across network calls. Handle expected constraint conflicts distinctly from server failures.

PostgreSQL's isolation levels have different anomaly guarantees. A transaction is not automatically serializable; serialization failures can require retrying the entire transaction with fresh reads. Keep retries bounded and prevent replayed external effects. Read the target engine/version's documentation instead of assuming all databases share PostgreSQL behavior. [Transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html).

## Query diagnosis

Measure the failing query path with realistic cardinality and parameters. Check query count, N+1 loading, joins, indexes, sort/filter alignment, returned payload, connection-pool waits and replica lag. `EXPLAIN ANALYZE` executes the statement and can be expensive or mutating; use an appropriate isolated environment. Match indexes to observed access patterns and account for write/storage cost. Do not add an index merely because a column exists.

If using read replicas, define read-after-write requirements; a freshly created record may not yet be visible there. Scope cache keys, constraints and query predicates to tenant boundaries where relevant.

## Migration workflow

Use [migration-plan.md](../assets/migration-plan.md) for changes whose compatibility, size or recovery matters. Inspect generated SQL, the migration runner's transaction behavior and the exact destination before applying it. Development reset/push commands are not a production migration strategy.

For a rolling change that renames/replaces a field:

1. Expand schema so old binaries still work.
2. Establish a strategy for concurrent writes (compatible dual-write, controlled transition or equivalent) before relying on a backfill.
3. Backfill in bounded, restartable batches without overwriting fresher writes. Persist progress and reconcile missed/failed rows; `SKIP LOCKED` or an empty batch alone may not prove completion.
4. Verify coverage and consistency, then move reads to the new representation. Keep the rollback compatibility window explicit.
5. Remove old writes/readers and retire the old column only after all relevant binaries/jobs/consumers stop needing it.

Adapt this sequence to downtime tolerance and engine capability; not every small migration needs dual-write machinery. Preserve successfully applied migration history. Record controlled repair of a failed migration rather than silently editing history or forcing a version to hide drift.

## PostgreSQL specifics that affect plans

- Adding a nullable column can avoid rewriting rows but still takes a lock. A fast metadata change is not lock-free. Constant/non-volatile defaults can avoid rewrites on supported versions; volatile defaults and other changes may not. Adding NOT NULL without a valid value to a populated table can fail. Assess lock acquisition, timeout and scan/rewrite behavior for the actual statement. [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html).
- `CREATE INDEX CONCURRENTLY` allows ongoing writes but can wait on transactions, take longer and leave an invalid index after failure. It cannot run inside a transaction block. Check the runner and verify index validity afterward; `IF NOT EXISTS` does not prove the existing index has the intended definition. [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- Batch commits must actually be separate transactions under the chosen runner. A loop inside one enclosing transaction does not provide bounded commit/lock duration. Monitor progress, lock wait, replication lag and database load with stopping criteria.

## Recovery

Separate reverting application code, correcting schema and restoring lost data. Prefer compatible forward repair where suitable; a destructive DOWN migration may discard newly written data. Define rollback limits and restore/PITR procedure for the actual database before destructive changes. A backup must have a usable restore path and acceptable recovery point/time.

Prisma `migrate resolve --rolled-back` changes migration bookkeeping for a failed migration; it does not undo executed SQL. Reconcile the real schema/data and follow the installed version's recovery workflow. [Prisma recovery documentation](https://www.prisma.io/docs/orm/prisma-migrate/workflows/patching-and-hotfixing).
