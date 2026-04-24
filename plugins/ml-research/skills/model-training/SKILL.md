---
name: model-training
description: Staged pre-flight test procedure for an ML training loop before launching a full run. Use when the user says a model is "ready to train", asks for a "shakedown" / "smoke test" / "sanity check" before a big run, wants to verify the training loop, or is about to submit a long training job. Covers code correctness (fast_dev_run), learnability (overfit-one-batch), GPU efficiency (profiler + utilization), and fault tolerance (SIGUSR1 checkpoint/requeue). Composes with the `slurm` skill when tests need to run on a cluster.
---

Run a sequence of tests for the provided training loop. The tests build on each other and should be run in order — each one progressively tests more complex functionality. If a test fails, stop and fix the issue before continuing.

All tests require a GPU. Before starting, check for a local GPU with `nvidia-smi`. If one is available, run the test commands directly. If not, **load the `/ml-research:slurm` skill first**, then use it to write and submit an appropriate sbatch script (single GPU, short wall time, no W&B logging) for each test.

The test commands use `uv run harness fit` with config layering (later `--config` flags override earlier ones). Every test command should include:
- `--trainer.logger=false` to avoid polluting the W&B dashboard with test runs
- `--trainer.enable_checkpointing=false` since test runs don't need saved checkpoints

The base config is always `--config=config/conf.yaml`. Additional configs are layered on top depending on the test (see below). For precomputed-embedding variants, also layer `--config=config/conf_precomputed.yaml`.

## Test sequence

### 1. Code correctness

