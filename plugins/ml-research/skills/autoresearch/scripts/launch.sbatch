#!/bin/bash
#SBATCH --job-name=autoresearch
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=5
#SBATCH --mem=120G
#SBATCH --gpus-per-node=1
#SBATCH --time=00:45:00
#SBATCH --output=logs/%x/%j/%t/stdout.log
#SBATCH --error=logs/%x/%j/%t/stderr.log

# Assumes a Lightning-CLI-style project with:
#   - `uv run harness fit` as the training entrypoint
#   - a base config at `config/conf.yaml`
#   - `scripts/torch.env` providing CUDA / NCCL env vars
# Fork this script if your project deviates.
#
# Caller must supply:
#   --account=<slurm-account>    on the sbatch CLI
#   AUTORESEARCH_SCRATCH_ROOT    env var, per-user scratch root (job dir is
#                                 created beneath it as $SLURM_JOB_ID and
#                                 exported as $TMPDIR)
#   + any data / model / logger overrides, passed as positional args.
#
# Example:
#   AUTORESEARCH_SCRATCH_ROOT=/work/hdd/<project>/$USER \
#   sbatch --account=<account> --partition=<p> \
#     "${CLAUDE_SKILL_DIR}/scripts/launch.sbatch" \
#     --config="${CLAUDE_SKILL_DIR}/config.yaml" \
#     --data.path=/path/to/dataset

set -euo pipefail

: "${AUTORESEARCH_SCRATCH_ROOT:?AUTORESEARCH_SCRATCH_ROOT must be set (per-user scratch root; job dir is created beneath it as \$SLURM_JOB_ID)}"

JOB_DIR="$AUTORESEARCH_SCRATCH_ROOT/$SLURM_JOB_ID"
mkdir -p "$JOB_DIR"
export TMPDIR="$JOB_DIR"

declare -a FIT_ARGS=(
    --seed_everything=42 \
    --config=config/conf.yaml \
    --trainer.num_nodes=$SLURM_NNODES \
    --trainer.devices=$SLURM_NTASKS_PER_NODE \
    --trainer.default_root_dir=$JOB_DIR \
    --trainer.logger.init_args.save_dir=$JOB_DIR \
    --data.num_workers=4 \
    --data.prefetch_factor=4
)

# Caller-supplied args (plugin config, data paths, model/logger overrides)
# come last so they override FIT_ARGS via later-wins config layering.
FIT_ARGS+=("$@")

srun -l uv run --env-file=scripts/torch.env harness fit "${FIT_ARGS[@]}"
