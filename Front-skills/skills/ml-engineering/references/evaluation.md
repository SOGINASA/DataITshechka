# Evaluation and experiments

Write the acceptance rule before choosing the winning model: primary metric and direction, baseline, meaningful improvement, allowed regressions, critical slices and resource budget. A simple CSV/JSON run ledger is enough initially; use the project's tracker when one exists.

## Baselines and metrics

| Task | Cheap baseline | Candidate evidence to choose by error costs |
|---|---|---|
| Classification | Class prior/majority, then linear or tree model | Confusion counts, precision/recall at the operating point, PR curve/AP for rare positives; calibration when probabilities drive decisions |
| Regression | Training median/mean or existing heuristic | MAE for absolute error; RMSE for stronger large-error penalty; residuals by target range and slice |
| Forecasting | Last value and seasonal naive | Horizon-specific errors and rolling backtests; avoid MAPE with zero/near-zero targets |
| Ranking/recommendation | Popularity/recency or current ranker | Recall/NDCG at actual display depth, query/user-level aggregation, coverage and popularity bias |
| Clustering/anomaly detection | Simple distance/rule method | Stability, domain review, known anomaly retrieval and alert workload; internal cluster scores alone do not prove usefulness |
| Generation/retrieval | Existing model, prompt or lexical search | Task success, unsupported claims, retrieval coverage and latency/cost; see the dedicated reference |

Specify positive class, averaging, weights, aggregation unit, units and sample counts. Do not compare scores with different candidate corpora or label coverage. Metric input formats and limitations are task-specific; consult the [Hugging Face metric guide](https://huggingface.co/docs/evaluate/choosing_a_metric).

Accuracy alone can conceal a failed minority class. ROC-AUC does not choose an operating threshold. F1 is a tradeoff, not a universal business objective. A score named probability is not automatically calibrated. Undefined AUC for a single-class slice is unavailable, not zero or a success.

## Selection, uncertainty and error analysis

- Select models/hyperparameters on validation or inner CV. Tune decision thresholds and calibration using appropriately held-out development predictions. Freeze those choices before final evaluation. [Threshold tuning](https://scikit-learn.org/stable/modules/classification_threshold.html).
- Compare candidates on identical examples and retain pairing. For confidence intervals, resample the independent unit (e.g. users or temporal blocks where appropriate), not automatically every row. Report procedure, counts and assumptions; fold standard deviation is not automatically a confidence interval. Repeated seeds measure training variation, not all sampling uncertainty.
- Inspect representative failures by segment, timestamp, missingness, source and difficult cases. Separate label ambiguity, pipeline bugs, model error and product ambiguity. Hypothesize one change capable of fixing the dominant failure.
- Avoid repeatedly probing the final test set. Once its results influence a change, say that it is now part of development; new final evidence is required.

## Reproducible evidence

Record run ID, code revision plus uncommitted patch identity, data snapshot/hash, split manifest, full configuration, preprocessing version, package lock, seed(s), hardware, elapsed time, peak memory, metrics and artifact hashes. Keep unsuccessful trials and stop reasons visible. Never imply that one seed establishes robust improvement.

For serving benchmarks record batch size, concurrency, warmup, data length, device and synchronization method. Separate warm inference from load/compile time when both matter. Use the target workload; laptop timing is not a production p95 estimate.

Promotion checks must reject missing, nonnumeric, NaN and infinite metrics, insufficient evaluation counts and unverified required slices. Declare direction and units for each gate; distinguish a percentage point from a relative percentage. Thresholds belong to the project contract. Do not copy example ECC constants such as AUC 0.82 into a new product.

Use [evaluation-report.md](../assets/evaluation-report.md). State what ran, with exact commands and observed outputs, and what remains untested.
