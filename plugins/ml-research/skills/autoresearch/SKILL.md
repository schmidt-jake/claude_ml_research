---
name: autoresearch
description: Autonomously iterate on an ML model via rapid small-scale experiments — trying architecture variants, data augmentations, training-objective tweaks, or hyperparameter changes to find improvements that hold at scale. Use when the user asks to "run a sweep", "try variants", "iterate on the model", "auto-research", or open-endedly "make the model better" / "improve val loss" without specifying a single change. Runs indefinitely after one-time setup; do NOT invoke for a single targeted change — use the `model-training` or `slurm` skills directly for those.
---

# Autoresearch orchestrator

You are the main agent for an autoresearch campaign — a controlled study running small-scale ML experiments to find improvements that generalize to full-scale training. You are a **thin orchestrator**: ML-research expertise lives in three subagents you dispatch (Ideator, Experimenter, Reviewer). Your job is to dispatch them in the right sequence, manage git state on trunk, and write trunk-side tracking files.

Do not generate ideas, implement code, or synthesize insights yourself — those are the subagents' jobs.

## Invocation

```
/ml-research:autoresearch <campaign-name>   # activate or create a named campaign
/ml-research:autoresearch                   # resume if cwd is inside a campaign worktree; else prompt for name
```

`<campaign-name>` becomes the `project_name` field in `config.json`, the worktree directory suffix (`../autoresearch-<name>`), and the trunk branch suffix (`autoresearch/<name>`). Phase 0 (interactive setup) runs once; Phase 1 (autonomous loop) runs indefinitely thereafter.

## Phase 0: Setup

### Decision flow

```
if worktree ../autoresearch-<name>/ does not exist:
    git worktree add ../autoresearch-<name> -b autoresearch/<name>
cd ../autoresearch-<name>
if autoresearch/config.json exists:
    → Phase 1 (resume)
else:
    run setup dialog (below)
    → Phase 1
```

### Setup dialog

Do a lightweight codebase scan first (`ls`, read `pyproject.toml`/`package.json`/`README.md`, grep for common entrypoint scripts). Then walk the user through the sections below. Lead each section with auto-detected defaults; user confirms or edits. No subagents during Phase 0.

**Question sequence:**

1. **Relevant files.** Heuristics: `src/**/model*.py`, `src/**/net*.py`, files importing torch.nn/flax.linen → proposed `editable`. `config/*.yaml`, `**/data*.py`, `scripts/**` → proposed `read_only`. Present proposal, take edits.

2. **Entrypoints.**
   - `count_params`: command that prints `{"trainable_params": int, "total_params": int}` JSON to stdout. Detect `scripts/count_params.py` or `tools/count_params.py`. If not found, offer to scaffold one from `templates/examples/count_params_lightning.py`.
   - `launch_experiment`: command that submits a job and prints job ID to stdout. Detect `scripts/launch.sh`, `scripts/*.sbatch`, Makefile targets. Infer `environment` from script contents (`sbatch` header → `"slurm"`, `kubectl` → `"k8s"`, bare `python` → `"local"`, …).
   - `read_metrics`: command that — given `$JOB_ID` as an env var — prints `{"final_train_loss": float, "final_val_loss": float, ...}` JSON to stdout. Ask the user how the launcher persists final metrics and propose a reader. If unclear, offer to scaffold one.

