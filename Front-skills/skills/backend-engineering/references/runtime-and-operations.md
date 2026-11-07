# Runtime, performance and operation

## Diagnose with a measured path

Trace request/trace IDs from the failing entrypoint to queries, queue work and external dependencies. Distinguish CPU saturation, event-loop/thread starvation, connection-pool waits, slow queries, lock contention and remote latency. Record baseline, workload, concurrency, payload/data size, cache state and resource limits before optimizing.

Measure latency distributions, throughput, errors and resource use; do not report averages as p95 or infer production capacity from one localhost request. Run a bounded load test only against an appropriate environment. Fix demonstrated costs before adding caching, batching or distribution.

## Resource lifecycles

Reuse bounded connection pools and clients according to the framework; account for replicas/serverless instances multiplying connections. Propagate deadlines/cancellation where possible. Keep blocking work off async/event-loop paths and stream large transfers with limits/backpressure rather than buffering everything.

On shutdown, stop accepting new work, drain bounded in-flight requests, stop/finish or safely release jobs and close clients before the platform's grace period. Test the interruption point relevant to the feature; an unawaited task may vanish when an invocation ends.

## Caching

Cache only when freshness and consistency requirements permit it. Include tenant, authorization-sensitive representation and other relevant dimensions in keys. A cache hit must not bypass access checks. Define expiry/invalidation, write ordering, stale-read policy and fallback on outage. Address stampedes with bounded coordination when observed or likely at scale.

Cache-aside does not automatically guarantee fresh reads after writes; a stale concurrent reader can refill an invalidated key. Decide whether to tolerate this, version keys/values or use a stronger strategy. Avoid caching errors or user-specific responses into shared keys accidentally. Test miss/hit, write, tenant separation and cache failure.

## Health and diagnostics

Separate startup completion, ability to serve traffic and process liveness. A downstream database outage is generally not repaired by repeatedly restarting every app process. Keep probes cheap and bounded; readiness may include critical dependencies according to service behavior. Use a startup probe when initialization needs time. [Kubernetes probe semantics](https://kubernetes.io/docs/concepts/workloads/pods/probes/) are a reference, not a requirement to adopt Kubernetes.

Log structured operation/status/duration and correlation identifiers with redaction. Expose rate/errors/duration and relevant saturation, queue or pool metrics. Avoid unbounded labels such as raw user IDs or full URLs in metric dimensions. Measure durations with an appropriate monotonic clock; do not return hard-coded “2 ms” as telemetry. Keep sensitive health details internal.

## Deployment and recovery

Reuse the project's build/deploy system. Validate required config without printing secrets, pin build dependencies/artifacts as appropriate and verify startup. Separate migration execution from uncontrolled simultaneous replica startup when duplicate execution would be unsafe.

For a release, name compatible app/schema versions, migration order, canary/health observations, stop criteria and rollback artifact. Include job/event versions and workers, not only HTTP pods. Test the relevant old/new combination during a rolling deployment. Define the point after which application rollback alone no longer works.

Do not mark deployment complete until the authorized target reports the expected version and scoped smoke/health checks succeed. Prepare concrete reviewable changes before any required approval; use authorization already provided. A disaster-recovery plan must address data restoration separately from selecting the previous container image.
