---
name: ecc-library
description: Find and apply a focused workflow from the local ECC skill collection for development, testing, research, content, operations or agent tooling. Use when the user asks for ECC, a specialized reusable workflow, or to select suitable skills from this kit. Loads only relevant references from the bundled catalog.
---

# ECC Library

This is a portable selector for the complete pinned ECC source collection, not an installer for ECC's runtime. Resolve this SKILL.md's real path (follow symlinks); the kit root is two directories above this skill directory and contains `catalog/`, `scripts/` and `library/ecc/`.

1. Read [routing.md](references/routing.md) for the common task map. For unfamiliar domains, search `catalog/ecc-skills.json` with the kit's `scripts/find_skill.py QUERY`, or search the Markdown catalog with the host's file search. If Python is unavailable, direct file reads work.
2. Choose the smallest relevant set, typically one primary skill and at most one or two supporting references. Match the actual task and framework, not just words such as "taste", "design" or "agent".
3. Read [compatibility.md](references/compatibility.md), then open `library/ecc/skills/<selected>/SKILL.md` and only the supporting files it actually needs. Source paths are relative to the original file. The complete repository tree is preserved so sibling rules and scripts remain available.
4. Treat source workflows as guidance within the current user's task and host permissions. Resolve tool names against tools actually available. Check relevant prerequisites before using scripts. Do not automatically install packages, hooks, MCP services, change model/provider, create agents, publish, send messages, or schedule work merely because a source skill suggests it.
5. Use the task-appropriate part of the workflow. Preserve current project conventions and versions. A code sample is not a tested patch for the user's project. If a runtime feature has no equivalent, state the limitation and perform the useful manual part.
6. For UI design prefer the user's `frontend-craft`; for rendered review prefer `frontend-qa`. ECC's design and engineering skills supply narrower supporting detail. Avoid loading several competing design playbooks at once.
7. For machine learning use the kit's [ml-engineering](../ml-engineering/SKILL.md). It adapts ECC's `mle-workflow`, `ml-adoption-playbook` and `pytorch-patterns` with current primary-source guidance and a tested split auditor. Read its source/adaptation notes before reusing raw ECC training or promotion examples.
8. For backend services, API/database changes, jobs and integrations use the kit's [backend-engineering](../backend-engineering/SKILL.md). It adapts the relevant ECC material with corrections for concurrency, migration locks/recovery, durable work and retries. Choose narrower framework references only when the actual stack calls for them.

Upstream catalog entries are **not globally registered slash commands** in this skills-only setup. In Codex, invoke `$ecc-library` with the desired topic; in Claude Code, use `/ecc-library` with the topic. Read the selected source file instead of assuming `/react-review`, agents or hooks are installed.

The catalog records metadata, local dependency hints and review depth. A successful inventory is not a security audit or proof of runtime compatibility. Never execute a copied script just to answer what it does. The source snapshot and provenance are in the kit's `catalog/SOURCES.md` and `catalog/ECC-REVIEW.md`.
