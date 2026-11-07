# Sources and adaptation record

Researched 2026-10-30. Original synthesis for Codex and Claude Code; external documentation is a reference, not an installed dependency. The skill is stack-neutral. Follow the actual project's versions rather than upgrading libraries to match a sample.

## ECC basis

Pinned source: [affaan-m/ECC](https://github.com/affaan-m/ECC/tree/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b), MIT, copyright 2026 Affaan Mustafa. The surrounding kit preserves its full tree and license under `library/ecc/`; this standalone skill does not require that tree at runtime.

| Source | Review scope | Adaptation |
|---|---|---|
| [backend-patterns](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/backend-patterns/SKILL.md) | Entire SKILL.md | Boundaries, data access, caching and runtime work; no mandatory Node/Next stack |
| [api-design](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/api-design/SKILL.md) | Entire SKILL.md | API semantics, explicit contracts and client compatibility |
| [database-migrations](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/database-migrations/SKILL.md) | Entire SKILL.md | Expand/contract, restartable backfills and recovery with engine-specific corrections |
| [contract-first](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/contract-first/SKILL.md) | Entire SKILL.md | One authoritative schema, consumer needs and real serialized-response checks |
| [security-review](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/security-review/SKILL.md) | Auth, CSRF, rate limiting, sensitive-data sections | Controls matched to the actual boundary; tenant/object access and contextual cookie choices |
| [deployment-patterns](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/deployment-patterns/SKILL.md) | Health/probes, rollback and readiness sections | Measured diagnostics and distinct application/schema/data recovery |

Entrypoint review is not an audit of all support scripts or framework skills. Upstream remains unchanged; the authored skill contains corrections.

## Material corrections

- ECC's in-memory queue loses queued work on process exit and catches failures without durable recovery. The skill distinguishes best-effort work from durable acceptance, duplicate-safe processing and reconciliation.
- The retry example retries arbitrary errors without jitter, a total deadline or operation-specific side-effect checks. The new guidance requires an explicit bounded policy and addresses unknown outcomes.
- JWT verification plus a static cast does not validate the whole application claim contract or object/tenant authorization. The skill makes those checks explicit without replacing the existing identity provider.
- “No rewrite” is not “no lock” for PostgreSQL DDL. Default volatility, existing data and the actual ALTER operation matter; adding a NOT NULL column without a valid value to populated rows can fail instead of simply doing a safe rewrite.
- The early rename/backfill sample does not by itself protect writes arriving during migration. The fuller expand/contract approach must include write transition, reconciliation and version compatibility.
- Prisma `migrate resolve --rolled-back` in the deployment sample is metadata reconciliation, not SQL/data rollback. Recovery is designed against actual schema state and the installed runner.
- The sample health check returns a literal latency value. The authored instructions require real timing and distinguish liveness, readiness and startup.
- Cursor pagination does not guarantee a frozen view under arbitrary concurrent changes. Order, tie-breakers, mutable keys and snapshot policy matter.
- Fixed rate limits, a 10K-row pagination cutoff, a universal two-version policy and SameSite=Strict everywhere are not adopted as general rules.

## Primary sources checked

| Source | Decision supported |
|---|---|
| [RFC 9110, HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) | Methods, status, idempotent effects and conditional requests |
| [RFC 9457, Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html) | Standard error representation where appropriate |
| [OpenAPI specification](https://spec.openapis.org/oas/latest.html) | Canonical HTTP contracts and version-aware tooling |
| [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | Explicit access policy and object-level checks |
| [OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) | Token integrity/claims and server-side API controls |
| [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) | Browser credential/CSRF boundary |
| [OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) | Outbound destination, DNS/redirect and network controls |
| [PostgreSQL isolation](https://www.postgresql.org/docs/current/transaction-iso.html) | Transaction guarantees and complete-transaction retry |
| [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) | Locks, defaults and rewrite behavior |
| [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) | Concurrent build limitations and failure states |
| [Prisma recovery](https://www.prisma.io/docs/orm/prisma-migrate/workflows/patching-and-hotfixing) | Failed migration reconciliation vs actual database repair |
| [AWS timeouts/retries/jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) | Bounded retries and avoiding amplified failures |
| [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests) | Concrete provider-specific replay semantics |
| [Stripe webhooks](https://docs.stripe.com/webhooks) | Signed raw payloads, duplicates and asynchronous handling |
| [Kubernetes probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/) | Different startup/readiness/liveness purposes |

No third-party backend server, database, payment flow or cloud deployment was started to build this skill. The kit validates packaging and installation; the target project's real tests must establish backend behavior. No generic scanner is bundled that claims to prove API security or migration safety from source text alone.
