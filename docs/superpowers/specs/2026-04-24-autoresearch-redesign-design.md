# Autoresearch skill — ground-up redesign

Date: 2026-04-24
Status: spec approved, plan not yet written

## Motivation

The current `ml-research:autoresearch` skill iterates on an ML model through rapid small-scale experiments. It works, but the architecture has three latent problems as a campaign accumulates experiments:

1. **Context rot.** Everything — ideas, narrative log, structured metrics — is in a handful of markdown/CSV files that get loaded whole at every turn. After dozens of experiments, the log alone exceeds useful context.
2. **Weak auditability at granularity.** A single unbounded `autoresearch_log.md` commingles many experiments' narratives; searching for one requires loading the whole file.
3. **No use of Claude-native context-management primitives.** The design predates the design norms behind progressive disclosure, subagent delegation, auto-memory, and structured tool notifications.

This redesign targets those three, under the constraints:

- **Runs inside Claude Code** (a skill, not a standalone SDK harness). Uses Claude Code-native primitives: the `Agent` tool (subagents), `TaskCreate`/`TaskList`, `Monitor`, `WebSearch`, the auto-memory directory, and the harness's built-in compaction.
- **Auditability via trunk-based development.** Every experiment's code is preserved on its own git branch forever; accepted experiments squash-merge onto the campaign trunk.
- **Fully autonomous after Phase 0.** Only user interaction is at one-time setup and when the user explicitly addresses the agent. Every transient infra failure, ambiguous result, and exhausted idea queue is handled by the agent itself.
- **Multi-campaign isolation.** Multiple autoresearch loops can run in parallel per project (different models, different config profiles) without state collision.

## Architecture

Three actors operate against a per-campaign state store:

```
Main agent (ml-research:autoresearch skill, thin orchestrator)
    │
    ├─── dispatches ──► Ideator subagent     (one idea with citations)
    ├─── dispatches ──► Experimenter subagent (one experiment end-to-end)
    └─── dispatches ──► Reviewer subagent     (periodic insights synthesis)

Per-campaign state store (git-tracked worktree):
    ../autoresearch-<project_name>/
    └── autoresearch/
        ├── config.json         # user-authoritative
        ├── ideas.md            # user-input buffer (FIFO)
        ├── insights.md         # synthesized cross-experiment patterns
        ├── results.csv         # structured metrics, one row/experiment
        └── experiments/
            ├── 001-baseline.md
            └── NNN-<slug>.md   # frontmatter + narrative
```

### Division of responsibility

| Actor | Scope | Reads | Writes |
|---|---|---|---|
| **Main agent** | Phase 0 setup (interactive); Phase 1 loop dispatch; git operations | `config.json`, `ideas.md`, `insights.md`, `results.csv`, experiment file frontmatters (scan-only) | Trunk: tracking files, experiment files, CSV rows, branch merges |
| **Ideator** | Generate exactly one experiment idea with citations | Same as main agent + JIT-read of past experiment files and code, WebSearch | Nothing to disk; returns structured object |
| **Experimenter** | Implement + launch + monitor + analyze one experiment, with internal debug loop | Same + `relevant_files` reads | Experiment branch only; code files matching `relevant_files.editable` |
| **Reviewer** | Synthesize insights from last 5 succeeded experiments | Recent experiment files, `insights.md`, CSV | Nothing to disk; returns structured insights delta |

### Context management strategy

Progressive disclosure is the core principle:

- **Main agent context stays flat** across campaign lifetime. Reads ≤10 KB of small, bounded tracking files per iteration. Never reads experiment narratives in bulk. Never holds subagent tool-call noise.
- **Subagent contexts die on return.** Each subagent performs whatever deep reading/tool use it needs, condenses to its structured return, and evaporates. The main agent sees only the return.
- **`insights.md` is the auto-synthesized long-term memory** (produced by Reviewer), bounded to ~50 lines. It acts as the main agent's compressed knowledge of the campaign.

The auto-memory directory (`~/.claude/projects/<proj>/memory/`) stays reserved for genuine cross-session/cross-campaign user+project context — it is *not* used for campaign-scoped research artifacts, since per-project memory would pollute every non-autoresearch session with campaign-specific files.

## Data model

### `autoresearch/config.json`

User-authoritative, written once at Phase 0 setup, read by the main agent at every iteration. Strict schema (JSON, no comments):

```json
{
  "project_name": "my-project",
  "relevant_files": {
    "read_only": ["config/conf.yaml", "src/data/**/*.py"],
    "editable":  ["src/models/**/*.py", "src/losses/*.py"]
  },
  "entrypoints": {
    "count_params":      { "command": "uv run python scripts/count_params.py" },
    "launch_experiment": {
      "command": "scripts/launch.sh",
      "environment": "slurm"
    },
    "read_metrics":      { "command": "scripts/read_metrics.sh" }
  },
  "experiment_budget": {
    "max_steps": 1000,
    "max_wall_time": "00:30:00"
  },
  "compile_cache_dir": "~/.cache/torch_compile/<project_name>",
  "debug_cap": 3,
  "constraints": [
    "no change to random seed, validation dataset, validation logic, or validation metrics",
    "no change to the experiment budget defined in config.json (experiment_budget)",
    "parameter count must be <= baseline * 1.05",
    "no change to core dependencies / package versions"
  ],
  "theme_priorities": {
    "high":   ["data_augmentation", "training_objective"],
    "medium": ["architecture"],
    "low":    ["optimizer"]
  },
  "prior_findings": [
    "LR sweep: 3e-4 > 1e-4",
    "Dropout didn't help",
    "Cosine > constant"
  ]
}
```

