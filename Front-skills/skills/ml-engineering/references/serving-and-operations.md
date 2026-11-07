# Integration and operations

Apply this lane only when shipping or maintaining inference is in scope. Batch inference, an in-process service class and an HTTP service are different options; keep the existing architecture unless requirements justify a change.

## Artifact and inference contract

Bundle or immutably reference weights, preprocessing, label mapping/tokenizer, configuration, feature/output schema, dependency lock, data/code lineage and evaluation report. Include units, allowed missing inputs, unsupported categories, input size bounds and model version.

Test a fixed example through training-time and serving-time preprocessing/scoring and compare within a declared tolerance. Add tests for malformed inputs, empty batches, missing features, artifact load failures and the specified fallback. Do not manufacture a confidence score when the estimator supplies only an uncalibrated margin.

Choose persistence for the serving environment. Pickle/joblib can execute code when loaded; load only trusted artifacts with known provenance. Alternative formats have model-coverage and compatibility constraints. Pin/test the load environment and verify predictions after conversion. [scikit-learn persistence](https://scikit-learn.org/stable/model_persistence.html).

## Promotion and rollout

Use the same evaluation contract for baseline, candidate and current production model. Validate configured metrics as finite numbers and include sample counts, important slices, resource limits and version identities. Missing evidence means a gate is unresolved, not passed.

Select a rollout method that fits the product: offline batch comparison, shadow scoring, canary or randomized experiment. Shadow traffic tests behavior and operations; it does not measure the causal effect of showing different decisions. Preserve a known-good artifact/config and a tested way to switch back without retraining. Authorized deployment requires actual post-deploy checks; a planned command is not deployment evidence.

## Monitoring

Track service errors, latency, load, memory/cost; schema/freshness/missingness; feature and prediction distributions; label arrival and quality by version/slice; and product outcomes. Distinguish data drift from demonstrated quality degradation. If labels arrive late, explicitly mark proxy metrics and evaluate outcomes once labels mature.

Use shared transformations and schemas to detect train/serve differences. Monitor sources of stale or unavailable features and biased feedback loops. An input-distribution alarm merits diagnosis; it does not by itself justify retraining or promotion. [Google monitoring guidance](https://developers.google.com/machine-learning/crash-course/production-ml-systems/monitoring).

Name the alert owner, review window, retraining criteria and rollback trigger. Store only necessary diagnostic identifiers with project-appropriate retention; avoid raw private inputs or credentials in run logs. Check the retrained candidate against the same contract before replacing the active model.
