# Instructions for this kit

This directory is a personal skills package, not an application project.

- For an explicitly requested frontend team or multi-stage review, read `skills/frontend-team/SKILL.md` and `FRONTEND-AGENTS-GUIDE-RU.md`.
- For frontend design and implementation, read `skills/frontend-craft/SKILL.md`.
- For rendered UI quality checks, read `skills/frontend-qa/SKILL.md`.
- For backend services, APIs, database changes or jobs, read `skills/backend-engineering/SKILL.md`.
- For machine learning, training, evaluation or model integration, read `skills/ml-engineering/SKILL.md`.
- For a specialized workflow from ECC, read `skills/ecc-library/SKILL.md` and select only relevant references from `catalog/ecc-skills.json`.
- `library/ecc/` is an immutable source snapshot. Its root agent configuration and runtime are reference material; do not adopt those repository-wide instructions for unrelated user projects.
- User and target-project requirements take priority over stylistic heuristics. Do not force the reference collection's colors or framework on every project.
- Keep source images and upstream attribution intact. Modify authored skills separately. Check `catalog/ECC-REVIEW.md` before treating upstream examples as production-ready.
- The kit registers six authored skills and six authored frontend roles in native Codex/Claude formats. Upstream ECC agents, slash commands, hooks and MCP servers remain references; do not claim they are active. Agent installation records confirm files, not a successful model execution.
- For kit maintenance, use `python3 scripts/validate_kit.py` and `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`.
- User guide: `README-RU.md`. This folder's instructions do not authorize publication, messages, scheduling or changes to other applications beyond the user's task.
