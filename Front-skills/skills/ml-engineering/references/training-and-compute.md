# Training, debugging and compute

First inspect project versions, data volume, target latency and available hardware. Reuse the environment and establish a small baseline. A tabular task does not automatically need deep learning; an existing pretrained representation can be a better first experiment than training from scratch. Avoid introducing a serving service for a notebook-only task.

## Device and budget

- Honor an explicit device configuration. If unavailable, report that and choose a fallback only when appropriate. Otherwise detect CUDA and Apple MPS through the installed PyTorch APIs and retain a CPU path. MPS requires actual runtime availability, not merely macOS. [PyTorch MPS](https://docs.pytorch.org/docs/stable/notes/mps.html).
- Estimate memory for parameters, activations, gradients, optimizer state, sequence/image size and batch; inference fit does not imply training fit. Measure a small batch before the larger run.
- Record max steps/epochs, trials, wall time, resource limits and stop conditions. Use early stopping only from development metrics. Do not start unbounded sweeps or paid cloud jobs merely because a reference suggests them.
- GPU-specific AMP settings, pinned memory and compilation are conditional optimizations. Verify device/dtype/operator support for installed versions; measure numerical stability, warmup overhead, memory and end-to-end throughput. Never promise a fixed speedup.

## Training correctness checklist

1. Check data/target shapes, dtypes, class mapping, missing values and finite values. Inspect an authorized sample; use deterministic evaluation preprocessing.
2. Run forward/loss/backward/optimizer for a tiny batch. Confirm parameters update and gradients are finite. Try to overfit a tiny training subset when suitable; augmentation/regularization may need temporarily disabling for this diagnostic.
3. Call `model.train()` for training and `model.eval()` for validation/inference. Also disable gradients for evaluation; `eval()` alone does not do that. Do not accidentally train through `.item()` or detached tensors.
4. Match loss and target encoding: e.g. multiclass cross-entropy expects logits and appropriate class targets, not an arbitrary extra softmax. Check masking and valid-token denominators for sequence losses.
5. For a loss reduced as a per-example mean, aggregate evaluation loss with sample counts, not an unweighted average of batch means. Use the actual weight/token denominator for weighted or masked losses. Reject empty evaluation loaders. Do not drop the last evaluation batch.
6. On macOS, begin with a simple loader and tune worker count by measurement. Use the main-entry guard for spawned processes; persistent workers require nonzero workers. More workers and pinned memory are not universally faster.
7. Clip gradients, schedule learning rate and accumulate batches only as justified by the model. With scaled gradients, unscale before clipping; account for accumulation and skipped updates. In distributed evaluation, avoid duplicate padded samples biasing counts.

## Repeatability and recovery

Seed Python, NumPy (including explicit generators), framework RNGs, data order and workers as used. Record deterministic settings and any unsupported operations. Identical seeds do not guarantee identical results across hardware, releases or platforms; deterministic paths can cost performance. [PyTorch reproducibility](https://docs.pytorch.org/docs/stable/notes/randomness.html).

Distinguish inference artifacts from resumable training checkpoints. Inference may need only weights, architecture/config and preprocessing. A faithful resume can also need optimizer, scheduler, scaler, RNG states, step/epoch and sampler/data position; verify resume against a short uninterrupted run when exact resume matters. Write checkpoints atomically and keep a known-good artifact.

Prefer explicit state dictionaries and trusted provenance. Restricted loading such as `weights_only=True` reduces exposure but does not make arbitrary artifacts universally safe. Check compatibility before loading; never silently enable remote code to get a download working. Record and test the dependency environment used for loading.
