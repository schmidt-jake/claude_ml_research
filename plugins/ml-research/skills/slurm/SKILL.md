---
name: slurm
description: Interact with an HPC cluster managed by SLURM — including NCSA Delta, University of Utah CHPC (notchpeak, kingspeak, lonepeak, granite, redwood), and any generic SLURM cluster. Use when submitting, monitoring, or debugging SLURM jobs; writing sbatch scripts; choosing partitions/QoS/accounts; tuning batch size; running interactive sessions (salloc, srun --pty); or diagnosing job failures (OOM, timeout, node errors). Also use when the user mentions sbatch, squeue, sacct, salloc, scancel, sprio, Delta, NCSA, bdhi, CHPC, notchpeak, job queues, GPU allocation, or cluster resource optimization.
---

You are on an HPC cluster managed by SLURM. Read the [SLURM quickstart guide](https://slurm.schedmd.com/quickstart.html). You are likely on a login node, but if `nvidia-smi` shows available GPUs, you are probably on a GPU-enabled compute node.

Primary use case: launching and monitoring distributed GPU-enabled training jobs.

## Identify the cluster

Before giving any cluster-specific advice (partitions, accounts, charge factors, filesystems, modules), identify which cluster you're on and load the corresponding site reference:

```bash
scontrol show config | grep ClusterName
```

| `ClusterName` value | Reference file to read |
|---|---|
| `delta` | `${CLAUDE_SKILL_DIR}/clusters/delta.md` |
| `notchpeak`, `kingspeak`, `lonepeak`, `granite`, `redwood`, `ash` | `${CLAUDE_SKILL_DIR}/clusters/chpc.md` |

If the cluster isn't in the table, proceed with the generic guidance below and explicitly note that site-specific details (partitions, charge rates, filesystem paths, account/QoS triples) are unknown — ask the user for a link to the cluster's user guide or have them paste `sinfo` output.

## Partition selection

Before submitting, survey the cluster state to pick the best partition and resource request. The goal is to jointly minimize expected time-to-start, time-to-completion, and total charge.

```bash
# Overview of partition availability and limits
sinfo -o "%20P %5a %10l %6D %6t %N"

# Current queue depth per partition
squeue -p <partition> --noheader | wc -l

# Node-level GPU and CPU utilization (if gnodes is available)
gnodes -p <partition>
```

Key trade-offs:

- **Preemptible partitions** typically have half the charge factor of their non-preemptible counterparts and shorter queue wait, but jobs can be preempted. Use for fault-tolerant workloads with checkpointing enabled.
- **Interactive partitions** have shorter max durations (often 1 hr) and higher charge factors, but may have shorter wait times. Use only for debugging and quick iteration.
- **GPU generation**: all else equal, prefer newer GPUs (Blackwell > Hopper > Ampere > Turing > Volta > Pascal) and more GPUs per node to reduce communication overhead. But if the cluster is busy, requesting fewer GPUs on an available partition may start sooner.
- **Billing rates**: the partition-level "charge factor" cited in cluster docs is shorthand for `TRESBillingWeights` (see next section). Effective cost depends on what the job actually requests, not just on which partition it lands in.

## TRES billing rates

A job's billing rate (the rate at which it consumes the project's allocation, expressed in billing-units per minute) is computed from the partition's `TRESBillingWeights` and the resources the job requests. Charge factors quoted in cluster documentation assume the job hits the "intended" shape for that partition — when it doesn't, the actual rate diverges, sometimes dramatically.

```bash
# The per-resource billing weights for a partition.
scontrol show partition <p> | grep -E 'PartitionName|TRESBillingWeights'

# How weights are combined.
scontrol show config | grep PriorityFlags

# What the scheduler actually computed for a specific job.
scontrol show job <jobid> | grep -E 'ReqTRES|AllocTRES'   # the billing= field is the rate per minute
```

How weights combine depends on `PriorityFlags`:

- `MAX_TRES` set: billing rate = max(weighted CPU, weighted Mem, weighted GPU). The job pays for whichever single TRES dominates; non-dominant requests are effectively free.
- Default (no `MAX_TRES`): billing rate = sum of all weighted contributions. Every requested unit costs.

Always check which mode applies before reasoning about cost.

### Reading TRESBillingWeights

A weight like `TRESBillingWeights=CPU=250, Mem=12G, GRES/gpu=3000` specifies billing-units per minute per resource:

- `CPU=250` — 250 billing-units per CPU per minute.
- `GRES/gpu=3000` — 3000 billing-units per GPU per minute.
- `Mem=12G` — 1 billing-unit per **12 GB** of memory per minute. The size suffix on memory weights sets the *divisor*, not the multiplier; without a suffix, the value is per-MB. Read the suffix carefully.

### Worked example (MAX_TRES)

Partition with `TRESBillingWeights=CPU=250, Mem=12G, GRES/gpu=3000`, job requesting `cpu=33, mem=240G, gres/gpu=1`:

| Resource | Computation | Billing/min |
|---|---|---:|
| CPU | 33 × 250 | **8250 ← dominant** |
| GPU | 1 × 3000 | 3000 |
| Mem | 240 / 12 | 20 |

Billing rate = 8250/min — driven entirely by CPU. The GPU is "free" because it doesn't dominate. Same shape under SUM mode would bill at 8250 + 3000 + 20 = 11,270/min. Confirm by reading `billing=` in `scontrol show job`.

### Right-sizing the request

Under MAX_TRES, the leverage point is the dominant TRES — trim *that one* until another TRES takes over; cuts to non-dominant resources don't change billing. Under SUM, trim whichever requests are most over-provisioned.

For a single-GPU job to make GPU the dominant TRES (and so cap the per-hour rate at the partition's GPU weight):
- `cpus-per-task ≤ GRES/gpu_weight ÷ CPU_weight`
- `mem ≤ GRES/gpu_weight × Mem_suffix_GB` (e.g. `Mem=12G` → up to `3000 × 12 = 36000 GB`)

Above those thresholds you're paying for CPU or memory, not the GPU. Whether shrinking CPUs hurts dataloader throughput is a separate empirical question — verify with a short profiling run before committing to a smaller request.

### Why this matters for QOSGrpBillingMinutes

`AssocGrpBillingMinutes` / `QOSGrpBillingMinutes` quotas are denominated in the same billing-units. When `squeue` shows `Reason=QOSGrpBillingMinutes`, the scheduler has projected `billing_rate × TimeLimit` against the remaining quota and refused to start the job. Lowering the *dominant* request (under MAX_TRES) or shortening `--time` may unblock it; cutting non-dominant requests will not.

## Understanding job priority

If a job pends with `REASON=Priority`, the scheduler ranked other jobs ahead of it. Under the multifactor priority plugin:

```
job_priority = sum(PriorityWeight<Factor> * normalized_factor) - nice
```

Inspect the cluster's weights and your own standing before reasoning about wait time:

```bash
scontrol show config | grep -E '^(Priority|PreemptType|SchedulerType|FairShare)'
sprio -w                      # effective factor weights
sprio -j <jobid> -l           # breakdown for a specific job
sshare -U                     # your fairshare (NormShares, EffectvUsage, FairShare)
scontrol show partition <p> | grep -E 'Priority(JobFactor|Tier)'
```

Key distinctions:

- **Fairshare** (`PriorityWeightFairshare`): usage relative to your account's allocation, decayed over `PriorityDecayHalfLife`. A `FairShare` score below ~0.2 means you're over-using and will sit behind other users in your account. It self-corrects after a half-life or two of idleness.
- **Partition** contributes two separate things: (a) `PriorityJobFactor` feeds the multifactor sum weighted by `PriorityWeightPartition`; (b) `PriorityTier` is a **hard pre-sort** — with `PreemptType=preempt/partition_prio`, a job in a higher-tier partition jumps ahead AND can preempt running jobs from lower-tier partitions on shared nodes. This is why `-preempt` partitions on most clusters sit at a lower tier than their standard counterparts.
- **Age** (`PriorityWeightAge`): bounded by `PriorityMaxAge`. Useful as a tiebreaker but rarely dominant.
- Any factor with weight `0` is irrelevant on that cluster — don't bother tuning `--qos=...` if `PriorityWeightQOS=0`.

### Reading pending-job reasons

`squeue` `REASON` tells you which lever matters:

- `Priority` — another job is ranked ahead. Backfill may still start yours if it fits a gap before a higher-priority job's predicted start.
- `Resources` — yours is next but no matching nodes are free. More priority won't help; wait or switch partitions.
- `AssocMaxJobsLimit` / `QOSGrpBillingMinutes` / `AssocGrp*` — account/QOS limit; priority is irrelevant until other jobs finish.
- `ReqNodeNotAvail` / "reserved for jobs in higher priority partitions" — preemption or reservation is gating your partition.
- `JobHeldUser` / `JobHeldAdmin` — held; release with `scontrol release <jobid>`.

### Estimating start time and picking a partition

`sinfo` and queue depth are proxies — they don't account for reservations, fairshare, or partition tier. Ask the scheduler directly instead:

```bash
# Predicted start time for a specific job shape on a specific partition.
# No job is queued; no SUs charged; no AssocMaxJobsLimit slot consumed.
sbatch --test-only \
  --account=<account> --partition=<partition> \
  --nodes=<N> --gpus=<G> --cpus-per-task=<C> --mem=<M> --time=<T> \
  --wrap='true'
# Output: "sbatch: Job <id> to start at <timestamp> ... in partition <p>"
```

Use `--test-only` to **compare partitions**, not to predict wall-clock wait. Empirically, the returned start time is the earliest the scheduler *could* place the job if it were the next one considered — it does not fully simulate queue position against other pending jobs. A real submission with a low priority score will often wait significantly longer than the `--test-only` timestamp suggested, especially when the cluster is busy and your fairshare is low.

Still, the same optimistic bias applies uniformly across partitions, so the **relative ordering** of predicted start times is a reliable signal for which partition is fastest at the real job's shape. Shape matters because backfill decisions depend on GPU count, memory, and walltime — a query at the wrong shape predicts nothing useful.

When multiple same-tier partitions are all plausible, let the scheduler pick:

```bash
# Real submission. SLURM places the job on whichever partition becomes eligible first.
sbatch --partition=gpuA100x4,gpuA40x4 scripts/train.sbatch
```

Caveat: multi-partition submission across priority tiers (e.g. mixing `-interactive` with standard, or standard with `-preempt`) is usually pointless — the higher-tier partition pre-sorts ahead regardless of load. Keep the partition list within one tier.

Once the real job is pending, `squeue --start -j <jobid>` shows backfill's committed start-time estimate. Unlike `--test-only`, this accounts for the job's actual priority rank in the queue — but it may report `N/A` for low-priority jobs the scheduler hasn't yet assigned a backfill slot to.


## Interactive sessions

For quick debugging, use `srun` to get an interactive allocation:

```bash
srun --account=<account> --partition=<interactive-partition> \
  --nodes=1 --gpus=1 --cpus-per-task=4 --mem=25G --time=01:00:00 \
  --pty bash
```

Use interactive sessions for: verifying a model loads, testing data pipelines, debugging CUDA errors, quick profiling. Don't use them for full training runs — use `sbatch` instead.

## SLURM support in PyTorch Lightning

Lightning has SLURM support via `lightning.fabric.plugins.environments.slurm.SLURMEnvironment`, including job preemption and requeueing. Read the [documentation](https://lightning.ai/docs/pytorch/stable/clouds/cluster_advanced.html). For anything beyond a quick debug run, make sure the job supports preemption and requeueing.

## Dataloader workers

The CPUs per task/rank (`--cpus-per-task`) should be equal to the number of dataloader workers (`--data.num_workers`) plus one (for the main process). Too few workers creates a data loading bottleneck that leaves the GPU idle. Check CPU utilization alongside GPU utilization during early training steps to verify balance.

## Monitoring and logging

All jobs should write stdout and stderr to `logs/%x/%j/%t/stdout.log` and `logs/%x/%j/%t/stderr.log`, respectively, using the [SLURM filename syntax](https://slurm.schedmd.com/sbatch.html#SECTION_FILENAME-PATTERN). Periodically monitor the job's status and resource usage. If the job hasn't started yet, check `squeue -j <jobid> -o "%T %r %S"` for state, reason, and predicted start time; for `REASON=Priority` use `sprio -j <jobid> -l` to see which factor is holding it back. Once the job has started, monitor its progress — it should enter the training loop within a few minutes of starting.

## Error recovery

**OOM (Out of Memory)**: check whether it's CPU or GPU OOM. For GPU OOM, reduce batch size or enable gradient checkpointing. For CPU OOM, reduce `num_workers`, `prefetch_factor`, or request more `--mem`. Resubmit after fixing.

**CUDA / NCCL errors**: often caused by hardware faults on a specific node. Check `sacct -j <JOB_ID> --format=JobID,State,ExitCode,NodeList` to identify the node, then exclude it with `--exclude=<node>` on resubmission. For NCCL timeout errors in multi-node jobs, verify the network interface and that `aws-ofi-nccl` or equivalent is loaded.

**Timeout**: if the job hit its wall-clock limit, request more time or optimize training speed (larger batch size, fewer val batches, mixed precision). For preemptible jobs, ensure checkpointing handles `SIGUSR1` so progress isn't lost.

**Preemption**: investigate the reason (cluster maintenance, higher-priority job). If frequent, consider switching to a non-preemptible partition. Ensure `--signal=SIGUSR1@120` and `--requeue` are set so Lightning can checkpoint and auto-requeue.

**Node failure**: SLURM will usually report `NODE_FAIL` state. Resubmit — no code changes needed unless it recurs on the same node.

## Writing sbatch scripts

Write `sbatch` scripts to the `scripts/` directory. These should be configured to run the appropriate training command with the appropriate configuration file and to write logs to the appropriate location. Use environment variables provided by SLURM (e.g. `SLURM_JOB_ID`, `SLURM_NNODES`, `SLURM_NTASKS_PER_NODE`) to configure the training command and logging.

### srun inside sbatch

Always launch the training command via `srun` inside sbatch scripts. Without `srun`, GPU binding (`CUDA_VISIBLE_DEVICES`) may not be set correctly, causing `cudaErrorDevicesUnavailable`. Example:

```bash
srun -l uv run --env-file=scripts/torch.env harness fit "${FIT_ARGS[@]}"
```

**Never background `srun` inside sbatch** (e.g. `srun ... &`). Backgrounded `srun` causes hangs during dataloader worker initialization. If you need to test signal handling, use SLURM's native `--signal` directive (e.g. `#SBATCH --signal=SIGUSR1@60`) instead of backgrounding a process and sending signals manually.