Run a single forward/backward pass on one batch using [fast_dev_run](https://lightning.ai/docs/pytorch/stable/common/trainer.html#fast-dev-run).

```bash
uv run harness fit \
    --config=config/conf.yaml \
    --trainer.fast_dev_run=1 \
    --trainer.logger=false \
    --trainer.enable_checkpointing=false \
    --trainer.detect_anomaly=true
```

Check for:
- No runtime errors
- No NaN or Inf in the loss
- All parameters receive gradients (anomaly detection will catch most issues)

### 2. Learnability

Overfit to one batch using [overfit_batches](https://lightning.ai/docs/pytorch/stable/common/trainer.html#overfit-batches). The `overfit_batch.yaml` config sets this up.

```bash
uv run harness fit \
    --config=config/conf.yaml \
    --config=config/overfit_batch.yaml \
    --trainer.logger=false \
    --trainer.enable_checkpointing=false \
    --trainer.max_epochs=500
```

Check that:
- Training loss drops to near zero (under epsilon) within ~10 minutes
- If it plateaus well above zero, the model may lack capacity or have a bug in the loss/forward pass

No validation is needed for this test.

### 3. GPU efficiency

Run for ~25 training steps and monitor GPU utilization. The `profile.yaml` config sets up the PyTorch profiler with appropriate warmup/active windows.

```bash
uv run harness fit \
    --config=config/conf.yaml \
    --config=config/profile.yaml \
    --trainer.logger=false \
    --trainer.enable_checkpointing=false
```

While running, monitor with `nvidia-smi` or `nvidia-smi dmon -s u` in another terminal. Disregard the first few steps as warmup. Check that:
- Step time is consistent (low variance after warmup)
- GPU memory allocation is close to the available max
- GPU utilization is high (>90%)

If memory utilization is low, consider increasing batch size, sequence length, or model dimension. If GPU utilization is low, the bottleneck is likely data loading — try increasing `num_workers` or `prefetch_factor`. Maximize batch size to fully utilize GPU memory, and scale learning rate accordingly. Use [`lightning.pytorch.callbacks.BatchSizeFinder`](https://lightning.ai/docs/pytorch/stable/api/lightning.pytorch.callbacks.BatchSizeFinder.html) to find the optimal batch size for the model and GPU configuration.

### 4. Fault tolerance

Training runs on SLURM are subject to wall-time limits (SIGUSR1) and priority preemption (SIGTERM). This test verifies the full interrupt-checkpoint-requeue-resume cycle using SLURM's native signal delivery.

Submit the dedicated fault tolerance test script:

```bash
sbatch scripts/test_fault_tolerance.sbatch
```

The script uses `#SBATCH --signal=SIGUSR1@60` with a 15-minute wall time. SLURM sends SIGUSR1 at ~14:00, which triggers `PreemptionCallback`:

- **Phase 1 (fresh):** Trains for ~14 minutes, then SIGUSR1 fires. The `_handle_wall_time` handler saves an HPC checkpoint, finalizes loggers, and calls `scontrol requeue`. Training should complete at least 1-2 epochs before interruption.
- **Phase 2 (resume):** The requeued job detects `last.ckpt` and resumes training with `--ckpt_path`. It trains the remaining epochs through `max_epochs=5`.

Check for:
- Phase 1 stderr: `"Received signal 10 (wall-time limit) — saving checkpoint and requeueing."`
- Phase 2 stdout: `"Phase 2: Resuming from checkpoint (post-requeue)"`
- Phase 2 stderr: `"Restored all states from the checkpoint at ..."`
- Final stdout: `"Fault tolerance test PASSED"`

**Signal handling architecture:** `PreemptionCallback` (a `SLURMEnvironment` subclass, registered as a trainer plugin) handles both signals. `ExceptionCallback` (a trainer callback) calls `PreemptionCallback.register_handlers()` during `on_train_start` and separately saves an emergency `on_exception.ckpt` for unhandled exceptions.

**Do not** test by manually sending `kill -SIGUSR1` to a backgrounded `srun` process inside sbatch — backgrounding `srun` causes hangs at dataloader initialization. Always use SLURM's native `--signal` directive.

### 4a. Mid-val fault tolerance (after callback / sampler / signal changes)

Verifies resume after SIGUSR1 fires *during validation*. The handler saves a checkpoint flagged with `saved_during_val=True`; on resume, `ExceptionCallback` monkey-patches `val_loop.run` to a one-shot no-op so validation is skipped rather than replayed from batch 0.

```bash
sbatch scripts/test_fault_tolerance_midval.sbatch
```

The script is tuned (`limit_train_batches=40`, `limit_val_batches=200`, `val_check_interval=20`) so the 15-minute wall clock lands inside the val loop on cycle 1. Phase detection uses `SLURM_RESTART_COUNT` (incremented on each requeue) because `ModelCheckpoint`'s `last.ckpt` is only written at epoch boundaries — mid-val preempts save an `hpc_ckpt_N.ckpt` that Lightning's `SLURMEnvironment` auto-detects on resume.

Check for:
- Phase 1 stderr: `"Received signal 10 (wall-time limit) — saving checkpoint and requeueing."`
- Phase 2 stdout: `"Skipping validation replay (mid-val preempt recovery)."`
- Phase 2 stderr: `"Restored all states from the checkpoint"`
- Final stdout: `"Fault tolerance mid-val test PASSED"`
- W&B run (if enabled) shows state transitions `running → preempting → running`.

Re-run this test whenever modifying:
- `ExceptionCallback.on_save_checkpoint` / `on_load_checkpoint` / `on_train_start`
- `PreemptionCallback` signal handlers
- `CellxGeneSampler` state-dict semantics

## Full training runs

After all tests pass, prepare a full-scale training run:

1. **Clean working directory.** `git status --porcelain` must be empty, so the commit hash tracked by W&B uniquely identifies the code used for training.
2. **Select partition.** Load the `/ml-research:slurm` skill to choose the right GPU partition based on the model's memory and compute requirements.
3. **Configure.** Adjust hyperparameters via config overrides or a new config file layered on top. For multi-GPU, the sbatch scripts automatically add `--config=config/fsdp.yaml` when `SLURM_NTASKS_PER_NODE > 1`.
4. **Submit.** `sbatch scripts/train.sbatch` (or the appropriate variant like `train_precomputed.sbatch`).
5. **Monitor.** Watch the run for the first few epochs in W&B. Check that loss curves, metrics, and GPU utilization look healthy. If anything looks off, stop the run and investigate before proceeding.