Notes on semantics:

- **`relevant_files`** is a hard safety rail for Experimenter. Shell-style globs (`**`, `*`, `?`). Subagents may *edit existing files or create new files* at paths matching `editable`; they may *read* files matching `read_only`; files outside both lists are implicitly off-limits to both reads and writes (other than the standard project-orientation reads like `pyproject.toml` or `README.md`). The constraint is about which paths can be touched, not whether the files preexist.
- **`entrypoints`** — pluggable user-provided commands. All contracts are documented in SKILL.md (not duplicated per-campaign):
    - `count_params.command` must print JSON with keys `trainable_params`, `total_params` to stdout.
    - `launch_experiment.command` must submit a job, print its job ID to stdout, and accept training overrides as positional args. **It must also write final-metrics output that `read_metrics.command` can return.** No agent ever streams stdout/stderr from `launch_experiment.command` into its context — the only path from job to context is via `read_metrics`.
    - `read_metrics.command` is invoked after the job completes (with `JOB_ID` as an env var) and must print JSON to stdout containing at minimum `{"final_train_loss": float, "final_val_loss": float}`. Other metrics keys (e.g. best-val-loss, GPU utilization) are allowed and surfaced into the experiment file. Implementations: read a metrics file the launcher wrote, query a tracking service (W&B, MLflow), or grep a structured log line.
