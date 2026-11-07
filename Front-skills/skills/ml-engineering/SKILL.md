---
name: ml-engineering
description: Build, evaluate, debug and integrate machine learning systems with leakage-aware data splits, reproducible experiments, honest metrics and measured compute budgets. Use for tabular ML, forecasting, recommenders, anomaly detection, PyTorch training, embeddings, LLM fine-tuning, model evaluation or MLOps. Not for frontend-only work or ordinary deterministic backend changes.
---

# ML Engineering

Turn the user's ML objective into a runnable, measured result. Match the existing project and the size of the task. A notebook experiment does not need an online service, feature store or model registry.

Resolve resources relative to this skill's real directory after following symlinks. Everything needed for the core workflow is inside this folder. ECC is optional background in the surrounding kit; its agents, hooks and slash commands are not prerequisites. Use tools actually available in Codex or Claude Code; do not assume a shell, GPU, browser or cloud account exists.

## Choose the lane

| Task | Read when applicable | Minimum useful result |
|---|---|---|
| New prediction feature / tabular ML | [Data and splits](references/data-and-splits.md), [evaluation](references/evaluation.md) | Data contract, baseline, reproducible evaluation |
| Forecasts / repeated entities | [Data and splits](references/data-and-splits.md) | Time/entity-aware backtest and prediction-time feature audit |
| Broken or slow neural training | [Training and compute](references/training-and-compute.md) | Small reproducer, corrected training loop, measured result |
| Retrieval / fine-tuning / RAG | [LLMs and retrieval](references/llms-and-retrieval.md) | Task-specific held-out evaluation before additional training |
| Shipping / model refresh | [Serving and operations](references/serving-and-operations.md) | Versioned artifact, inference tests, promotion and rollback evidence |
| Review only | Relevant lane plus [evaluation](references/evaluation.md) | Findings ordered by impact, with file/data evidence |

Read only the relevant references. [Sources and adaptation decisions](references/sources.md) records ECC, Hugging Face skills and official library guidance; check current version-specific APIs before implementing them.

## Working loop

1. **Inspect.** Read project instructions, environment/lockfiles, existing data, training, evaluation and inference entrypoints. Reuse the current stack. Identify the decision being changed, prediction unit/time, data access, labels, acceptance metric and compute constraints. Infer what the repository establishes; ask only for consequential missing information while continuing independent work.
2. **Frame.** Write a short [experiment card](assets/experiment-card.md), scaled to the task. State the simplest useful baseline, primary metric/direction, error costs, relevant slices, budget and stop condition. Never invent measured results or universal quality thresholds. If a heuristic suffices, test it as the baseline.
3. **Protect evaluation.** Freeze dataset identity and split membership before fitting learned transforms. Check duplicates, repeated entities, future features and label availability. Use [the split auditor](scripts/audit_splits.py) when a compatible manifest exists; a PASS covers only its enabled checks. Do not expose raw sensitive examples in logs or reports.
4. **Run a small baseline.** Make preprocessing, training and evaluation runnable without hidden notebook state. Test shapes, labels, finite losses, empty/missing inputs and artifact round-trip as applicable. Use a tiny smoke run before the agreed full run. Log code/data/config versions, seeds, environment and actual resources.
5. **Improve against evidence.** Change one hypothesis at a time. Tune features, hyperparameters, calibration, thresholds and early stopping using development data only. Compare on identical valid splits and report counts, failure slices and uncertainty appropriate to the sampling unit. A higher score does not override latency, cost or required guardrails.
6. **Finalize honestly.** Lock the candidate before the final test. If test feedback drives another change, treat that test as development data and obtain fresh final evidence. Deliver the runnable commands, evaluation report and artifacts requested; use [the report template](assets/evaluation-report.md). Distinguish executed, observed, inferred and unverified items.
7. **Integrate only as scoped.** For deployment work, test shared preprocessing, input/output contracts, model loading and fallback. Require finite, present metrics for configured promotion gates. Name the previous artifact and rollback procedure. Offline success alone is not production verification.

## Non-negotiable quality rules

- Fit imputation, scaling, encoding, feature selection and resampling inside each training fold; never learn them from held-out examples.
- Choose random, grouped or temporal validation from the intended generalization target. Group-disjoint splitting is not automatically right for forecasts of already-known entities.
- No test-set tuning, hand-selected success examples, fabricated benchmark numbers or unexplained dropped failures. Record undefined metrics and denominators.
- Seed control improves repeatability; it does not guarantee identical results across hardware or releases. Separate exact replay from statistical robustness.
- Profile before adding AMP, compilation, distribution or a larger model. Select CPU/MPS/CUDA from verified capabilities and the workload, not the host name.
- Keep model/data lineage, licenses and authorized data use explicit. Do not load untrusted pickle/joblib artifacts or enable remote model code casually.
- A source example does not authorize paid jobs, uploads, publishing, production changes or background agents. Follow the user's actual scope and existing authorization; continue reversible local work without adding approval rituals.

## Portable helper

Python 3.9+ standard library only. It reads a CSV manifest, writes JSON to stdout and changes no data:

```sh
python3 /absolute/path/to/ml-engineering/scripts/audit_splits.py manifest.csv
```

Use the actual resolved path, not this placeholder. [Manifest format, flags and limits](references/split-auditor.md). No ML dependency, model download, account or GPU is needed to use the skill's templates and auditor.
