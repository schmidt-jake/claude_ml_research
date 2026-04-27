# NCSA Delta

Site-specific reference for the NCSA Delta cluster. Read alongside the generic SLURM guidance in this skill's `SKILL.md`.

Delta allocations follow the pattern `<project-code>-delta-gpu` (for GPU access) and `<project-code>-delta-cpu` (for CPU-only access). Check the user's allocations with `accounts` or `mychpc usage`; ask them which account to charge if unclear.

You have access to the `gnodes` and `jobinfo` executables provided by [slurm-utils](https://github.com/birc-aeh/slurm-utils/tree/master).

## GPU partitions

| Partition | GPU | GPUs/Node | Nodes | GPU Mem | Host RAM | Cores/Node | Max Duration | Charge Factor |
|---|---|---|---|---|---|---|---|---|
| `gpuA40x4` | A40 (PCIe) | 4 | 100 | 48 GB | 256 GB | 64 | 48 hr | 0.5 |
| `gpuA40x4-interactive` | A40 (PCIe) | 4 | 4 | 48 GB | 256 GB | 64 | 1 hr | 1.0 |
| `gpuA40x4-preempt` | A40 (PCIe) | 4 | 100 | 48 GB | 256 GB | 64 | 48 hr | 0.25 |
| `gpuA100x4` | A100 (SXM) | 4 | 100 | 40 GB | 256 GB | 64 | 48 hr | 1.0 |
| `gpuA100x4-interactive` | A100 (SXM) | 4 | 4 | 40 GB | 256 GB | 64 | 1 hr | 2.0 |
| `gpuA100x4-preempt` | A100 (SXM) | 4 | 100 | 40 GB | 256 GB | 64 | 48 hr | 0.5 |
| `gpuA100x8` | A100 (SXM) | 8 | 6 | 40 GB | 2 TB | 128 | 48 hr | 1.5 |
| `gpuA100x8-interactive` | A100 (SXM) | 8 | 2 | 40 GB | 2 TB | 128 | 1 hr | 3.0 |
| `gpuH200x8` | H200 (SXM) | 8 | 8 | 141 GB | 2 TB | 96 | 48 hr | 3.0 |
| `gpuH200x8-interactive` | H200 (SXM) | 8 | 1 | 141 GB | 2 TB | 96 | 1 hr | 6.0 |

GPU interconnects: A40 nodes use PCIe Gen4 (no NVLink). Quad A100 nodes have NV4 (4-way NVLink). Octa A100 nodes have NV12. H200 nodes have NV18. More NVLink = faster multi-GPU communication within a node.

Service unit (SU) = 1 GPU-hour. Each GPU comes bundled with 16 cores and ~62.5 GB RAM (quad nodes) or 250 GB RAM (octa nodes). Charges are based on whichever fraction is larger: GPUs requested or memory requested.

Default wall-clock if unspecified: 30 min. Default memory per core: 1000 MB.

Preempt queues guarantee a minimum 10 min run (PreemptExemptTime) plus 5 min grace if SIGTERM is handled.

### Partition selection guidance

- **A100x4** is the workhorse — best balance of availability, compute power, and cost for most training jobs.
- **A40x4** at 0.5x charge is good for jobs that don't need A100 compute (data preprocessing, smaller models, hyperparameter sweeps). A40 has more VRAM (48 GB) than quad-A100 (40 GB).
- **A100x8** for large models needing >4 GPUs or >256 GB RAM. 1.5x charge factor.
- **H200x8** for maximum throughput. 141 GB HBM3e per GPU eliminates most OOM issues. 3.0x charge factor — use only when the speedup justifies the cost.
- **Preempt variants** at half charge are worth using for any fault-tolerant workload with checkpointing.

## Job priority on Delta

Delta uses `priority/multifactor`. Effective weights (verify with `sprio -w`):

| Factor | Weight | Notes |
|---|---|---|
| Partition | 11000 | Dominant factor. Set by `PriorityJobFactor` per partition. |
| FairShare | 10000 | 1-day `PriorityDecayHalfLife` — recent usage is forgotten fast. |
| Age | 1000 | Caps at 7 days. Rarely dominant. |
| JobSize, QOS, Assoc | 0 | Irrelevant — don't bother tuning these. |

`PriorityFlags=MAX_TRES`: fairshare usage is scored on your single dominant TRES (typically GPU-hours), not summed across CPU+memory+GPU. Sizing memory to fit in a smaller billing bracket won't help if GPUs are your binding usage.

### Partition priority tiers

Each partition class has both a `PriorityJobFactor` (multifactor contribution) and a `PriorityTier` (hard pre-sort and preemption gate under `preempt/partition_prio`):

| Partition class                  | PriorityTier | PriorityJobFactor | Partition contribution |
|----------------------------------|-------------:|------------------:|-----------------------:|
| `*-interactive`                  |         1000 |             10000 |                 ~11000 |
| Standard (e.g. `gpuA100x4`)      |          100 |               100 |                   ~110 |
| `*-preempt`                      |           30 |                30 |                    ~33 |

Implications:

- Interactive partitions have ~100× the partition priority of standard batch AND sit at a higher tier — they jump the queue but cap at 1 hr and charge 2–6× standard. Use only for debugging.
- Standard batch tier (100) > preempt tier (30), so **standard batch jobs can preempt your `-preempt` jobs on shared hardware** — this is the mechanism behind the "preempt" name, not a background janitor.
- The `PriorityTier` gap (100 vs 30) is also a hard pre-sort: a standard-partition job will be considered before a preempt-partition job regardless of fairshare or age. Switching from `-preempt` to the standard partition typically dwarfs any fairshare deficit.

### Checking and interpreting your priority

```bash
sshare -U -o "Account,User,NormShares,EffectvUsage,FairShare"  # your fairshare standing
squeue -u "$USER" -o "%.10i %.12P %.8T %.10r %.10Q %.20S"      # job state, reason, priority, predicted start
sprio -j <jobid> -l                                             # factor breakdown
```

A `FairShare` score below ~0.2 means you're over-using and jobs will queue behind other users in your account. Because decay half-life is 1 day, this self-corrects after roughly a day of lighter activity — it isn't a long-term penalty.

Priority levers ranked by leverage, best to worst:

1. Move off `-preempt` into the standard partition (≈100× partition factor, jumps tier).
2. Wait out fairshare decay if you've been heavy (hours to a day, not weeks).
3. Drop to a less-contested GPU class (A40 vs A100 vs H200).
4. Shrink the allocation (fewer GPUs / less memory) so backfill can slot you into a gap before a higher-priority job's predicted start.

Age and QOS are not useful levers here.

## Filesystems

| Filesystem | Path | Quota | Purged | Use for |
|---|---|---|---|---|
| HOME | `/u/$USER` | 100 GB, 750K files | No (30-day snapshots via `~/.snapshot/`) | Code, configs, small files. Not for job I/O. |
| PROJECTS | `/projects/<code>` | 500 GB (up to 25 TB by request) | No | Shared project data, results, software. |
| WORK (HDD) | `/work/hdd/<code>` | 1 TB (up to 100 TB by request) | No | Primary job I/O and large datasets. |
| WORK (NVME) | `/work/nvme/<code>` | By request | No | Many small-file I/O workloads. |
| /tmp | Node-local SSD | 1.5 TB (GPU nodes) | After each job | Fast temporary storage. Not shared across nodes. |

Conventional data directory: `/work/hdd/<project-code>/$USER/data/`
Conventional job scratch pattern: `/work/hdd/<project-code>/$USER/$SLURM_JOB_ID/` (set as `$TMPDIR` in sbatch scripts)

## Multi-node networking

When running multi-node jobs (`$SLURM_NNODES > 1`):

```bash
module load aws-ofi-nccl
export NCCL_SOCKET_IFNAME=hsn
```

The `hsn` (Slingshot) interface is required for inter-node GPU communication.

## Preemption behavior

Preempt queues guarantee a minimum 10 min run (PreemptExemptTime). If preempted, job receives SIGTERM+SIGCONT, and will have 5 minutes GraceTime to checkpoint and exit before receiving another SIGTERM+SIGCONT followed by SIGKILL.

## Known issues

Some interactive partition nodes (e.g. gpua001, gpua022, gpua026) have intermittent `cudaErrorDevicesUnavailable` errors. These are transient hardware issues, not code bugs. If hit, retry — `srun` will typically land on a different node. For batch jobs, use `--exclude=<node>` to avoid known-bad nodes.

## Reference documentation

For details beyond what's inlined above, consult the official docs:

- [System architecture](https://docs.ncsa.illinois.edu/systems/delta/en/latest/user_guide/architecture.html)
- [Job accounting](https://docs.ncsa.illinois.edu/systems/delta/en/latest/user_guide/job_accounting.html)
- [Running jobs](https://docs.ncsa.illinois.edu/systems/delta/en/latest/user_guide/running_jobs.html)
- [Data management](https://docs.ncsa.illinois.edu/systems/delta/en/latest/user_guide/data_mgmt.html)
