# University of Utah CHPC

Site-specific reference for the University of Utah Center for High Performance Computing clusters. Read alongside the generic SLURM guidance in this skill's `SKILL.md`.

## Clusters

General-environment clusters covered by this reference:

| Cluster | Login host | Notes |
|---|---|---|
| **notchpeak** | `notchpeak.chpc.utah.edu` (→ login1/login2) | Primary general cluster. Intel Skylake/Cascadelake + AMD Rome/Naples + mixed GPUs. |
| **granite** | `granite.chpc.utah.edu` | Newer Ampere/Hopper/Blackwell GPUs. |
| **kingspeak** | `kingspeak.chpc.utah.edu` | Older general cluster (Pascal/Maxwell GPUs). |
| **lonepeak** | `lonepeak.chpc.utah.edu` | No allocation required; older hardware. |
| **redwood** / **ash** | restricted (Protected Environment) | PHI/sensitive data only. |

Cross-submit with `sbatch -M <cluster> job.sh`. Check `mychpc` for your own allocations.

## Accounts, partitions, QOS (the golden rule)

Jobs need a compatible `--account` + `--partition` + `--qos` triple. Mismatched triples are the #1 reason jobs are rejected. Common valid combinations on notchpeak:

| Scenario | account | partition | qos |
|---|---|---|---|
| Free, short (≤8h), debugging | `notchpeak-shared-short` | `notchpeak-shared-short` | `notchpeak-shared-short` |
| General allocation (whole nodes) | `<PI>` | `notchpeak` | `<PI>` |
| General allocation, shared node | `<PI>` | `notchpeak-shared` | `<PI>-shared` |
| Use idle general cycles (preemptable, free) | `<PI>` | `notchpeak-freecycle` | `<PI>-freecycle` |
| Preempt owner nodes (free, preemptable) | `owner-guest` | `notchpeak-guest` | `owner-guest` |
| GPU, general allocation | `notchpeak-gpu` | `notchpeak-gpu` | `notchpeak-gpu` |
| GPU, owner preempt | `owner-gpu-guest` | `notchpeak-gpu-guest` | `owner-gpu-guest` |
| Your own owner nodes | `<PI>-np` | `<PI>-np` | `<PI>-np` (or unset) |

Run `sacctmgr -p -n show assoc user=$USER format=cluster,account,partition` to see exactly what you can use. The analogous patterns apply on other clusters — swap the suffix (`-kp`, `-lp`, `-grn`).

`*-shared` partitions let multiple jobs share a node; request `--mem` and `--cpus-per-task` carefully. Non-shared partitions give you the whole node regardless of what you request.

Preemptable partitions (`*-guest`, `*-freecycle`) can be killed at any time — only use for restartable/checkpointed work and set `--requeue` if appropriate.

## TRES billing rates on CHPC

CHPC bills against PI allocations (denominated in node-hours / SUs depending on cluster) for the standard general partitions (`<PI>`, `notchpeak`, `notchpeak-gpu`, equivalents on other clusters). Several partitions are explicitly free of allocation charge:

- `notchpeak-shared-short` (and equivalents) — free, capped at 8 hr.
- `*-freecycle` — uses idle general cycles, free, preemptable.
- `*-guest` (`owner-guest`, `notchpeak-gpu-guest`) — preempts owner nodes, free.
- `lonepeak` — no allocation required at all.

For partitions that *do* bill, inspect the per-resource weights directly — values vary by cluster and change over time, so don't reason from cached numbers:

```bash
scontrol show partition <p> | grep -E 'PartitionName|TRESBillingWeights'
scontrol show config | grep PriorityFlags     # MAX_TRES vs SUM
scontrol show job <jobid> | grep -E 'ReqTRES|AllocTRES'  # billing= field is units/min
```

See SKILL.md's "TRES billing rates" section for how to compute the dominant TRES and right-size requests. Whole-node (non-shared) general partitions may bill on the whole node regardless of what the job requests — confirm by submitting a tiny test and reading the resulting `billing=` field before drawing conclusions about cost levers.

For owner partitions (`<PI>-np`), the PI controls scheduling but jobs typically don't decrement a CHPC allocation. Treat them as free at the allocation level (subject to PI policy).

When `Reason=AssocGrpBillingMinutes` or `QOSGrpBillingMinutes` shows up on a pending job, the PI's allocation is exhausted or projected-cost-plus-used would exceed it. Contact help@chpc.utah.edu for the current balance, or check `mychpc usage`.

## Writing an sbatch script

Minimal template:

```bash
#!/bin/bash
#SBATCH --job-name=myjob
#SBATCH --account=notchpeak-shared-short
#SBATCH --partition=notchpeak-shared-short
#SBATCH --qos=notchpeak-shared-short
#SBATCH --time=1:00:00             # HH:MM:SS, or D-HH:MM:SS
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G                  # per node; or --mem-per-cpu=4G
#SBATCH --output=logs/%x/%j/stdout.log
#SBATCH --error=logs/%x/%j/stderr.log

set -euo pipefail
# module load <foo>   # if needed
srun ./my_program
```

Output dirs with `%x` (job name) or `%j` (jobid) must exist before submission — SLURM does not `mkdir -p` for you. `mkdir -p logs/myjob` in the submit script wrapper, or pre-create.

Useful extra directives:
- `--constraint=rom` — AMD Rome nodes (64 cores, no AVX-512)
- `--constraint="skl|csl"` — Intel Skylake/Cascadelake (have AVX-512)
- `--array=0-49%10` — array of 50, max 10 concurrent
- `--requeue` — safe for preemptable partitions
- `--mail-type=END,FAIL --mail-user=...`
- `--exclusive` — prevent node sharing even on `*-shared`

