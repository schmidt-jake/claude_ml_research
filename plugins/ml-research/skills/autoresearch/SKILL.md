---
name: autoresearch
description: Autonomously iterate on an ML model via rapid small-scale experiments — trying architecture variants, data augmentations, objective tweaks, or hyperparameter changes to find improvements that hold at scale. Use when the user asks Claude to "run a sweep", "try variants", "iterate on the model", "auto-research", or open-endedly "make the model better" / "improve val loss" without specifying a single change. Runs indefinitely and self-paced; do NOT invoke for a single targeted change or one-off experiment — use the `model-training` or `slurm` skills directly for those.
---

Goal: iterate autonomously and indefinitely on model architecture, data augmentation, and training loop via rapid small-scale experiments to discover improvements that *work at scale*.

## Scope

You may change architecture, data augmentation, training loop, objective function, hyperparameters, etc. At the start of each session, identify the project's model and data modules (confirm with the user if ambiguous) — typically the `LightningModule` subclass referenced by `config/conf.yaml`'s `model.class_path` and the data-augmentation code in the corresponding `LightningDataModule`.

**Do not** modify:

- validation dataset, logic, or existing metrics (adding new metrics alongside existing ones is fine)
- the random seed, number of training steps, or model width/depth

**Parameter budget**: try not to exceed the baseline parameter count. Verify before submitting: `uv run python "${CLAUDE_SKILL_DIR}/scripts/count_params.py"`. Reducing parameters while maintaining performance is a valid direction.

**Utility at scale**: improvements should hold at scale (bigger models, more data, longer training). Avoid changes that overfit to the specifics of the current small-scale experimental setup/budget (regularization tuned specifically for small data / short runs, hyperparameter micro-optimization, tricks that exploit the specific number of training steps or val set composition).

**Engineering best practices**: All else equal, prefer changes that:
- simplify the codebase and reduce technical debt
- increase Model FLOPS Utilization

## Worktree

All work happens in a dedicated worktree at `../autoresearch` (`git worktree add ../autoresearch autoresearch`). Reuse it if it already exists. All commands, branching, and tracking files live there.

## Procedure

Each experiment runs on a single A100 for up to 45 min via `${CLAUDE_SKILL_DIR}/scripts/launch.sbatch`. The launch script sets `config/conf.yaml` as the base; the caller layers `${CLAUDE_SKILL_DIR}/config.yaml` on top (1 epoch, reduced val batches, 30-min timer, learning-rate monitor). The script reads two caller-supplied values (nothing is hardcoded to a specific project):

- `--account=...` on the sbatch CLI — the SLURM account to charge (e.g. `<project>-delta-gpu` on Delta).
- `AUTORESEARCH_SCRATCH_ROOT` env var — per-user scratch root; the job creates `$AUTORESEARCH_SCRATCH_ROOT/$SLURM_JOB_ID` as its working dir and exports it as `$TMPDIR`.

Any data paths, model overrides, or logger settings are passed as additional CLI args after the config (later `--config=` values override earlier ones). Export `AUTORESEARCH_SCRATCH_ROOT` once per shell (e.g. in `~/.bashrc`) so you don't re-supply it each submit:

```bash
sbatch --account=<slurm-account> \
  "${CLAUDE_SKILL_DIR}/scripts/launch.sbatch" \
  --config="${CLAUDE_SKILL_DIR}/config.yaml" \
  --model.lr=3e-4
```

To tag experiments launched via this skill (recommended, makes them filterable in your tracker), append `--trainer.logger.init_args.tags+=[autoresearch]` — or whatever syntax your logger/jsonargparse combination uses for list-append.

Run `uv run harness fit --help` for docs on available overrides.

**Branching**: trunk is `autoresearch`. Each experiment gets a branch off trunk with the prefix `autoresearch/experiments/` (e.g., `autoresearch/experiments/003-gelu-activation`). Successful experiments are rebased, squash-merged into trunk. Failed branches are preserved. Rebase trunk onto `main` every ~5 experiments.