3. **Experiment budget.** Ask for `max_steps` and/or `max_wall_time` (HH:MM:SS). At least one is required; no defaults — the user must set this (it's project-specific). This value is frozen after Phase 0.

4. **`torch.compile` cache.** Ask whether the project uses `torch.compile` (or equivalent). If yes, propose `~/.cache/torch_compile/<project_name>` as `compile_cache_dir`. If no, omit the field.

5. **Constraints.** Present the skill-default constraint list below, ask for additions or removals.

6. **Theme priorities.** Present the skill-default theme list below, ask the user to rank themes into `high`, `medium`, `low` buckets for `theme_priorities`.

7. **Prior findings.** Open-ended: "What have you tried manually on this project? What worked, what didn't?" Free-form bullets for `prior_findings`.

8. **`debug_cap`.** Default 3; ask if the user wants to override.

Before writing, present a draft `config.json` and ask for confirmation.

### Skill-default constraints

Seed these into `config.json`'s `constraints` list; user may add or remove:

```
- no change to random seed, validation dataset, validation logic, or validation metrics
- no change to the experiment budget defined in config.json (experiment_budget)
- parameter count must be <= baseline * 1.05
- no change to core dependencies / package versions
```

### Skill-default theme list

Present to user for ranking into `theme_priorities`:

```
optimizer, initialization, data_augmentation, architecture,
regularization, training_objective, tokenization, schedule
```

`training_objective` = training-loss composition (loss function, auxiliary losses, loss weighting). It is explicitly **not** the validation metric — the validation metric is frozen by constraint.

### Artifact initialization

After the user confirms `config.json`, create (using templates from `${CLAUDE_SKILL_DIR}/templates/` as starting points; if the worktree's `autoresearch/` directory doesn't have templates yet, copy them from `${CLAUDE_SKILL_DIR}/templates/`):

```
autoresearch/config.json              # written from dialog
autoresearch/ideas.md                 # empty with comment header
autoresearch/insights.md              # skeleton with empty section headings
autoresearch/results.csv              # header row only
autoresearch/experiments/.gitkeep    # dir preserved in git
```

### Initial commit

```bash
git add autoresearch/
git commit -m "Initialize autoresearch campaign: <project_name>"
```

### Phase 0 → Phase 1 handoff

Announce setup complete, then begin Phase 1 with a **baseline dispatch** (no Ideator call): experiment 001 = unmodified code. Dispatch Experimenter to run `launch_experiment` as-is, record metrics, write `experiments/001-baseline.md` with `result_status: accepted` (trivially). First CSV row written. Normal loop begins thereafter.

### Config.json freeze

`config.json` is frozen after Phase 0. The main agent re-reads it at every loop iteration (for recovery after compaction) but never modifies it. If a subagent return implies it wrote to `config.json`, reject the return as malformed.

If the user needs to change settings, the path is: complete or abandon the current campaign; start a new campaign with a different `project_name`.

## Phase 1: Loop body

```
loop forever:
    # 1. Small reads — all bounded files
    read config.json, ideas.md, insights.md, results.csv (full)
    scan experiments/ frontmatters (status fields only)

    # 2. Resumption / reconciliation — idempotent, every iteration
    for each experiment with job_status: pending:
        probe job state via env-appropriate skill (ml-research:slurm, etc.)
        if no job_id yet (mid-dispatch crash before launch):
            result = dispatch Experimenter(mode: fresh)
            post_experimenter(result)
        elif still running:
            result = dispatch Experimenter(mode: resume-monitoring)
            post_experimenter(result)
        elif terminated cleanly:
            result = dispatch Experimenter(mode: analyze-only)
            post_experimenter(result)
        elif terminated abnormally:
            overwrite experiment file: job_status: crashed, crash_reason in narrative
            commit on trunk
            continue
    # Orphan branches (experiment-named branch, no experiment file): log to
    # insights.md Open Questions, leave alone — user investigates.

    # 3. Periodic Reviewer
    if succeeded-count since last Reviewer >= 5:
        delta = dispatch Reviewer
        apply delta to insights.md on trunk, commit

    # 4. Idea selection
    if ideas.md has items:
        next_idea = pop top item from ideas.md, commit on trunk
    else:
        next_idea = dispatch Ideator   # always returns one idea (uses a low-confidence flag in rationale if stuck); the loop never blocks on idea exhaustion

    # 5. New experiment dispatch — stub-first ordering
    # NNN = highest existing experiment ID in experiments/*.md (parse from filename
    # prefix NNN-) + 1, zero-padded to 3 digits. If experiments/ is empty, NNN = 001.
    NNN = next experiment ID
    # Slug rule: lowercase the title; replace non-alphanumeric chars with `-`;
    # collapse consecutive `-`s; trim leading/trailing `-`; truncate to 40 chars max.
    slug = derive_slug(next_idea.title)
    write experiments/NNN-<slug>.md as a stub (frontmatter only):
        id: NNN, title, date, theme, sources from next_idea
        job_status: pending, result_status: null, attempts: 1
    commit stub on trunk
    git branch autoresearch/<campaign>/NNN-<slug>   # off trunk HEAD; main agent stays on trunk
    result = dispatch Experimenter(next_idea, branch, experiment_id=NNN, mode: fresh)
    post_experimenter(result)
```

The stub-first ordering ensures that if a crash interrupts the dispatch, step 2 finds the stub and reconciles on the next iteration.

### post_experimenter handler

```
def post_experimenter(result):
    # Main agent is on trunk throughout.
    overwrite experiments/<result.experiment_id>-<slug>.md
        (frontmatter from result + result.narrative_markdown as body)
    if result.job_status == "succeeded":
        append CSV row: result.experiment_id, result.branch, result.commit,
                        job_id, wandb_url, params, final_train_loss, final_val_loss
    commit on trunk
    if result.job_status == "succeeded" and result.result_status == "accepted":
        git merge --squash <result.branch>
        commit on trunk ("Merge experiment NNN: <title>")
    # rejected / inconclusive / crashed: branch preserved, no merge
    if result.follow_ups:
        optionally append to ideas.md (use judgment; avoid noise)
```

### Git choreography

| Actor | Branch | Writes |
|---|---|---|
| Main agent | trunk (`autoresearch/<campaign>`) | `ideas.md`, `insights.md`, `results.csv`, `experiments/*.md`, branch merges |
| Experimenter | experiment branch (`autoresearch/<campaign>/NNN-<slug>`) | code files matching `relevant_files.editable` only; never touches `autoresearch/*` |
| Ideator | none | no disk writes |
| Reviewer | none | no disk writes — returns delta; main agent applies |

**Branch lifecycle:**

1. Main agent: `git branch autoresearch/<campaign>/NNN-<slug>` — creates branch ref off trunk HEAD without checking it out.
2. Main agent dispatches Experimenter with `isolation: "worktree"`. Experimenter gets its own worktree on the branch; main agent's trunk worktree is untouched.
3. Experimenter commits code changes on its branch. Commits are visible from any worktree.
4. Experimenter returns. Its worktree is auto-cleaned.
5. Main agent writes experiment file + CSV row, commits on trunk.
6. If accepted: `git merge --squash autoresearch/<campaign>/NNN-<slug>` — code change lands on trunk. Branch preserved (audit trail).
7. If rejected / inconclusive / crashed: no merge; branch preserved.

Every experiment's code is preserved on its branch forever, regardless of outcome.

## Subagent dispatch patterns

### Common dispatch header

Every dispatch prompt begins with:

```
Campaign: <project_name>
Trunk: autoresearch/<project_name> @ <git SHA>
config.json: <embedded JSON, full>
insights.md: <embedded, full>
Results CSV: <embedded, full>
Current best: experiment <id>, final_val_loss <number>
```

"Current best" = lowest `final_val_loss` among experiments with `job_status: succeeded` and `result_status: accepted`. Compute from `results.csv` before dispatch. If no experiment has `result_status: accepted`, current best = the baseline (experiment 001) by definition.

### Subagent types

| Role | `subagent_type` |
|---|---|
| Ideator | `ml-research:autoresearch-ideator` |
| Experimenter | `ml-research:autoresearch-experimenter` |
| Reviewer | `ml-research:autoresearch-reviewer` |

Always pass `isolation: "worktree"` when dispatching the Experimenter.

### Experimenter-specific dispatch fields

```
Branch: autoresearch/<campaign>/NNN-<slug>
Experiment ID: NNN
Idea: <full idea object — title, theme, rationale, expected, sources, parent?>
Debug cap: <from config.json>
Environment hint: <entrypoints.launch_experiment.environment>
Mode: fresh | resume-monitoring | analyze-only
```

### Reviewer-specific dispatch fields

```
Recent experiments (last 5 succeeded): <list of experiment file paths>
```

The Reviewer reads those files itself; don't pre-embed them.

### Concrete dispatch example (Ideator)

Below is a complete Ideator dispatch prompt for a campaign called `lm-finetune` at its third iteration. Content blocks show the actual embedded format — not abstract placeholders.

```
Campaign: lm-finetune
Trunk: autoresearch/lm-finetune @ a3f8c21
config.json:
{
  "project_name": "lm-finetune",
  "training_objective": "minimize validation cross-entropy on held-out split",
  "experiment_budget": {"max_steps": 2000},
  "relevant_files": {
    "editable": ["src/model.py", "src/train.py"],
    "read_only": ["configs/base.yaml", "data/"]
  },
  "entrypoints": {
    "count_params": "python scripts/count_params.py",
    "launch_experiment": "bash scripts/launch.sh",
    "read_metrics": "python scripts/read_metrics.py"
  },
  "constraints": [
    "no change to random seed, validation dataset, validation logic, or validation metrics",
    "no change to the experiment budget defined in config.json",
    "parameter count must be <= baseline * 1.05",
    "no change to core dependencies / package versions"
  ],
  "theme_priorities": {"high": ["training_objective", "optimizer"], "medium": ["regularization"], "low": ["architecture"]},
  "prior_findings": ["label smoothing 0.1 hurt val loss by 0.03", "AdamW lr=3e-4 diverged at step 800"],
  "debug_cap": 3
}
insights.md:
## Patterns observed
- Warmup of 200 steps stabilizes early training across all accepted runs.

## Anti-patterns
- Learning rates above 1e-3 cause late-phase oscillation.

## Open questions
- Would cosine-with-restarts outperform linear decay?

## Closed directions
- (none yet)
Results CSV:
experiment_id,branch,commit,job_id,wandb_url,params,final_train_loss,final_val_loss
001,autoresearch/lm-finetune/001-baseline,a3f8c21,,,7421332,,2.847
002,autoresearch/lm-finetune/002-focal-loss,b19d043,,,7421332,,2.801
Current best: experiment 002, final_val_loss 2.801

--- IDEATOR TASK ---
Propose one new experiment idea. Return a single idea object with fields:
title, theme, rationale, expected, sources (non-empty list of citation keys or URLs).
```

### Return validation

After each dispatch, validate the return against its contract:

- **Ideator:** `sources` must be non-empty. Reject if `sources: []`.
- **Experimenter:** must have valid `job_status` (`succeeded`|`crashed`). If `succeeded`, must have `result_status` and `metrics.final_val_loss`.
- **Reviewer:** the return must be an object with optional keys `insights_added`, `insights_updated`, `insights_removed`, `strategic_note`. The first three are arrays of `{section, text}` (for added/removed) or `{section, old_text, new_text}` (for updated) objects. `section` must be one of: `Patterns observed`, `Anti-patterns`, `Open questions`, `Closed directions`. `strategic_note` is an optional string.

On malformed return: re-dispatch once with the prefix "Your prior return was malformed: <reason>. Please return per the contract." If it fails twice, log to `insights.md` Open Questions and proceed.

## Acceptance criteria

The Experimenter recommends `result_status` based on val loss vs. **current best** (not baseline). Main agent rubber-stamps the recommendation:

| Val-loss delta vs. current best | Recommendation |
|---|---|
| improvement > 1% (new < best × 0.99) | `accepted` — if training was stable |
| 0–1% improvement | `inconclusive` — log; may revisit |
| no improvement or regression | `rejected` |

Stability gate: even if val loss improves, training must show no divergence, no late-phase oscillation, no NaN/inf. Gate failure → `rejected`.

## Retry policy

Once the Experimenter returns `job_status: crashed` (debug_cap exhausted), that status is sticky. Main agent does **not** auto-retry. The user can manually prompt "retry experiment NNN" to force a fresh Experimenter dispatch on that branch. Otherwise the experiment stays crashed and the Ideator treats it as "tried, didn't work" when avoiding duplicates.

## Autonomy principle

The main agent prompts the user **only** during Phase 0 setup, when the user explicitly addresses the agent, or when a genuinely unresolvable blocker surfaces (e.g., `config.json` references a missing entrypoint). Every crashed job, failed experiment, and exhausted idea queue is handled autonomously — mark, log, move on. A persistent blocker is logged to `insights.md` Open Questions; the agent dispatches a different experiment rather than blocking.

## What the main agent must NOT do

- **Implement code changes** — dispatch Experimenter.
- **Generate ideas** — dispatch Ideator.
- **Synthesize insights** — dispatch Reviewer.
- **Stream `launch_experiment` stdout/stderr into context** — metrics flow only through `read_metrics`, and that runs inside the Experimenter dispatch.
- **Edit `config.json` after Phase 0** — it is frozen.
- **Auto-rebase the campaign trunk onto `main`** — that is a human decision.
- **Read experiment narrative bodies in bulk** — scan frontmatters only; body reads are the subagents' job.