Walltime caps: 3 days default on general partitions, 14 days on most owner partitions, 8 hours on `notchpeak-shared-short`. Ask help@chpc.utah.edu for a `*-long` QOS to exceed.

## GPUs

Request via GRES: `--gres=gpu:<type>:<count>`. Omitting the type gives any GPU.

GPU types seen on notchpeak-gpu (general): `v100`, `2080ti`, `p40`, `a100`, `3090`.
On notchpeak-gpu-guest (preempt): add `a6000`, `a800`, `h100nvl`, `a100_80gb_pcie`, MIG slice `a100_80gb_pcie_1g.10gb`.
Granite hosts newer (`h200`, `h100`, `gh200`, `blackwell`).

List live inventory: `sinfo -p notchpeak-gpu -o "%N %G %m %c"`.

Load CUDA separately: `module load cuda/12.8.1` (use `module spider cuda` to list). The `(g)` marker on modules means "GPU node only."

## Storage

| Path | Size / quota | Backed up? | Purged? | Use for |
|---|---|---|---|---|
| `/uufs/chpc.utah.edu/common/home/$USER` | 50 GB default (purchasable up) | No (unless bought) | No | Code, configs, small datasets. |
| `/uufs/chpc.utah.edu/common/home/<group>` | Per-group purchase | Optional | No | Shared group data, software. |
| `/scratch/general/nfs1` | 595 TB pool | No | Yes — files untouched 60 days deleted | Job I/O. |
| `/scratch/general/vast` | ~1.5 PB, 50 TB/user | No | Yes — files untouched 60 days | Preferred high-throughput scratch. |
| `/scratch/rai/vast1` | 1.8 PB, 50 TB/group | No | No auto-scrub | AI Initiative members only. |
| `/scratch/local` | Node-local disk | No | Wiped at job end + 2-week scrub | Per-job temp. Point `TMPDIR` here for heavy tmp. |
| Pando (S3/Globus) | $150/TB/5y | No | No | Archive of large results. |

Rules of thumb: never run jobs writing to `$HOME` or group space (slow, no quota headroom). Stage inputs to `/scratch/general/vast`, write outputs there, copy finals back. Check usage with `mychpc storage` (hourly) or `ncdu` (real-time).

## Modules (Lmod)

- `module spider <name>` — best search, shows all versions and dependencies
- `module avail` — what's loadable *given currently-loaded modules* (hierarchy matters)
- `module load cuda/12.8.1`
- `module list`, `module purge` (except sticky `chpc/1.0` — don't remove)
- `ml` is shorthand for `module` (e.g. `ml load gcc`)

Hierarchy means some modules only appear after loading a compiler or MPI. If `module avail foo` shows nothing, try `module spider foo` and load its prerequisites.

## Interactive jobs

```bash
# Quick shared shell on shared-short (8h cap, free, no allocation)
salloc -A notchpeak-shared-short -p notchpeak-shared-short -q notchpeak-shared-short \
       -n 1 -c 4 --mem=16G -t 1:00:00

# GPU interactive
salloc -A notchpeak-gpu -p notchpeak-gpu -n 1 -c 8 --mem=32G --gres=gpu:1 -t 2:00:00
```

`salloc` drops you into a shell on the login node but with allocation reserved — `srun` or step commands execute on the compute node. For a true shell on the compute node, `srun --pty bash -l` after `salloc`, or use `srun --pty` directly.

## Monitoring / debugging

- `squeue --me` — your queued/running jobs
- `squeue -p <partition> --start` — expected start times on a partition
- `scontrol show job <jobid>` — full job detail (reason codes)
- `sacct -j <jobid> --format=JobID,State,ExitCode,Elapsed,MaxRSS,ReqMem,ReqTRES` — post-mortem
- `sstat -j <jobid>` — live stats for a running job
- `scancel <jobid>` / `scancel --me`

Common pending reason codes: `Priority` (queue ordering), `Resources` (waiting for nodes), `QOSMaxJobsPerUserLimit`, `AssocGrpCPURunMinutesLimit`, `ReqNodeNotAvail` (usually means mismatch of constraint vs. partition).

## Gotchas

- The account/partition/qos triple must match. `sbatch` error `Invalid account or account/partition combination` → run the `sacctmgr` query above.
- On shared partitions, `--ntasks` × `--cpus-per-task` is what you actually get; don't forget `--mem`.
- `notchpeak-shared-short` is account=partition=qos, has no allocation cost, and is the right default for testing/debugging.
- Preemptable jobs (`*-guest`, `*-freecycle`) can die at any moment — always add `--requeue` and checkpoint.
- `module load` inside an sbatch script will not carry `~/.bashrc` sourcing by default. Add an explicit `source /etc/profile.d/chpc.sh` or `source ~/.bashrc` if your env depends on it.
- `/scratch` is *not* mounted on login nodes universally — check `ls /scratch/general/vast` before assuming.
- Don't run heavy work on login nodes; they are killed by watchdogs and you'll get emailed.

## Docs

- Index: https://www.chpc.utah.edu/documentation/index.php
- Notchpeak guide: https://www.chpc.utah.edu/documentation/guides/notchpeak.php
- SLURM: https://www.chpc.utah.edu/documentation/software/slurm.php
- Modules: https://www.chpc.utah.edu/documentation/software/modules.php
- GPUs: https://www.chpc.utah.edu/documentation/guides/gpus-accelerators.php
- Storage: https://www.chpc.utah.edu/resources/storage_services.php
- Helpdesk: helpdesk@chpc.utah.edu