- **`environment`** is a free-form hint string (`"slurm"`, `"local"`, `"k8s"`, `"ray"`, …) that tells the Experimenter which env-specific skill (if any) to invoke for monitoring.
- **`experiment_budget`** caps each experiment's compute. At least one of `max_steps` or `max_wall_time` (HH:MM:SS) must be set. The `launch_experiment` entrypoint is responsible for honoring these; the Experimenter passes them as overrides if the launcher accepts them, and otherwise relies on the launcher's own defaults. Frozen by constraint after Phase 0 — changing the budget mid-campaign would break experiment comparability.
- **`compile_cache_dir`** (optional). If set, the Experimenter exports `TORCHINDUCTOR_CACHE_DIR` (or the equivalent env var for the user's compile backend) when launching a job. The cache is shared across experiments for speed; the Experimenter wipes it before launching when `theme: architecture` (architecture changes invalidate compiled kernels). Omit this field if the project doesn't use `torch.compile`.
- **`debug_cap`** caps the Experimenter's internal retry loop. Default 3. Counts total attempts including the first launch.
- **`constraints`** is a flat list of free-text rules. Phase 0 seeds skill-default constraints; user can add/remove.
- **`theme_priorities`** ranks themes. Skill-default theme list: `optimizer, initialization, data_augmentation, architecture, regularization, training_objective, tokenization, schedule`. The `training_objective` theme refers to the *training* loss / objective function; the validation metric is frozen by constraint and can never be a theme target.

### `autoresearch/experiments/NNN-<slug>.md`

One file per experiment. Frontmatter (required) + free-form markdown body (Experimenter-authored):

```yaml
---
id: 42
title: GELU in FFN
date: 2026-04-24
job_status: pending          # pending | succeeded | crashed
result_status: null          # null | accepted | rejected | inconclusive
theme: architecture
tags: [activation, ffn]
attempts: 1
parent: 37                   # optional — experiment ID this builds on
sources:                     # from the originating Ideator idea
  - url: https://arxiv.org/abs/2301.12345
    note: proposes GELU-like activation
  - ref: insights.md#activations-underexplored
    note: from insight synthesis
---

## Change
<what was modified and why>

## Training dynamics
<convergence, stability, anomalies — per-attempt if multiple>

## Analysis
<why it worked/didn't; insights for future>

## Complexity
<lines changed; conceptual complexity; worth the improvement?>

## Attempts log
- attempt 1 (job 12345): OOM on batch 300 — retry with reduced batch
- attempt 2 (job 12346): completed, final val loss 2.41
```

The "Attempts log" section appears only when `attempts > 1`.

**Two-axis status:**

- `job_status ∈ {pending, succeeded, crashed}` — did the job run to completion?
- `result_status ∈ {null, accepted, rejected, inconclusive}` — is the measured outcome worth merging?

Orthogonality rule: `result_status` is non-null only when `job_status: succeeded`. A crashed experiment never gets a result evaluation.

### `autoresearch/results.csv`

Structured-only (no freeform text, no duplication with frontmatter):

```
experiment_id,branch,commit,job_id,wandb_url,trainable_params,total_params,final_train_loss,final_val_loss
```

One row per `job_status: succeeded` experiment. Crashed experiments get no CSV row — their identity is preserved in the experiment file + git branch.

### `autoresearch/ideas.md`

**User-input buffer only** (not a Claude-maintained queue). Usually empty. The user adds ideas when they want to bias the next experiment. Main agent processes FIFO (top-to-bottom), removing an idea section when it's picked.

```markdown
# User-suggested ideas (FIFO)

## Try grad-norm clipping
- theme: optimizer
- rationale: hunch, not yet swept
```

### `autoresearch/insights.md`

Reviewer-maintained synthesis. No hard size bound — the Reviewer is responsible for keeping it useful (consolidating, pruning stale entries, removing redundancy). Structured into named sections so insights can be referenced by anchor in idea citations.

```markdown
# Insights

## Patterns observed
- LR warmup is necessary for attention-variant experiments; without it, 3/3 diverged (exp 014, 019, 021).
- Data augmentation at strength > 0.4 consistently hurt val loss on this dataset (exp 008, 011, 028).

## Anti-patterns
- Dropout on FFN layers: neutral to slightly negative (exp 004, 017).

## Open questions
- LR-schedule × grad-clipping interaction — exp 009 suggested yes, exp 022 inconclusive.

## Closed directions
- Mixture-of-experts: out-of-scope per constraints.
- Recomputation-only tricks: deprioritized per constraints.
```

### Reading cost at main-agent loop start

At worst, all five files combined:

| File | Typical size |
|---|---|
| `config.json` | ~2 KB |
| `ideas.md` | 0–1.5 KB |
| `insights.md` | small to start; Reviewer prunes — should stay manageable in practice |
| `results.csv` | ~150 B × N (tiny even at N=500) |
| Experiment frontmatters (scan) | ~500 B × N pending/crashed only |

Main agent context remains well under 10 KB of state per iteration, flat across campaign lifetime.

## Phase 0: Setup

Runs once per campaign, interactive with the user.

### Invocation

```
/ml-research:autoresearch <campaign-name>   # activate/create named campaign
/ml-research:autoresearch                   # resume if cwd is inside a worktree, else prompt for name
```

The `<campaign-name>` argument is the same string as the `project_name` field in `config.json`. The two are used interchangeably in this spec — invocation arg, worktree directory suffix, trunk branch suffix, and config field all share the value.

### Decision flow

```
if worktree ../autoresearch-<name>/ doesn't exist:
    git worktree add ../autoresearch-<name> -b autoresearch/<name>    # trunk off current HEAD
cd ../autoresearch-<name>
if autoresearch/config.json exists:
    → Phase 1 (resume)
else:
    run setup dialog
    → Phase 1
```

### Setup dialog

The main agent does a lightweight codebase scan first (a few `ls`, read `pyproject.toml`/`package.json`/`README.md`, grep for common entrypoint scripts), then walks the user through sections. Each section leads with auto-detected defaults; user confirms or edits. No subagents; all interaction is between main agent and user.

**Question sequence:**

1. **Relevant files.** Heuristics: `src/**/model*.py`, `src/**/net*.py`, files importing torch.nn/flax.linen → proposed `editable`. `config/*.yaml`, `**/data*.py`, `scripts/**` → proposed `read_only`. Present proposal, take edits.

2. **Entrypoints.**
    - `count_params`: Detect `scripts/count_params.py` or `tools/count_params.py`. If not found, offer to scaffold one from `templates/examples/count_params_lightning.py`.
    - `launch_experiment`: Detect `scripts/launch.sh`, `scripts/*.sbatch`, Makefile targets. Infer `environment` from script contents (sbatch header → `slurm`, `kubectl` → `k8s`, bare `python` → `local`, …). Present and take edits.
    - `read_metrics`: Ask the user how the launcher persists final metrics, and propose a one-line command that returns them as JSON. Common patterns: `cat $JOB_DIR/metrics.json`, a wandb-API query, or a `grep`+`jq` over a structured log line. If unclear, offer to scaffold a small reader script.

3. **Experiment budget.** Ask for `max_steps` and/or `max_wall_time` (at least one required). Defaults: none — must be user-set, since "what is a small experiment" is project-specific.

4. **`torch.compile` cache.** Ask whether the project uses `torch.compile` (or equivalent). If yes, propose a default `compile_cache_dir` under `~/.cache/torch_compile/<project_name>`. If no, omit the field.

5. **Constraints.** Present skill-default constraints (see below), ask for additions/removals.

6. **Theme priorities.** Present skill-default theme list, ask user to rank into high/medium/low buckets.

7. **Prior findings.** Open-ended: "What have you tried manually on this project? What worked, what didn't? Anything to bias ideation for or against?" Free-form bullet strings.

8. **`debug_cap`.** Default 3; ask if user wants to override.

Before writing, main agent presents a draft `config.json` and asks for confirmation.

### Skill-default constraints (seeded into `constraints` list)

```
- no change to random seed, validation dataset, validation logic, or validation metrics
- no change to the experiment budget defined in config.json (experiment_budget)
- parameter count must be <= baseline * 1.05
- no change to core dependencies / package versions
```

(The "no change to experiment budget" constraint is a hard rule; the budget is set once at Phase 0 and cannot be edited later — see "Config.json freeze" below.)

### Skill-default theme list

```
optimizer, initialization, data_augmentation, architecture,
regularization, training_objective, tokenization, schedule
```

`training_objective` = training-loss composition (loss function, auxiliary losses, loss weighting). Explicitly *not* the validation metric — that's frozen by constraint.

### Artifact initialization

After config confirmation, main agent creates:

```
autoresearch/config.json              # written
autoresearch/ideas.md                 # empty with comment header
autoresearch/insights.md              # skeleton with empty Patterns/Anti-patterns/Open-questions/Closed-directions sections
autoresearch/results.csv              # header row only
autoresearch/experiments/.gitkeep     # dir preserved in git
```

### Initial commit

```
git add autoresearch/
git commit -m "Initialize autoresearch campaign: <project_name>"
```

### Phase 0 → Phase 1 handoff

Main agent announces setup complete and begins Phase 1 with a **baseline dispatch** (no Ideator call): experiment 001 = unmodified code. Experimenter runs the `launch_experiment` entrypoint as-is, records metrics, writes `experiments/001-baseline.md` with `result_status: accepted` (trivially). First CSV row written. Normal loop begins thereafter.

### Config.json freeze

**`config.json` is frozen after Phase 0.** Once initialized and committed, it is not edited — not by the main agent, not by subagents, not by the user mid-campaign.

The reason: changing constraints, themes, entrypoints, or `experiment_budget` mid-campaign would compromise experiment comparability. Two experiments run under different `experiment_budget` values aren't comparable on val loss; two experiments evaluated under different `constraints` may conflict on what counts as acceptable. The campaign is a controlled study; `config.json` is the protocol.

If the user genuinely needs to change settings, the path is: complete or abandon the current campaign, start a new campaign with a different `project_name`. Multiple campaigns can coexist in the same project (per the multi-campaign isolation property).

The main agent re-reads `config.json` at every iteration to recover its working knowledge after compaction, but it does not modify the file. If a subagent ever attempts to write to `config.json`, the main agent rejects the resulting return as malformed.

## Phase 1: Loop body

Runs forever after Phase 0. Main agent's per-iteration script:

```
loop forever:
    # 1. Small reads — full files; all bounded for the campaign's lifetime
    read config.json, ideas.md, insights.md, results.csv (full)
    scan experiments/ frontmatters (status fields only)

    # 2. Resumption / reconciliation — idempotent, runs every iteration
    for each experiment with job_status: pending:
        probe job state via env-appropriate skill (ml-research:slurm, etc.)
        if no job_id recorded yet (mid-dispatch crash before launch):
            # Stub exists, branch may or may not, Experimenter never started
            # Re-dispatch fresh (Experimenter idempotently re-uses existing branch)
            result = dispatch Experimenter in fresh mode
            post_experimenter(result)
        elif still running:
            result = dispatch Experimenter in resume-monitoring mode
            post_experimenter(result)
        elif terminated cleanly:
            result = dispatch Experimenter in analyze-only mode
            post_experimenter(result)
        elif terminated abnormally:
            update experiment file: job_status: crashed + crash_reason in narrative
            commit on trunk
            continue
    # Also: detect orphan experiment-named branches with no experiment file (shouldn't
    # happen given the stub-first ordering below, but if it does, log to insights.md
    # and leave alone — user can investigate)

    # 3. Periodic maintenance
    if succeeded-count since last Reviewer >= 5:
        delta = dispatch Reviewer
        apply insights delta to insights.md on trunk, commit

    # 4. Idea selection
    if ideas.md has items:
        next_idea = pop top item from ideas.md, commit on trunk
    else:
        next_idea = dispatch Ideator   # returns one idea with citations

    # 5. New experiment dispatch
    NNN = next experiment ID (auto-increment from experiments/ dir)
    slug = derive_slug(next_idea.title)
    # Stub-first ordering: create the experiment-file marker BEFORE the branch and
    # BEFORE the dispatch. If anything below crashes mid-flight, resumption (step 2)
    # finds the stub and reconciles.
    write experiments/NNN-<slug>.md as a stub (frontmatter only):
        id: NNN, title, date, theme, sources from next_idea,
        job_status: pending, result_status: null, attempts: 1
    commit stub on trunk
    git branch autoresearch/<campaign>/NNN-<slug>     # branch ref created off trunk; main agent stays on trunk
    result = dispatch Experimenter with next_idea + branch name + experiment_id=NNN
        # Experimenter operates on the branch (recommended: isolation: "worktree" so it
        # gets its own worktree on the branch and main agent's trunk worktree is untouched)
        # Experimenter runs its internal debug loop up to debug_cap
        # returns structured summary + narrative text
    post_experimenter(result)


# Single post-Experimenter handler, invoked after every dispatch (resumption or new):
def post_experimenter(result):
    # Main agent is on trunk throughout this handler.
    # The stub experiment file already exists (written before dispatch); this overwrites it.
    overwrite experiments/<result.experiment_id>-<slug>.md
        (frontmatter from result + result.narrative_markdown as body)
    if result.job_status == "succeeded":
        append CSV row from result.metrics, result.experiment_id, result.branch, result.commit
    commit on trunk
    if result.job_status == "succeeded" and result.result_status == "accepted":
        git merge --squash <result.branch>
        commit on trunk
    # rejected / inconclusive / crashed: branch preserved as-is, no merge
```

### Git choreography

| Actor | Branch | Writes |
|---|---|---|
| Main agent | trunk (`autoresearch/<campaign>`) | `config.json` (rarely), `ideas.md`, `insights.md`, `results.csv`, `experiments/*.md`, branch merges |
| Experimenter | experiment branch (`autoresearch/<campaign>/NNN-<slug>`) | code files only (matching `relevant_files.editable`). Does NOT touch `autoresearch/*` tracking files. |
| Ideator | none | no disk writes |
| Reviewer | none | no disk writes — returns delta; main agent applies |

**Experiment branch lifecycle:**

1. Main agent (on trunk): `git branch autoresearch/<campaign>/NNN-<slug>` — creates the branch ref off trunk HEAD without checking it out. Main agent's working tree stays on trunk.
2. Main agent dispatches Experimenter with `isolation: "worktree"` (recommended) or equivalent, passing the branch name. Experimenter gets its own worktree on the branch; main agent's trunk worktree is untouched.
3. Experimenter commits code changes in its isolated worktree. Commits land on the branch in the shared `.git` repo, visible from any worktree.
4. Experimenter returns its result. The isolated worktree is auto-cleaned (per Agent-tool semantics).
5. Main agent (still on trunk) writes experiment file + CSV row, commits on trunk.
6. If accepted: `git merge --squash autoresearch/<campaign>/NNN-<slug>` from trunk brings the code change onto trunk. Branch is preserved (not deleted — audit trail).
7. If rejected / inconclusive / crashed: branch preserved as-is, no merge. Trunk has the experiment file and CSV row; trunk does NOT have the code change.

If `isolation: "worktree"` is not used (e.g., the harness doesn't support it for some reason), the fallback is for the main agent to `git checkout <branch>` before dispatching and `git checkout <trunk>` after the dispatch returns. This works but is fragile across crashes (a mid-dispatch interruption leaves the main agent's working tree on the experiment branch). Worktree isolation is strongly preferred.

Every experiment's code is preserved on its branch forever, regardless of outcome. Auditability requirement met in full.

### Acceptance criteria

The Experimenter recommends `result_status` based on the experiment's val loss compared to the **current best** — not the original baseline (experiment 001). "Current best" = the lowest `final_val_loss` among all experiments with `job_status: succeeded` and `result_status: accepted`. The main agent provides this number in the Experimenter's input contract so the Experimenter doesn't need to recompute it.

Recommendation rules (Experimenter applies; main agent rubber-stamps):

| Val-loss delta vs. current best | Recommendation |
|---|---|
| improvement > 1% (i.e., new < best * 0.99) | `accepted` (provided training was stable; see below) |
| 0–1% improvement | `inconclusive` (log; may revisit later, possibly combined with other changes) |
| no improvement or regression | `rejected` |

Stability gate (applied even when val-loss improves): training must show no divergence, no oscillation past the early phase, and no NaN/inf. If the gate fails, the recommendation drops to `rejected` regardless of val-loss improvement.

Complexity check: `acceptance_recommendation` should also weigh added complexity against the magnitude of improvement. The Experimenter's `reasoning_short` records this judgment.

### Monitor usage

The Experimenter uses `Monitor` inside its dispatch to stream job-state transitions (one notification per terminal state, not per-poll). The main agent does not use `Monitor` against the Experimenter dispatch itself, for two reasons:

1. **`Monitor` watches a script's stdout; subagent dispatches via the `Agent` tool don't expose stdout in that form.** The `Agent` tool returns one final message (sync) or one completion notification (with `run_in_background: true`) — neither is a stream. So Monitor isn't a fit for Experimenter dispatches even mechanically.
2. **The main agent has no in-flight work to do during an Experimenter dispatch under the current design** (serial loop). Pipelining the next Ideator call against an in-flight Experimenter is plausible future work but is explicitly out of scope here.

So the dispatch model stays: **main agent dispatches Experimenter synchronously and awaits the structured return.** The Experimenter is internally responsible for streaming progress (via Monitor on the underlying job) and condensing it to its return.

### Retry policy

Once the Experimenter exits with `job_status: crashed` (debug-cap exhausted), the status is sticky. Main agent does **not** auto-retry. The user can manually prompt "retry experiment 042" to force a new Experimenter dispatch on that branch; otherwise it stays crashed, and the Ideator treats it as "tried, didn't work" when avoiding duplicates.

### Autonomy principle

Main agent prompts the user only during Phase 0 setup, when responding to user-initiated prompts (charter edit requests, explicit "retry experiment X"), or when a genuinely unresolvable blocker surfaces (e.g., config.json references a missing entrypoint). Every crashed job, failed experiment, and exhausted queue is handled by the agent itself (mark, retry-if-allowed, dispatch Reviewer, loop forward). A persistent blocker gets logged to `insights.md` and the agent moves on to a different experiment rather than hanging.

## Subagents

### Definitions

Three agent types in the plugin:

```
plugins/ml-research/agents/
├── autoresearch-ideator.md
├── autoresearch-experimenter.md
└── autoresearch-reviewer.md
```

Each has frontmatter (`name`, `description`, `tools` allowlist, default `model` and `effort`) plus a detailed system prompt. Main agent dispatches via the `Agent` tool with `subagent_type: "ml-research:autoresearch-<role>"` and an optional `model` override.

### Default model + effort per subagent

| Subagent | Default model | Default effort | Reasoning |
|---|---|---|---|
| Ideator | Opus 4.7 | medium | Idea quality is high-leverage and infrequent (one call per loop iteration when the user queue is empty). The cost of a bad idea is a wasted experiment (substantial GPU time); spending Opus tokens to pick well pays for itself easily. |
| Experimenter | Sonnet 4.6 | medium | Bulk of token generation is mechanical (file edits, command running, log reading). Sonnet is more than adequate at the implementation level. The debug loop's diagnoses use the same model — Sonnet handles standard crash patterns well. |
| Reviewer | Opus 4.7 | medium | Cross-experiment synthesis is high-leverage and infrequent (every 5 succeeded experiments). Opus is better at finding patterns vs. just restating individual experiment summaries. |

These are defaults in each agent's frontmatter; the main agent can override per dispatch (e.g., promote Experimenter to Opus for an unusually tricky implementation). User can also override at the plugin level.

### Tool allowlists

| Subagent | Tools |
|---|---|
| Ideator | `WebSearch, WebFetch, Read, Grep, Bash (read-only)` |
| Experimenter | `Bash, Read, Edit, Write, Grep, Monitor, Skill (ml-research:slurm, ml-research:model-training, and any env-specific helper)` |
| Reviewer | `Read, Grep, Bash (read-only)` |

Read-only-ness for Ideator and Reviewer is enforced by omitting Edit/Write. They return structured output; the main agent applies changes to disk.

### Input contract (common dispatch header)

Every dispatch prompt includes:

```
Campaign: <project_name>
Trunk: autoresearch/<project_name> @ <git SHA>
config.json: <embedded JSON, full>
insights.md: <embedded, full>
Results CSV: <embedded, full — typically tens of rows, each ~150 B>
Current best: experiment <id>, final_val_loss <number>
```

Plus a role-specific section (details in "Output contracts" below).

### Output contracts

**Ideator returns** a single JSON object:

```json
{
  "title": "GELU in FFN",
  "theme": "architecture",
  "rationale": "1-3 sentences",
  "expected": "1-2 sentences",
  "sources": [
    {"url": "https://arxiv.org/abs/2301.12345", "note": "..."},
    {"ref": "insights.md#activations-underexplored", "note": "..."}
  ],
  "parent": 37
}
```

**Sources requirements (system-prompt-enforced; main agent rejects malformed returns):**

1. **At least one source required.** Non-negotiable — empty `sources: []` triggers rejection.
2. **Strongly encouraged: an official reference implementation.** Author's codebase, library's canonical, paper's companion repo.
3. **Otherwise encouraged: a reputable reference implementation** (HuggingFace, nanoGPT, fairseq, etc.).
4. **Fallback: paper or authoritative blog post.** Acceptable when no reference implementation exists publicly. Ideator must flag this in `rationale`: "no reference implementation available; Experimenter will implement from paper description."

Internal references (`ref:` to prior experiments or `insights.md` anchors) are valid sources and count toward the "at least one" requirement alone — typical for ideas that are variations on already-explored ground.

Source quality is a ranking dimension: between two ideas of comparable expected impact, the Ideator returns the one with stronger reference-implementation grounding.

**Curated starter source list** — the Ideator's system prompt includes a curated list of sites to consult first when looking for techniques. Recommended starting set (edit per project domain in the agent file):

- arxiv (cs.LG, cs.CL, cs.CV — theme/domain dependent)
- paperswithcode.com — for paper → reference-impl crosswalk
- HuggingFace docs and model repos
- Major reference codebases for the model family (e.g., nanoGPT, fairseq, jax-models, levanter)
- distill.pub, lilianweng.github.io, sebastianraschka.com — for high-quality digest articles
- Recent NeurIPS / ICML / ICLR proceedings

The Ideator is expected to consult these *before* speculating from first principles. Web search calls land in the Ideator's context, not the main agent's.

**Experimenter returns** (success path):

```json
{
  "experiment_id": 42,
  "branch": "autoresearch/my-project/042-gelu-ffn",
  "commit": "abc123",
  "job_status": "succeeded",
  "result_status": "accepted",
  "attempts": 1,
  "job_ids": ["12345"],
  "metrics": {
    "trainable_params": 1234567,
    "total_params": 1234567,
    "final_train_loss": 2.31,
    "final_val_loss": 2.41
  },
  "acceptance_recommendation": "accept",
  "reasoning_short": "3% val loss improvement over current best (exp 037), stable training, no added complexity",
  "follow_ups": [
    "Try combining with warmup schedule (insight #2 suggests interaction)"
  ],
  "narrative_markdown": "## Change\n...\n## Training dynamics\n...\n## Analysis\n..."
}
```

`narrative_markdown` is the full body written to `experiments/NNN-<slug>.md` by the main agent. `follow_ups` is free-text candidate ideas — the main agent may append to `ideas.md` or ignore.

**Experimenter returns** (crash path, debug-cap exhausted):

```json
{
  "experiment_id": 42,
  "branch": "autoresearch/my-project/042-gelu-ffn",
  "commit": "abc123",
  "job_status": "crashed",
  "result_status": null,
  "attempts": 3,
  "job_ids": ["12345", "12346", "12347"],
  "crash_reasons": ["OOM", "NaN loss", "NaN loss"],
  "narrative_markdown": "## Change\n...\n## Attempts log\n- attempt 1 (job 12345): OOM...\n- attempt 2: ..."
}
```

**Reviewer returns** an insights delta:

```json
{
  "insights_added": [
    {"section": "Patterns observed", "text": "..."}
  ],
  "insights_updated": [
    {"section": "Anti-patterns", "old_text": "...", "new_text": "..."}
  ],
  "insights_removed": [
    {"section": "Open questions", "text": "..."}
  ],
  "strategic_note": "Attention-variant directions have yielded 0/4 accepted; suggest deprioritizing."
}
```

Main agent applies the delta to `insights.md` on trunk and commits. `strategic_note` is informational — surfaced to the user on next prompt, not auto-applied.

### Experimenter's internal debug loop

```
attempt = 1
while attempt <= debug_cap:
    if attempt == 1:
        implement the change on the branch, commit
    else:
        apply diagnosed fix, commit
    run count_params entrypoint, verify param budget (<= baseline * 1.05)
    if compile_cache_dir is set and theme == "architecture":
        wipe compile_cache_dir before launch (architecture changes invalidate compiled kernels)
    run launch_experiment entrypoint, get job_id
        (export TORCHINDUCTOR_CACHE_DIR=compile_cache_dir if set)
    monitor job to terminal state via env-appropriate skill
    while job runs: poll nvidia-smi periodically; record GPU utilization
    if job succeeded:
        run read_metrics entrypoint, get metrics JSON
        analyze metrics, GPU utilization, training curves
        return success summary + narrative
    else:  # job crashed
        diagnose from logs (OOM, NaN, python error, node fail, timeout, unknown)
        append to "Attempts log" in narrative
        if fixable and attempt < debug_cap:
            attempt += 1
            continue
        else:
            return crash summary
```

**Diagnosis → fix table:**

| Diagnosis | Fix | Fixable? |
|---|---|---|
| OOM | Reduce batch size, increase grad accumulation | yes |
| NaN / inf loss | Add gradient clipping, lower LR, add warmup | yes |
| Python exception / traceback | Read traceback, patch the code change | yes |
| Timeout (exceeded wall clock) | Usually not fixable within debug budget | no |
| Node failure / preemption | Resubmit unchanged (infra issue) | yes (cheap) |
| Unknown / unparseable logs | Give up | no |

### GPU utilization

The Experimenter polls `nvidia-smi` (or the env-appropriate equivalent) periodically while the job runs and records peak/mean GPU utilization. The narrative includes this in the "Training dynamics" section.

If utilization is materially low on a *successful* run (e.g., < 70% mean), the Experimenter's analysis flags it as a potential issue and the `follow_ups` field includes "consider larger batch size to improve MFU" or similar. Low utilization does not by itself trigger a retry on a successful run — the result still counts. It does inform the next experiment's choices.

If utilization is low on a *crashed* run that the Experimenter is otherwise about to retry (e.g., crash was OOM), the fix-and-retry naturally improves utilization (larger effective batch, fewer accumulation micro-steps).

### `torch.compile` cache reuse

If `compile_cache_dir` is set in `config.json`, the Experimenter exports `TORCHINDUCTOR_CACHE_DIR` (or the appropriate env var for the user's compile backend) when launching, pointing at that directory. The cache is shared across experiments to amortize compilation overhead.

**Invalidation rule:** when the experiment's theme is `architecture`, the Experimenter wipes the cache before launching the job (`rm -rf $compile_cache_dir/*`). Architecture changes can invalidate compiled kernels in subtle ways; safer to recompile from scratch.

For other themes (optimizer, augmentation, loss, etc.), the cache is reused as-is. This typically saves 1–10 minutes of compile time per experiment for non-trivial models.

### Proxy-task discipline

The autoresearch loop runs *small* experiments (short steps, single GPU, often a fraction of full training data) as **proxies** for full-scale runs. The real goal is to find improvements that generalize: bigger models, more data, longer training, more compute.

Both the Experimenter and the Reviewer are explicitly prompted on this point. Concretely:

- **Avoid changes that overfit to the proxy.** Regularization tuned specifically for short runs, hyperparameters micro-optimized for the experiment's exact step count, tricks that exploit the val set's specific composition or the random seed — these can show wins at small scale that don't survive scaling. The Experimenter should refuse to recommend such ideas as `accepted` even when val-loss improves; surface them as `inconclusive` with reasoning.
- **Prefer changes with theoretical or empirical scaling support.** Ideas with a known scaling story (e.g., supported by scaling-law analyses, or with reference implementations validated at multiple scales) are stronger candidates than purely empirical small-scale wins.
- **Reviewer flags proxy-overfit risk.** When synthesizing insights, the Reviewer specifically tags patterns that look like proxy-overfit (improvements that disappear when combined with other changes, regularization that helps only in this experimental regime, etc.) and adds them to "Anti-patterns" rather than "Patterns observed."

This discipline isn't enforceable mechanically — it's a quality bar baked into the Experimenter and Reviewer system prompts.

### Subagent hard rules (encoded in each system prompt)

- **Ideator and Reviewer:** no disk writes, no code modifications, no commits. Return structured output only.
- **Experimenter:**
  - Writes only to files matching `relevant_files.editable`.
  - Does not touch `autoresearch/*` tracking files (main agent owns those).
  - Commits only on the experiment branch. Never commits on trunk.
  - No `git merge`, `git rebase`, or destructive git ops.
- **Every subagent:**
  - Must respect all `constraints` from `config.json`.
  - Must not propose or implement changes that modify validation dataset, validation logic, or validation metrics.

## Files & migration

### Plugin-shipped files (new layout)

```
plugins/ml-research/
├── agents/                                    # NEW — subagent definitions
│   ├── autoresearch-ideator.md
│   ├── autoresearch-experimenter.md
│   └── autoresearch-reviewer.md
└── skills/autoresearch/
    ├── SKILL.md                               # orchestration prompt (~200-300 lines)
    └── templates/
        ├── config.json                        # schema stub for Phase 0 scaffold
        ├── ideas.md                           # skeleton with comment header
        ├── insights.md                        # skeleton with empty sections
        ├── results.csv                        # header row only
        └── examples/                          # NEW — copy-and-adapt reference implementations
            ├── count_params_lightning.py      # current count_params.py, relabeled as example
            └── launch_slurm_lightning.sbatch  # current launch.sbatch, relabeled
```

### User-provided (in their project repo)

- Project source tree (untouched by the skill's own files).
- Executable for `entrypoints.count_params.command` (contract: prints JSON `{"trainable_params": int, "total_params": int}` to stdout).
- Executable for `entrypoints.launch_experiment.command` (contract: submits a job, prints job ID to stdout, accepts training overrides as positional args).
- `config.json` (generated at Phase 0 setup).

### SKILL.md shape (main agent's prompt)

Thin — orchestration only, no ML-research expertise. Length target: 200–300 lines. Structure:

- Frontmatter: name, description, invocation args.
- Identity: orchestrator; never does research itself.
- Phase 0 procedure (invocation, worktree creation, setup dialog, defaults, artifact init, initial commit).
- Phase 1 loop body (resumption, idea selection, dispatch patterns, post-dispatch housekeeping).
- Git choreography rules.
- Resumption protocol.
- Subagent dispatch patterns (common header, role-specific sections, return-contract validation).
- Autonomy principle.

### Agent definition files (long; carry the deep domain expertise)

Lengths are approximate upper targets — these don't touch main-agent context, so there's no penalty for depth:

- **`autoresearch-ideator.md`** (~400-500 lines): research ideation — reading past experiments, evaluating expected impact, hunting for reference implementations, duplicate-checking, writing good rationales, citation-quality rules, curated source list, proxy-task discipline (don't propose ideas that are likely to be proxy-overfit wins).
- **`autoresearch-experimenter.md`** (~600-800 lines): implementation — localizing code changes within `editable` globs, running entrypoints (count_params, launch_experiment, read_metrics), `Monitor` patterns, GPU-utilization tracking, `torch.compile` cache reuse and invalidation, crash diagnosis repertoire, fix-per-crash-type playbook, narrative-writing conventions, acceptance-criterion application against current best, proxy-task discipline.
- **`autoresearch-reviewer.md`** (~300 lines): synthesis — efficient scan of N experiment files, pattern identification (not restatement), pruning stale insights, grounding every insight in experiment IDs, proxy-overfit detection, strategic-note guidelines.

### Migration from current skill

Compared to the current `plugins/ml-research/skills/autoresearch/`:

- **Keep:** skill path. `config.yaml` (Lightning trainer overrides) could stay as an example template but is no longer mandatory.
- **Move:** `scripts/count_params.py` → `templates/examples/count_params_lightning.py`. `scripts/launch.sbatch` → `templates/examples/launch_slurm_lightning.sbatch`.
- **Drop:** current `templates/autoresearch_{ideas,log,results.csv}` — replaced by new template shapes. Current SKILL.md — rewritten from scratch against this design.
- **New:** three agent definition files in `plugins/ml-research/agents/`.

## Out of scope for this spec

The following are explicitly deferred; they may warrant their own specs later:

- **Pipelining** Ideator for experiment N+1 while Experimenter runs N. Simpler serial loop first.
- **Multi-experiment parallelism** (dispatching multiple Experimenters concurrently). Single-stream first; parallelism later if it doesn't compromise context hygiene.
- **Automated rebase onto `main`.** Left as a human decision.
- **Auto-promotion of campaign trunk to `main` on success.** Also a human decision.
- **Cross-campaign learning** (a Reviewer that synthesizes insights across multiple campaigns). Per-campaign isolation is sufficient for now.
- **API-level features beyond what Claude Code exposes.** The `advisor_20260301` tool and `clear_tool_uses_20250919` context-editing strategy are out of reach from inside a Claude Code skill; their Claude Code-native analogues (subagents and harness-managed compaction) are sufficient for this design.
