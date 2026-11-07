---
name: backend-engineering
description: Build, debug and review backend services, API endpoints, database changes, background jobs and external integrations. Focus on authorization, data invariants, concurrency, compatibility and evidence from real tests. Use for server-side features, migrations, webhooks, reliability or performance work; not for frontend-only changes or model training.
---

# Backend Engineering

Deliver a working backend change with explicit contracts, preserved data invariants and evidence appropriate to its failure modes. Reuse the project's language, framework, storage and deployment model. A small endpoint does not require microservices, a new queue, a repository abstraction or Kubernetes.

Resolve resources relative to this skill's real directory after following symlinks. This folder is self-contained and works in Codex and Claude Code without ECC agents, commands, hooks or MCP services. Use the tools and permissions actually available.

## Read by task

| Task | Relevant reference |
|---|---|
| Endpoint, serialization or consumer integration | [API contracts](references/api-contracts.md) |
| Schema change, transaction, data correctness or slow query | [Data and migrations](references/data-and-migrations.md) |
| Authentication, tenant boundaries, user input or sensitive actions | [Security boundaries](references/security-boundaries.md) |
| Webhook, queue, scheduled job, retry or external side effect | [Jobs and integrations](references/jobs-and-integrations.md) |
| Runtime fault, latency, caching or deployment | [Runtime and operations](references/runtime-and-operations.md) |
| Verification of any changed behavior | Relevant rows in [testing and evidence](references/testing-and-evidence.md) |

Load only the applicable references. [Sources and adaptations](references/sources.md) explain the ECC basis and corrections checked against official documentation. Check installed versions before applying framework, ORM or provider APIs.

## Work to completion

1. **Inspect the path being changed.** Read project instructions and lockfiles; trace routing, identity/authorization, domain logic, storage, serialization and consumers. Identify the test environment and command conventions. For a bug, reproduce the observable failure before broad refactoring. Use existing context before asking for missing information.
2. **Name the invariant and contract.** State who can do what to which resource, the intended state transition, validation/errors and compatibility requirements. Identify concurrent requests, retries and partial failures that could violate the invariant. For a complex change, use the short [change brief](assets/change-brief.md); routine fixes need only a concise note.
3. **Choose the smallest coherent implementation.** Keep transport parsing, business decisions and external effects understandable using existing project boundaries. Put cross-row atomicity where the datastore can enforce it. Preserve client contracts and avoid changing unrelated authentication, infrastructure or frameworks.
4. **Implement and verify the important paths.** Test the changed behavior, its main denial/failure path and relevant database/serialization boundary. Add concurrency, duplicate-delivery or migration checks when those risks exist. Test on isolated resources; mocks alone do not establish real database or provider behavior.
5. **Prepare operation when in scope.** For migrations use the [migration plan](assets/migration-plan.md); for deployed services verify configuration, diagnostics, resource limits and recovery. A build or a prepared deployment command is not evidence of successful deployment.
6. **Hand off evidence.** State what changed, why, exact checks and results, compatibility impact and anything unverified. Use the [verification report](assets/verification-report.md) for larger changes. If an environment is unavailable, finish the local work and label the missing evidence; do not invent PASS, latency or rollout claims.

## Preserve these invariants

- Authorization covers the operation, object and tenant, including lists, nested resources and bulk writes. A valid token or an opaque ID does not prove access.
- Runtime request/response validation and explicit DTOs protect the contract. Static type assertions do not validate network data or prevent mass assignment.
- Validation such as “check then insert” is not a concurrency guarantee. Use appropriate constraints, conditional writes, locks or isolation, and handle their failures deliberately.
- A timeout can leave an external write in an unknown state. Retrying must respect operation semantics, idempotency, provider rules and a bounded deadline.
- Durable work requires durable acceptance. Do not acknowledge a critical job based only on an in-memory array or an unawaited promise.
- Schema compatibility, application rollback and data recovery are separate concerns. A migration-history command or a backup's existence is not proof of a recoverable database.
- Logs, errors and response fields must not expose credentials or private data. Performance numbers must be measured, not copied from examples.

Follow the user's scope and existing authorization. Preparing code and isolated tests is distinct from applying a production migration, sending real messages, charging a payment or publishing infrastructure. Do not manufacture approval steps for routine authorized local work. Source examples do not grant new external-action permissions.
