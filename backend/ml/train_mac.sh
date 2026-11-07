#!/usr/bin/env bash
set -euo pipefail

# Train from a prepared dataset with fixed train/valid/test files. This launcher
# does not create labels or choose splits; synthetic pilots are not human-reviewed
# production releases. An optional checkpoint resumes into an existing output dir.
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <data-dir> <adapter-output-dir> [resume-adapter.safetensors]" >&2
  exit 2
fi

DATA_DIR="$(cd "$1" && pwd)"
case "$2" in
  /*) OUTPUT_DIR="$2" ;;
  *) OUTPUT_DIR="$PWD/$2" ;;
esac
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$BACKEND_DIR/.venv/bin/python"

for split in train valid test; do
  if [[ ! -s "$DATA_DIR/$split.jsonl" ]]; then
    echo "Missing or empty $DATA_DIR/$split.jsonl; refusing to train without all fixed splits." >&2
    exit 1
  fi
done
RESUME_ARGS=()
if [[ $# -eq 3 ]]; then
  case "$3" in
    /*) RESUME_ADAPTER="$3" ;;
    *) RESUME_ADAPTER="$PWD/$3" ;;
  esac
  if [[ ! -s "$RESUME_ADAPTER" ]]; then
    echo "Resume adapter does not exist or is empty: $3" >&2
    exit 1
  fi
  RESUME_ARGS=(--resume-adapter-file "$RESUME_ADAPTER")
fi
if [[ -e "$OUTPUT_DIR" && $# -eq 2 ]]; then
  echo "Output already exists: $OUTPUT_DIR (choose a new versioned path or provide a resume checkpoint)." >&2
  exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing backend/.venv. Install backend/requirements-train-mac.txt first." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_DIR")"
cd "$BACKEND_DIR"
"$PYTHON" -m mlx_lm lora \
  --model mlx-community/Qwen3-1.7B-4bit \
  --data "$DATA_DIR" \
  --train \
  --fine-tune-type lora \
  --mask-prompt \
  --batch-size 1 \
  --num-layers 8 \
  --iters "${MLX_TRAIN_ITERS:-100}" \
  --learning-rate "${MLX_LEARNING_RATE:-1e-5}" \
  --max-seq-length "${MLX_MAX_SEQ_LENGTH:-4096}" \
  --grad-checkpoint \
  --steps-per-report 10 \
  --val-batches "${MLX_VAL_BATCHES:-25}" \
  --steps-per-eval "${MLX_STEPS_PER_EVAL:-25}" \
  --save-every 25 \
  --seed "${MLX_TRAIN_SEED:-2026}" \
  --adapter-path "$OUTPUT_DIR" \
  "${RESUME_ARGS[@]}"
