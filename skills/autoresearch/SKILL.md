---
name: autoresearch
description: Autonomous research and development for model architecture, data augmentation, and objective functions.
---

Goal: iterate autonomously and indefinitely on model architecture, data augmentation, and training loop via rapid small-scale experiments to discover improvements that *work at scale*.

## Scope

You may change architecture, data augmentation, training loop, objective function, hyperparameters, etc. Key code paths:

- `metabolo_genes/models/single_cell.py` (architecture, training loop, objective)
- `metabolo_genes/data/single_cell.py` (data augmentation)

**Do not** modify:

- validation dataset, logic, or existing metrics (adding new metrics alongside existing ones is fine)
- the random seed, number of training steps, or model width/depth

**Parameter budget**: try not to exceed the baseline parameter count. Verify before submitting: `uv run python .claude/skills/autoresearch/scripts/count_params.py`. Reducing parameters while maintaining performance is a valid direction.

**Utility at scale**: improvements should hold at scale (bigger models, more data, longer training). Avoid changes that overfit to the specifics of the current small-scale experimental setup/budget (regularization tuned specifically for small data / short runs, hyperparameter micro-optimization, tricks that exploit the specific number of training steps or val set composition).

**Engineering best practices**: All else equal, prefer changes that:
- simplify the codebase and reduce technical debt
- increase Model FLOPS Utilization

## Worktree

All work happens in a dedicated worktree at `../autoresearch` (`git worktree add ../autoresearch autoresearch`). Reuse it if it already exists. All commands, branching, and tracking files live there.

## Procedure

Each experiment runs on a single A100 for up to 45 min via `.claude/skills/autoresearch/scripts/launch.sbatch`. The launch script layers `.claude/skills/autoresearch/config.yaml` on top of `config/conf.yaml` (1 epoch, no checkpointing, reduced val batches, 30-min timer, W&B `autoresearch` tag). Override further with CLI args:

```bash
sbatch .claude/skills/autoresearch/scripts/launch.sbatch --model.lr=3e-4
```

Run `uv run harness fit --help` for docs on available overrides.

**Branching**: trunk is `autoresearch`. Each experiment gets a branch off trunk with the prefix `autoresearch/experiments/` (e.g., `autoresearch/experiments/003-gelu-activation`). Successful experiments are rebased, squash-merged into trunk. Failed branches are preserved. Rebase trunk onto `main` every ~5 experiments.

**Baseline**: the first experiment runs unmodified code to establish baseline metrics.

### Tracking

Tracking files live in `autoresearch/` (a subdirectory of the worktree root), not in the templates directory. Templates in `.claude/skills/autoresearch/templates/` are pristine starting points — **never edit them directly**.

**Initialization**: on first run (or if a tracking file is missing), copy each template into the tracking directory:

```bash
mkdir -p autoresearch
for f in autoresearch_ideas.md autoresearch_log.md autoresearch_results.csv; do
  [ -f "autoresearch/$f" ] || cp ".claude/skills/autoresearch/templates/$f" "autoresearch/$f"
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
6. Use the slurm skill to select the best partition, then submit:
   ```sh
   sbatch --partition=<selected> .claude/skills/autoresearch/scripts/launch.sbatch \
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
