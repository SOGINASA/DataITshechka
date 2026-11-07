# Public training-source inventory

These sources are separate from the protected 65-record DEV test set.

## Kazakh customer-support QA

- Repository: https://huggingface.co/datasets/mangi-llm/kazakh-customer-support-qa
- Attribution: Mäñgi ÜTM / `mangi-llm`.
- License: CC BY 4.0 (attribution required)
- Downloaded: 406 Kazakh question/answer records, plus upstream dataset card.
- Use limit: single-turn QA/domain labels, not a CQA dialogue-quality rubric. Do not map its `intent` or reference answers directly to our eight quality scores. If used, treat source text as a topic/reference seed, create new conversations and assign separate weak labels with provenance.
- Changes in this project: a deterministic sample of 16 Kazakh topics was machine-translated to Russian and English, then expanded into new synthetic dialogues with programmatic weak labels.

## Support-JSON-RU

- Repository: https://huggingface.co/datasets/A11Sunday/support-json-ru
- Attribution: A11Sunday.
- License: CC BY 4.0; attribution and notice of changes required. Code/adapter have separate licenses.
- Downloaded only `selected/train.parquet` (512 rows) and `selected/validation.parquet` (96 rows). The published test split was not downloaded.
- Use limit: synthetic Russian policy-conditioned decisions, not dialogue QA labels. Card states labels are programmatic/template-based and not human-reviewed; it also says the published test was already evaluated. Use train/validation only as auxiliary data, not as gold CQA supervision or as our evaluation set.
- Changes in this project: selected 128 records from the published train split as topic seeds, then created new synthetic dialogue variants and programmatic weak CQA labels.

The CC BY 4.0 legal text is included in `CC-BY-4.0.txt`. Translations, synthetic dialogues
and labels are modifications; they are not claimed to be source-dataset annotations.

## Separation rule

Never add IDs from `backend/ml/protected_test_ids.json` to training data, synthetic prompts, validation or model-selection runs. DEV may only be used for a final locked comparison after the model, prompt and thresholds are frozen.
