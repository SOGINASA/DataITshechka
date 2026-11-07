# Split auditor

`scripts/audit_splits.py` is a read-only Python 3.9+ standard-library helper. It does not split data, train models, load model files, upload anything or install dependencies. It reads only the CSV you give it. Use a minimal manifest with pseudonymous identifiers; it prints counts, enabled checks and up to ten logical CSV record numbers per issue code, never input cell values.

## Input and invocation

Required default columns: `row_id,split`. A row ID identifies a unique source observation, not merely a new index assigned after copying a sample. Duplicate row IDs fail even within a split. Splits are `train`, `validation` (`val` accepted) and `test`; train and test must have at least one valid row. Validation is optional unless `--require-validation` is set. Use this for a fixed holdout manifest or one outer-fold export at a time; a cross-validation manifest with overlapping folds is not this format.

Synthetic sample: [split-manifest.example.csv](../assets/split-manifest.example.csv).

From the skill directory:

```sh
python3 scripts/audit_splits.py assets/split-manifest.example.csv \
  --group-column entity_id --fingerprint-column content_hash \
  --time-column prediction_at --gap-seconds 86400 --require-validation
```

For real data replace the input path and configure only applicable checks:

| Option | Meaning |
|---|---|
| `--id-column`, `--split-column` | Override required column names |
| `--group-column` | Fail any group shared between partitions; use only when testing unseen groups |
| `--fingerprint-column` | Fail equal fingerprints across partitions; values must be computed consistently from relevant source content |
| `--time-column` | Require all train timestamps before validation, and all validation before test (or train before test if validation absent) |
| `--gap-seconds` | Minimum elapsed UTC seconds between adjacent partition extrema, in addition to strict ordering |
| `--require-validation` | Require a nonempty validation partition |

Time values must be ISO-8601 datetimes with explicit timezone, such as `2026-01-02T12:00:00+05:00` or `2026-01-02T07:00:00Z`. Equal boundary timestamps fail. The CSV need not be sorted. A nonzero gap requires `--time-column`; NaN/infinite/negative gaps fail. Configured fields cannot be blank, missing or reuse the same column. Surrounding whitespace on values is stripped; fingerprint case remains significant.

Exit codes: `0` enabled checks passed; `1` manifest/read/check failure; `2` invalid options. `rows_read` counts parsed data records, including invalid ones. `valid_rows_by_split` counts structurally valid records, including records subsequently flagged for overlap. Issue counts are detections, not the number of unique overlapping values.

## Interpretation

A PASS is a narrow manifest result. No group/time/fingerprint check runs without its option; inspect `checks` in the output. Known-entity forecasts often permit repeated entities and should not enable the disjoint-group requirement. For custom temporal policies allowing equal boundary instants, adapt the manifest policy or use a project-specific validator; do not misrepresent this helper's strict rule.

The script cannot detect fabricated IDs, near-duplicates, a poor fingerprint recipe, target leakage, pretrained benchmark contamination, learned-transform leakage, future joins or label-window overlap. Event-time gaps are not evidence of label availability. It keeps ID/group/fingerprint sets in memory (linear in unique values); use a database-backed audit for very large manifests.
