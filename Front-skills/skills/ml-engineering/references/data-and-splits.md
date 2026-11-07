# Data contracts and valid splits

Record one row's meaning, stable occurrence ID, entity/group ID if relevant, prediction timestamp, label definition and availability timestamp, feature availability, units, missing-value policy and immutable dataset version. Event time and time a value becomes available can differ. A refund outcome recorded later is not a valid feature for the original purchase decision.

Inspect distributions, missingness, duplicates, label counts, provenance and collection bias. Explore training data freely; inspect held-out data only as allowed by the evaluation protocol. If a data fix changes the dataset or splits, version the change and re-evaluate all compared candidates.

## Choose the evaluation target

| Intended use | Split policy | Failure to check |
|---|---|---|
| New independent observations | Random; stratify labels when appropriate | Related rows masquerading as independent examples |
| Previously unseen people, customers, documents or sites | Hold out whole relevant groups | Same entity/source or augmented original on both sides |
| Future observations of known entities | Forward temporal validation / rolling origin | Future aggregates, labels or revisions entering training |
| Future observations of new entities | Combined time and group constraints | A single off-the-shelf splitter satisfying only one constraint |

Match validation horizon and sampling to deployment. Irregular time series may need explicit calendar windows. `TimeSeriesSplit.gap` counts samples, not seconds; choose gaps/purging from overlapping feature/label windows and data latency. Do not shuffle time series across time boundaries. Group splitting tests unseen groups; it is not a universal rule for every repeated customer. See [scikit-learn cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html).

## Leakage audit

1. Audit feature construction at the simulated prediction time: use as-of joins, historic snapshots and lagged aggregates. A historic event subsequently corrected can still leak information.
2. Keep duplicate documents/images and all their augmentations in the same partition. Compare content fingerprints; review near-duplicates separately.
3. Confirm training labels would have arrived by each simulated fit cutoff. Purge label windows crossing that cutoff when required. An ordering check on event timestamps alone does not prove this.
4. Split before learned preprocessing. Fit encoders, imputers, scalers, feature selection and resampling only on the training fold; transform held-out rows with the fitted pipeline. Target encoders need leakage-aware training encodings too. [scikit-learn pitfalls](https://scikit-learn.org/stable/common_pitfalls.html).
5. Keep a final test set outside all tuning, early stopping and feature decisions. If data is too small for a stable holdout, use appropriate nested or outer evaluation and describe the limitation; do not call training-set scores generalization.

For tabular data, preserve schema and categorical handling in one pipeline. Treat ID columns as identifiers unless a defensible feature hypothesis and valid generalization test justify them. If a resampling method changes the validation prevalence, the resulting score may not represent deployment.

Use [audit_splits.py](../scripts/audit_splits.py) only on a minimal manifest with pseudonymous identifiers where possible. Its exact-ID, optional group/fingerprint and optional time checks supplement the audit above. It cannot inspect feature lineage, label windows, target encodings or near-duplicates.
