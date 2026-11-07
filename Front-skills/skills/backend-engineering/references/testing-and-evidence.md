# Test behavior at the boundary that can fail

Use the existing project runner and isolated fixtures. Choose the applicable checks below; a tiny response-text fix does not need a new load test, full audit or migration suite. Protect live systems from test cleanup, mutation and notification side effects.

| Change | Evidence that matters |
|---|---|
| New or changed endpoint | Real serialization, happy path, malformed/invalid input, documented errors and relevant consumer contract |
| Authentication/authorization | Anonymous/invalid identity, permitted identity, forbidden action, another owner's/tenant's object and nested/bulk access |
| Create/update invariant | Database constraint/atomic behavior, conflicting simultaneous requests and correct affected-row/error handling |
| Retry/idempotency | Same key/same payload, changed payload conflict, two simultaneous attempts and interrupted/ambiguous outcome |
| Migration/backfill | Upgrade from previous schema with representative data, partial-run recovery, concurrent writes, data preservation and old/new binary compatibility |
| Queue/webhook | Invalid signature where applicable, duplicate/out-of-order delivery, crash/redelivery and durable acceptance |
| Cache | Hit/miss, invalidation/staleness behavior, tenant separation and cache outage |
| Performance/runtime | Reproducible baseline/workload, actual query/latency/resource evidence and targeted failure/shutdown behavior |

## Avoid misleading green tests

- Unit-test pure domain rules, integration-test database/query semantics with the actual relevant engine and contract-test serialized output. Mocks are useful for controlled external failures but cannot prove transaction isolation, SQL syntax, unique constraints or provider integration.
- Run concurrent requests/transactions when testing races; two sequential calls do not establish concurrency correctness. Synchronize the competing operations where useful instead of relying on arbitrary sleeps.
- Test a migration on an upgrade path with existing data, not only a fresh database. Test recovery according to the real runner; a mock “rollback called” assertion says nothing about restored data.
- In multi-tenant tests, use at least two tenants and valid cross-tenant IDs. Verify returned data and persistent effects, not only the HTTP status.
- Inspect actual side effects and task status. A 202 proves acceptance only if the implementation persisted it; a 200 from a webhook does not prove the worker completed the business operation.
- Do not turn snapshot churn or assertions mirroring private implementation details into proof of useful behavior. Keep regression tests tied to a reproducible failure/invariant.

## Report what was observed

Use [verification-report.md](../assets/verification-report.md) for substantial work. Include exact commands, environment/versions, relevant fixture scale, passed/failed checks and evidence location. Distinguish static type/lint/build success from tests, integration checks, load measurements and production observations.

State what could not run and its impact. If no database is available, do not claim SQL/migration compatibility from mocks; still complete the code, review the SQL and provide the exact remaining verification step. Stop expanding checks once the relevant requirements pass unless a new failure or unresolved concern warrants more work.
