# Experimental Qwen3 CQA adapter

This directory contains the MLX LoRA adapter and saved training checkpoints for the
multilingual weak-label pilot. It is not a complete base model and is not a production
quality model.

## Provenance and status

- Base: [`mlx-community/Qwen3-1.7B-4bit`](https://huggingface.co/mlx-community/Qwen3-1.7B-4bit), Apache-2.0; the base weights are not bundled here.
- Training corpus: `data/training/weak-cqa-v1/` (2,176 train, 320 validation, 320 synthetic test records).
- Label provenance: programmatic labels from controlled synthetic dialogue variants; not human gold.
- Last adapter: 125 of 300 planned optimizer steps. Training stopped when the Mac powered off.
- The single-dialogue smoke result is in `smoke_gen-ru-short-004.json`. It showed incorrect evidence IDs and incomplete reviewed ranges, so do not use this adapter for customer evaluation or production.

The `00000*_adapters.safetensors` files are intermediate checkpoints. `adapters.safetensors`
is the last saved adapter and currently matches the 125-step checkpoint.

## Load for research on Apple Silicon

Install the pinned training stack in a native ARM64 Python environment, then load the
base and adapter with MLX-LM:

```python
from mlx_lm import load

model, tokenizer = load(
    "mlx-community/Qwen3-1.7B-4bit",
    adapter_path="data/models/qwen3-1.7b-weak-cqa-v1",
)
```

To resume toward 300 steps on a Mac, use the dataset and last checkpoint:

```sh
MLX_TRAIN_ITERS=175 MLX_VAL_BATCHES=2 MLX_STEPS_PER_EVAL=100 \
  backend/ml/train_mac.sh \
  data/training/weak-cqa-v1 \
  data/models/qwen3-1.7b-weak-cqa-v1 \
  data/models/qwen3-1.7b-weak-cqa-v1/0000100_adapters.safetensors
```

If the resumed adapter is later committed, check `adapter_config.json` for local absolute
paths before publishing. The loader needs `fine_tune_type`, `num_layers`, and
`lora_parameters`; local paths and training logs should not be embedded in the committed
config.

## License notices

The base model is Apache-2.0. The public seed datasets are CC BY 4.0 and their attribution
and change notices are recorded in `data/public_sources/SOURCES.md` and the source cards.
The adapter is derived from the base model and is provided with its upstream license
notice. The training scripts and generated weak-label corpus are project artifacts; the
synthetic test split must not be represented as real-world QA accuracy.
