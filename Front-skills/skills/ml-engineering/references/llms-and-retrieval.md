# LLMs, embeddings and retrieval

Use this lane only when the task calls for it; ordinary ML is not synonymous with LLM fine-tuning.

## Diagnose before training

Build a representative held-out task set with expected outcomes, important failures and dataset provenance. Compare the current model/prompt or lexical search baseline. Decide whether errors stem from missing knowledge, retrieval, ranking, formatting, reasoning or domain behavior. Fine-tuning is one possible intervention, not the default answer to every weak response.

## Retrieval and embeddings

Freeze query sets, relevance judgments, corpus and chunking/index versions. Split related documents and paraphrase families appropriately; mine training negatives without looking at held-out labels. Distinguish an eligible corpus document from a training example: retrieval evaluation requires the relevant documents to remain in its evaluation corpus.

Measure candidate retrieval recall at K separately from reranking metrics and final answer quality. Record languages, filters, document lengths, index size and latency. Test a domain set; a public benchmark score need not transfer.

The official [Hugging Face sentence-transformers skill](https://github.com/huggingface/skills/tree/25910b3d0ba31a2ba102f901cdc9e008c278a69c/skills/train-sentence-transformers) distinguishes dense encoders, pairwise rerankers, sparse encoders and late-interaction models. Use the matching model/loss/data/evaluator references when implementing that specific stack. The entrypoint alone is insufficient to copy a training recipe; its support files are external, not bundled or installed here.

## Fine-tuning

Separate source documents/conversations before constructing examples. Verify tokenizer, chat template, label masks, truncation and dataset format using a small inspected batch. Keep held-out prompts and answers out of supervised targets, preference data and reward tuning. Inspect response-only vs full-sequence loss rather than assuming a flag behaves identically across versions.

Choose the learning objective from the available evidence: SFT uses demonstrations; preference training needs preference evidence; reward-driven training needs a defensible reward with checks against shortcuts. The [official TRL skill](https://github.com/huggingface/skills/blob/25910b3d0ba31a2ba102f901cdc9e008c278a69c/skills/trl-training/SKILL.md) maps trainer types to data formats. Verify current TRL/Transformers/PEFT APIs and hardware compatibility before adapting its examples. CUDA/FlashAttention examples are not drop-in Mac defaults.

Record base-model revision/license, tokenizer, adapter config, precision, training data, seed and budget. Compare candidate to the frozen base on both target tasks and necessary general capability checks. Measure adapter merge, quantization or export separately if the served artifact differs from training.

## Evaluation

Score task success and required format, correctness/groundedness and failure severity, along with latency and cost. Inspect critical failures; automatic lexical scores alone can miss semantic errors. If using an LLM judge, record judge revision, rubric and prompt, calibrate against human-scored examples, control order bias and disclose its limitations. Do not call judge scores ground truth.

Freeze prompt templates, retrieval settings and generation parameters for comparisons. Keep RAG answers grounded in retrieved evidence and test cases with missing/conflicting evidence. Red-team retrieved text that tries to alter tool behavior or reveal secrets as a product-specific test. Do not upload private data, publish models or start paid jobs without task authorization.
