---
name: frontend-team
description: Coordinate frontend design, implementation, code review, browser QA, accessibility and performance agents using the Forte skills kit. Use when the user requests a frontend team, several independent checks, or an end-to-end frontend build-and-review workflow. Also supports review-only requests. Not for a small isolated edit that needs no delegation, backend-only work or ML training.
---

# Frontend team

Coordinate in the main conversation; specialist agents do bounded work and return evidence. This skill supplies a workflow, not a new service, permanent memory or permission to override host/project policy. Read [agent contract](references/agent-contract.md) and [role routing](references/role-routing.md). User and target-project requirements take priority.

## 1. Ground and scope

Identify the actual project, task mode (build-and-verify / review-only / design-only), user journey, acceptance criteria, framework, existing design system, changed files and current work. Read the target project's applicable instructions. Respect uncommitted work. Do not change application files in review-only mode.

Read frontend-craft and frontend-qa from the sibling skill directories; resolve this skill's real path if installed through a symlink. Discover available named agents and browser/test tools. Do not assume the host refreshed after installation or that the child sees the whole conversation.

Use the smallest useful team. A minor label or spacing fix usually needs direct implementation plus a focused check. A new interactive screen normally needs a brief, builder, code review and browser QA; add accessibility for meaningful interaction changes and performance when the scope or evidence justifies it. An explicit full frontend audit can use all review roles. A team request permits delegation within the requested scope when the host supports it; if higher-priority host rules prohibit delegation, follow the sequential fallback below.

## 2. Give each role a concrete handoff

Use [handoff template](assets/handoff-template.md), keeping only relevant fields. Supply absolute project path, task mode, role goal, assigned files, baseline/snapshot and diff, exact skill paths, acceptance criteria, current app URL/start command, fixtures and safe actions, evidence directory and previous results. Never include secrets. Record unresolved questions explicitly.

Only frontend-builder writes application code/tests. Default to one builder. Do not delegate concurrent writers to shared files. Read-only analysis can run in parallel only on a stable snapshot and when independent. Shared browser/preview state has one owner at a time, including builder self-checks, QA, accessibility and performance. Tool availability is not a reason to invent tests or install services.

## 3. Execute in useful order

1. **Design:** frontend-designer returns a concrete brief for substantial visual work. Skip when an existing brief/components already determine the change. No separate approval ritual unless the user's instructions actually require one.
2. **Implement:** frontend-builder edits the assigned scope and runs proportionate project checks. Capture the actual changed-file snapshot, including relevant untracked files; a commit SHA alone does not identify a dirty worktree.
3. **Review:** frontend-code-reviewer assesses correctness on that snapshot. Review-only requests start here or with the requested specialist; never run builder as an implicit fix step.
4. **Render:** frontend-browser-qa inspects the real UI and journeys at relevant sizes, captures and views images. Source review does not replace this. Run accessibility/performance when relevant, handing off the browser lease sequentially.
5. **Resolve:** consolidate duplicate findings, verify their evidence and choose the smallest justified fixes. In build-and-verify mode send them to builder, then rerun affected checks on the new snapshot. Keep pre-existing failures and unresolved questions visible. Do not relaunch the entire team for an unrelated tiny change.

Keep roles bounded: no recursive agent spawning, no unrelated audits or unsolicited redesign. Respect user time/compute constraints. Do not cycle indefinitely: after two unsuccessful fix/recheck attempts for the same issue, investigate its cause or missing input and report the concrete limitation; continue independent work rather than repeatedly retrying unchanged steps.

## 4. Finish with evidence

Read the returned reports and relevant artifacts yourself before relying on a conclusion. Use [report template](assets/report-template.md). Summarize delivered behavior or review findings, changed scope, checks actually executed and remaining limitations. Use `passed`, `failed`, `unverified`, `not applicable` for each relevant check; do not invent one universal green status when a required check is unavailable.

A verified delivery requires the requested behavior, scoped code checks, current rendered evidence for visual changes and no unresolved demonstrated blocking defects. If a required check cannot run, describe the implementation as delivered with that verification limitation. Do not call the whole application accessible, secure or fast from these specialist reports. Do not commit, merge, publish or deploy unless included in the user's authorization.

## Host fallback

Prefer the six installed named agents. If a host supports delegation but does not expose their names, pass the corresponding rendered role instructions and exact skill paths to a permitted general worker; say which fallback was used. If delegation is unavailable, follow the same role sequence in the main session and explicitly call it a sequential self-review, not an independent agent review. Missing browser/fixtures remains unverified; do not substitute imagined screenshots.

Installation, troubleshooting, sources and host formats: [frontend agents guide](../../FRONTEND-AGENTS-GUIDE-RU.md). This orchestrator depends on the full kit and sibling skills; the backend and ML standalone skills remain separate.
