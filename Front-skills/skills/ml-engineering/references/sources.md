# Sources and adaptation record

Researched 2026-10-30. This skill is an original synthesis for Codex and Claude Code. External pages are references, not installed runtime dependencies. Check the project's installed library versions before applying API examples. Primary sources were used; mirrors and generic SEO tutorials were excluded.

## ECC: pinned local source

Repository: [affaan-m/ECC](https://github.com/affaan-m/ECC/tree/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b), MIT, copyright 2026 Affaan Mustafa. The surrounding kit preserves the full snapshot and license under `library/ecc/`. These three complete SKILL.md entrypoints were read; this is not an audit of all referenced scripts or every supporting skill.

| Source | Adopted and adapted |
|---|---|
| [mle-workflow](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/mle-workflow/SKILL.md) | Data/prediction contracts, task-sized workflow, experiment evidence, model promotion and operations |
| [ml-adoption-playbook](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/ml-adoption-playbook/SKILL.md) | Baseline-first integration, inference boundary and fallback; no mandatory approval ritual or new API service for every task |
| [pytorch-patterns](https://github.com/affaan-m/ECC/blob/25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b/skills/pytorch-patterns/SKILL.md) | Explicit shapes, train/eval modes, checkpointing and profiling, with corrections below |

### Corrections made instead of blindly copying examples

- The ECC PyTorch device example detects CUDA/CPU only. The authored workflow includes MPS availability and workload-specific device choices.
- Seeds alone are not a complete reproducibility guarantee. Resume checkpoints may also need scheduler/scaler/RNG/sampler state.
- An unweighted average of batch-mean losses is wrong for uneven batches when an example-weighted mean is intended; the denominator must match loss reduction.
- Loader settings, AMP speedups and `torch.compile` modes are hardware/workload-dependent. No unconditional 2× acceleration or fixed best worker count is promised.
- `weights_only=True` is a restriction, not an assertion that all third-party files are safe. Inference weights and resumable checkpoints have different purposes.
- ECC's sample promotion gate comparisons do not explicitly reject NaN values. The authored workflow requires finite metrics and rejects missing evidence; its sample AUC/latency cutoffs are not adopted as defaults.
- Existing host/user authorization governs actions. ECC examples do not install agents, activate paid compute, request redundant approvals or publish model artifacts automatically.

## Additional official skills

Hugging Face repository main resolved to commit `25910b3d0ba31a2ba102f901cdc9e008c278a69c` during research. Its entrypoints were inspected as external references; training recipes/supporting scripts were not executed or bundled. This skill remains usable without installing the Hugging Face plugin.

- [TRL training skill](https://github.com/huggingface/skills/blob/25910b3d0ba31a2ba102f901cdc9e008c278a69c/skills/trl-training/SKILL.md): matching trainer objective to dataset format; verify stack/version-specific options before implementation. The source declares Apache-2.0.
- [Sentence-transformers skill](https://github.com/huggingface/skills/blob/25910b3d0ba31a2ba102f901cdc9e008c278a69c/skills/train-sentence-transformers/SKILL.md): model-type routing and the need to consult the matching loss/evaluator/template resources. Reviewed the routing and selected workflow sections; not its entire support tree.

## Primary technical documentation

| Source | Use in this skill |
|---|---|
| [scikit-learn: common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) | Train-only fitting and consistent preprocessing; Pipeline-based leakage prevention |
| [scikit-learn: cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html) | Independent, grouped and temporal evaluation; choose by generalization target |
| [scikit-learn: threshold tuning](https://scikit-learn.org/stable/modules/classification_threshold.html) | Separate prediction scores from operating decisions and tune on development evidence |
| [scikit-learn: persistence](https://scikit-learn.org/stable/model_persistence.html) | Artifact trust, serialization tradeoffs and environment compatibility |
| [PyTorch: reproducibility](https://docs.pytorch.org/docs/stable/notes/randomness.html) | Limits of seeds, deterministic settings and hardware/release dependence |
| [PyTorch: MPS](https://docs.pytorch.org/docs/stable/notes/mps.html) | Runtime detection and Apple accelerator support |
| [Hugging Face: choosing a metric](https://huggingface.co/docs/evaluate/choosing_a_metric) | Task-specific metric choice, expected inputs and limitations |
| [Google: Rules of ML](https://developers.google.com/machine-learning/guides/rules-of-ml) | Simple baselines, engineering checks and train/serve consistency |
| [Google: monitoring pipelines](https://developers.google.com/machine-learning/crash-course/production-ml-systems/monitoring) | Schema/feature validation, skew, delayed quality signals and production observation |

The split auditor and templates are newly authored for this kit. They do not reproduce third-party training code or make library-version claims. Their automated tests use only synthetic manifests. No real model training, fine-tuning, cloud job, dataset upload or deployment was performed while creating this skill.
