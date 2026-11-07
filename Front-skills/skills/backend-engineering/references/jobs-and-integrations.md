# Retries, durable work and integrations

## Retry policy

For every external call, define timeout/deadline, retryable errors, total attempt/time budget and behavior after an ambiguous result. A timeout may occur after a side effect committed. Do not retry non-idempotent operations blindly or retry permanent validation/auth errors.

Use capped backoff with jitter when retries are appropriate; respect provider guidance and Retry-After within the remaining budget. Avoid multiplying retries across gateway, application and SDK layers. Propagate cancellation/deadline where supported and bound connection/read time as needed. Distinguish max attempts from retries. [AWS guidance](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/).

## Application idempotency

For duplicate-sensitive operations, define the key's scope (tenant/principal + operation), request fingerprint, retention, in-progress conflict behavior and replay result. Reuse a key only for the same logical operation. Atomically claim it with a unique constraint or equivalent durable mechanism; “look up, then insert” races.

For a local database effect, coordinate the idempotency record and business write in the same transaction where possible. For external effects, use the provider's idempotency mechanism and reconcile unknown outcomes. Recording a key after an external action leaves a crash window; recording it as completed before the action can lose work. Do not claim global exactly-once delivery from a local key table.

Provider semantics differ. For example, Stripe API v1 and v2 document different replay/failure behavior; check the actual API version, parameter matching and key lifetime rather than copying a universal 24-hour policy. [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests).

## Durable jobs and events

An in-memory queue is suitable only when losing that work is acceptable. For work that must survive process exit, persist acceptance before reporting it accepted. Use the existing durable queue or a deliberately designed database job table; a new broker is not mandatory.

Specify delivery guarantees and assume duplicates if the transport permits them. Acknowledge at the appropriate durable processing boundary; combine local deduplication and state changes transactionally. Make handlers safe on redelivery and partial failure. If an external side effect cannot be made idempotent, plan reconciliation or compensation rather than pretending a database transaction covers it.

Use transactional outbox/inbox patterns when a database write and message publication/consumption must stay consistent. An outbox relay can still publish duplicates. Define retry bounds, dead-letter/review handling, visibility/lease behavior, heartbeat for long work and safe replay. Bound worker concurrency and queue growth; expose backlog age, attempts and failures. A scheduled task can run twice or be missed; design the logical run identity and catch-up policy when that matters.

## Webhooks

Follow the provider's signature protocol over the exact bytes it signs, including timestamp/replay checks and secret rotation. Do not parse/re-encode a signed raw body before verification. Persist or durably enqueue accepted events, then return the appropriate success promptly; do not return success before reliable acceptance.

Deduplicate redeliveries, tolerate out-of-order events and protect monotonic business transitions. Delivery event ID and semantic business operation ID may differ; choose both where needed. Fetch current provider state if the protocol requires it instead of assuming arrival order is authoritative. Test invalid signatures, duplicates, concurrent delivery, delayed events, worker failure and redelivery after restart. [Stripe webhook guidance](https://docs.stripe.com/webhooks) is one concrete provider reference; other providers can differ.

Use test/sandbox integrations for verification. Sending real notifications, charging live payments, registering public webhooks or running production replay requires authorization from the task; a code example is not that authorization.
