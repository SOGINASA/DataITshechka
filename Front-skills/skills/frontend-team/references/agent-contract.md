# Shared frontend agent contract

## Snapshot and ownership

The coordinator names a task mode, scope, owner and evidence directory. Read the applicable project instructions before work. Do not assume a child has the parent's history. Reuse observations only when their route, state, fixtures and code snapshot match the current task.

Identify a Git baseline by the actual base/ref and commit; also list the changed tracked and relevant untracked files, and capture their diff or content hashes. Do not hash or expose secrets. For non-Git work, use a focused before/after file inventory. If the scope changes during review, the coordinator marks affected evidence stale before proceeding. No reset/stash/checkout of unrelated changes to make a clean baseline.

One frontend-builder owns application/test edits. All other roles propose changes and return results. Parallel reading is useful for independent concerns on a stable snapshot. Tests that mutate shared fixtures and all browser-driving work are serialized or use genuinely isolated resources. Do not request worktrees merely to produce a read-only report. Keep builds/profile measurements from interfering with each other.

The browser lease records owner, URL/tab, preview process ownership, fixture state and evidence directory. Release it with a short description of current state. Do not close unrelated tabs or stop a server started by the user. Clean up temporary processes you started when the task is done unless the user needs the preview.

## Evidence and findings

Each finding includes priority, concrete trigger, location (file/line or route/control/state), actual/expected outcome, user impact, evidence and suggested correction. Use priorities proportionally:

- P0: a demonstrated critical issue needing immediate attention; unusual for a bounded UI pass.
- P1: a broken primary journey, data/security defect or inaccessible required interaction.
- P2: a material correctness, responsive, readability or usability problem affecting a defined case.
- P3: small polish or maintainability issues when they matter to the task.

A source-observed defect can be valid without running it; label its evidence accurately. Never turn a speculative pattern match into a demonstrated runtime defect. Optional taste/preferences and questions go separately. Do not invent issues to fill a quota. Duplicate symptoms of the same cause can share one finding.

Checks have status `passed`, `failed`, `unverified`, or `not applicable`, with scope and reason. A screenshot needs route, viewport, state, current snapshot and confirmation that the agent viewed it. If no baseline exists, current inspection is possible but a before/after regression claim is not. Record command and exit outcome for actual project checks; distinguish inherited logs from independent reruns.

Use the project's report location or the coordinator's scratch/evidence directory. Reports can be returned as text for the coordinator to save. Automated test tools may write their normal reports. Do not write application files during review or use shell as a workaround for a disabled edit tool. Do not capture tokens, cookies or private records in shared evidence.

## Bounded completion

The coordinator reconciles reports, assigns fixes only in implementation mode, and rechecks affected behavior. A specialist's clean result covers only its stated scope. Unavailable tools, production-only routes, missing login/fixtures or unknown baselines stay explicit. No full compliance/security/performance certification. Never silently skip failing checks, install a new global runtime, submit production journeys or publish results because an upstream workflow suggests it.
