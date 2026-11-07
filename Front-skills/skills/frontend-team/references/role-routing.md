# Role routing and knowledge

| Role | When useful | Knowledge loaded | Output |
|---|---|---|---|
| frontend-designer | New screen, redesign, visual direction, visual comparison | frontend-craft; selected real Forte images and reference notes | Brief, component/token choices, responsive/state acceptance criteria |
| frontend-builder | UI implementation and assigned fixes | frontend-craft + frontend-qa | Scoped changes, meaningful tests, preview instructions, current snapshot |
| frontend-code-reviewer | Meaningful diff, explicit source review | frontend-craft + frontend-qa + ecc-library | Concrete correctness/integration/security findings |
| frontend-browser-qa | Rendered UI changes and journeys | frontend-qa + frontend-craft | Viewed captures, journey matrix, repros |
| frontend-a11y-reviewer | Forms, dialogs, menus, focus/navigation, a11y request | frontend-qa + ecc-library; relevant W3C criteria | Barriers, tested keyboard/semantics coverage, limits |
| frontend-performance-reviewer | Performance request, heavy route, measured regression | frontend-qa + ecc-library; project profiling tools | Comparable measurements or explicit unmeasured hypotheses |

All six also read the shared contract. They load current skill files, not a frozen summary remembered from another session. Claude's adapters preload named SKILL.md content; explicit file paths in both host adapters locate the same sources and supporting resources. Never preload the whole ECC tree or all 63 images. Missing installed skill names do not justify ignoring existing target-project instructions.

Common task shapes:

- Tiny text/spacing correction: main agent + focused check, no team overhead.
- New interactive page: designer → builder → code reviewer + browser QA; add a11y for interaction changes, performance for relevant weight/latency risks.
- Bug in async search: builder → code reviewer → browser regression check. Usually no separate designer.
- Review only: requested reviewers; return defects, no builder or automatic fixes.
- Mobile visual audit: browser QA, designer if comparing directions, a11y if interaction barriers emerge.
- Slow dashboard: performance reviewer establishes evidence → builder fixes → performance remeasurement + affected browser/code checks.
- Full frontend audit: code, visual/journeys, accessibility and performance, bounded to requested routes and data. Use designer for brief comparison only if needed. No implementation until it belongs to the task.

`backend-engineering` is relevant only when the parent's task includes server/API changes. `ml-engineering` is not loaded for ordinary frontend work. Optional existing design-system/brand/ui-styling skills can supplement a real requirement when available; these agents do not require them or change them.
