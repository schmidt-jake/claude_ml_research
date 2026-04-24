#!/bin/bash
#SBATCH --job-name=autoresearch
#SBATCH --account=bdhi-delta-gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=5
#SBATCH --mem=120G
#SBATCH --gpus-per-node=1
#SBATCH --time=00:45:00
#SBATCH --output=logs/%x/%j/%t/stdout.log
#SBATCH --error=logs/%x/%j/%t/stderr.log

set -euo pipefail

DATA_DIR=/work/hdd/bdhi/$USER/data
JOB_DIR=/work/hdd/bdhi/$USER/$SLURM_JOB_ID
mkdir -p $JOB_DIR

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
