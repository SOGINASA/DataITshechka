---
name: frontend-qa
description: Verify rendered web UI quality and user interactions with screenshots, responsive checks, keyboard navigation, content states and project tests. Use for a frontend QA pass, visual review, responsive defects or checking a completed UI change. Does not deploy or run destructive production journeys.
---

# Frontend QA

Check the rendered interface against the user's requested behavior and the existing design system. Read [review-guide.md](references/review-guide.md). Keep the review proportional: a label change needs focused checks; a new multi-state page needs broader evidence.

1. Identify the changed surface, primary journey, supported viewports and applicable states. Locate existing project test/build commands and the available browser tools.
2. Start or connect to the intended local/preview app. Use the host's actual browser capability; tool names shown in third-party skills are examples, not guaranteed installed tools.
3. Inspect the affected view at narrow and wide sizes, adding an intermediate width for substantial layouts. Capture screenshots where possible and actually open them. A saved file alone is not visual review.
4. Exercise the primary flow and meaningful alternatives: no results, empty data, pending, validation error, recoverable server error, success, permission or partial data where applicable. Record unavailable states as untested, not passed.
5. Check keyboard access, focus visibility and restoration, names/labels, contrast, long text, image loading and reduced motion. Run available automated accessibility checks, but do not treat them as complete accessibility verification.
6. Run relevant project checks and examine the diff. Re-run affected checks after fixing defects. Do not impose a new coverage percentage or test framework on a styling task.
7. Report findings in severity order with route/component, viewport/state, reproduction, expected vs actual behavior, evidence and suggested fix. If implementation was requested, fix within scope and verify; review-only requests produce findings without edits.

Use [report-template.md](assets/report-template.md) when a persistent report helps. There is no mandatory score or JSON ceremony. Evidence must describe what was actually checked.

Respect the environment: local disposable test data can be exercised within the task. Production writes, payments, real outbound messages and destructive journeys require specific authorization and an appropriate test environment. Never infer that a QA request authorizes deployment.

If browser access or dependencies are missing, complete the checks you can run and label the rest unverified. Do not invent screenshots, metrics or a passing verdict. Without a baseline, say "visual inspection"; do not call it visual regression testing. Lab performance observations are not production field metrics.