**Baseline**: the first experiment runs unmodified code to establish baseline metrics.

### Tracking

Tracking files live in `autoresearch/` (a subdirectory of the worktree root), not in the templates directory. Templates in `${CLAUDE_SKILL_DIR}/templates/` are pristine starting points — **never edit them directly**.

**Initialization**: on first run (or if a tracking file is missing), copy each template into the tracking directory:

```bash
mkdir -p autoresearch
for f in autoresearch_ideas.md autoresearch_log.md autoresearch_results.csv; do
  [ -f "autoresearch/$f" ] || cp "${CLAUDE_SKILL_DIR}/templates/$f" "autoresearch/$f"
done
```

Each file has a single responsibility — do not duplicate information across files.

- **`autoresearch_ideas.md`** — prioritized queue of **untried** ideas only. When you launch an experiment for an idea, remove it from this file. From that point the idea is tracked solely in the log and results CSV.
- **`autoresearch_log.md`** — narrative research log. Each entry: description/rationale, training dynamics, analysis, and complexity assessment. **No structured data** (metrics, run metadata, acceptance status) — that belongs in the CSV. Reference experiments by ID for cross-referencing.
- **`autoresearch_results.csv`** — single source of truth for all structured/quantitative data: experiment ID, title, branch, commit, SLURM job ID, W&B URL, date, parameter counts, metrics, acceptance status, and short notes.

### The loop

1. Start from `autoresearch` HEAD.
2. Pick an idea from `autoresearch_ideas.md` and remove it from the queue.
3. Branch: `git checkout -b autoresearch/experiments/NNN-description`.
4. Implement the changes.
5. Verify param budget with `count_params.py`.
6. Use the slurm skill to select the best partition, then submit (assumes `AUTORESEARCH_SCRATCH_ROOT` is exported):
   ```sh
   sbatch --account=<account> --partition=<selected> \
     "${CLAUDE_SKILL_DIR}/scripts/launch.sbatch" \
     --config="${CLAUDE_SKILL_DIR}/config.yaml" \
     --trainer.logger.init_args.name="$(git branch --show-current)" \
     --trainer.logger.init_args.notes="One-sentence summary of the change"
   ```
7. Monitor (poll `sacct -j <JOB_ID> --format=JobID,State,Elapsed,MaxRSS,ExitCode --noheader` every 2 min; check `logs/autoresearch/<JOB_ID>/0/std*.log` for health).
   - OOM: reduce batch size, relaunch.
   - NaN/exception: analyze, fix, relaunch.
   - Healthy: refine ideas for the next experiment.
8. Log results: add structured data (metrics, run metadata, acceptance) to `autoresearch_results.csv`; add narrative analysis (training dynamics, rationale, insights) to `autoresearch_log.md`.
9. Accept or reject per criteria below.

### Acceptance criteria

Merge into `autoresearch` if **all** hold:

- **Val loss**: lower than current best beyond a noise margin (>=1%).
- **Stability**: no divergence, oscillation, or pathological training dynamics.
- **Simplicity**: improvement magnitude justifies added complexity.

Ambiguous results (0–1%): log and move on — may revisit or combine later.

### Recovery

On resumption: verify worktree exists (`git worktree list`), check for running jobs (`squeue -u $USER -n autoresearch`), review tracking files and `git branch -a | grep autoresearch/` for unlogged work, then continue the loop.

### Rollback

If a merge introduces regressions: `git revert -m 1 <merge-commit>` and record in the log.

## Generating ideas

Never ask for user input. If stuck:
- Review `autoresearch_ideas.md` and `autoresearch_log.md`
- Read papers referenced in the ideas file or codebase
- Revisit previously rejected ideas — try variations, combine with other changes
- Analyze training dynamics and failure modes for clues
- Search the web, but adapt ideas to this context
- Try more radical ideas within scope

Users may volunteer feedback at any time.
