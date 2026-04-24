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

# Account and data paths are not hardcoded — the caller must supply them:
#   --account=<slurm-account>   passed to sbatch on the CLI
#   AUTORESEARCH_DATA_DIR       env var, inherited by the job
#   AUTORESEARCH_SCRATCH_ROOT   env var, inherited by the job
# Example:
#   AUTORESEARCH_DATA_DIR=/work/hdd/<project>/$USER/data \
#   AUTORESEARCH_SCRATCH_ROOT=/work/hdd/<project>/$USER \
#   sbatch --account=<project>-delta-gpu --partition=<p> \
#     "${CLAUDE_SKILL_DIR}/scripts/launch.sbatch" \
#     --config="${CLAUDE_SKILL_DIR}/config.yaml"

set -euo pipefail

: "${AUTORESEARCH_DATA_DIR:?AUTORESEARCH_DATA_DIR must be set (dataset root)}"
: "${AUTORESEARCH_SCRATCH_ROOT:?AUTORESEARCH_SCRATCH_ROOT must be set (per-user scratch root; job dir is created beneath it as \$SLURM_JOB_ID)}"

DATA_DIR="$AUTORESEARCH_DATA_DIR"
JOB_DIR="$AUTORESEARCH_SCRATCH_ROOT/$SLURM_JOB_ID"
mkdir -p "$JOB_DIR"

export TMPDIR=$JOB_DIR

declare -a FIT_ARGS=(
    --seed_everything=42 \
    --config=config/conf.yaml \
    --trainer.num_nodes=$SLURM_NNODES \
    --trainer.devices=$SLURM_NTASKS_PER_NODE \
    --data.mdata_path=$DATA_DIR/combined.h5mu \
    --data.gtf_path=$DATA_DIR/gencode.vM25.annotation.gtf \
    --trainer.default_root_dir=$JOB_DIR \
    --trainer.logger.init_args.save_dir=$JOB_DIR \
    --trainer.logger.init_args.id=$SLURM_JOB_ID \
    --data.num_workers=4 \
    --data.prefetch_factor=4
)

# Caller supplies the plugin-bundled config override (and any other layered
# configs or arg overrides) via positional args. Because $@ is appended after
# FIT_ARGS, later --config files override earlier ones. Example invocation:
#   sbatch "${CLAUDE_SKILL_DIR}/scripts/launch.sbatch" \
#     --config="${CLAUDE_SKILL_DIR}/config.yaml" \
#     --trainer.max_epochs=50
FIT_ARGS+=("$@")

srun -l uv run --env-file=scripts/torch.env harness fit "${FIT_ARGS[@]}"
