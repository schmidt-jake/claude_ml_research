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
    }
  },
  "debug_cap": 3,
  "constraints": [
    "no change to random seed, step count, validation dataset, validation logic, or validation metrics",
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

- **`relevant_files`** is a hard safety rail for Experimenter. Shell-style globs (`**`, `*`, `?`). Subagents may only *edit* files matching `editable`; they may *read* files matching `read_only`; files outside both lists are implicitly off-limits.
- **`entrypoints`** — pluggable user-provided commands. Contract for each is documented in SKILL.md (not duplicated per-campaign). `count_params.command` must print JSON with keys `trainable_params`, `total_params` to stdout. `launch_experiment.command` must submit a job, print its job ID to stdout, and accept training overrides as positional args.
- **`environment`** is a free-form hint string (`"slurm"`, `"local"`, `"k8s"`, `"ray"`, …) that tells the Experimenter which env-specific skill (if any) to invoke for monitoring.
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

Reviewer-maintained synthesis. Bounded (~50 lines target; Reviewer prunes). Structured into named sections so insights can be referenced by anchor in idea citations.

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
| `insights.md` | ~2 KB (bounded) |
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

3. **Constraints.** Present skill-default constraints (see below), ask for additions/removals.

4. **Theme priorities.** Present skill-default theme list, ask user to rank into high/medium/low buckets.

5. **Prior findings.** Open-ended: "What have you tried manually on this project? What worked, what didn't? Anything to bias ideation for or against?" Free-form bullet strings.

6. **`debug_cap`.** Default 3; ask if user wants to override.

Before writing, main agent presents a draft `config.json` and asks for confirmation.

### Skill-default constraints (seeded into `constraints` list)

```
- no change to random seed, step count, validation dataset, validation logic, or validation metrics
- parameter count must be <= baseline * 1.05
- no change to core dependencies / package versions
```

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

### Edit-later semantics

`config.json` is user-editable at any time post-setup. Main agent:
- Re-reads at every iteration (it's small).
- May propose edits ("15 experiments in, all attention-variants failed — add to constraints?") but never writes `config.json` without user approval.
- User is the only writer of `config.json` after Phase 0.

## Phase 1: Loop body

Runs forever after Phase 0. Main agent's per-iteration script:

```
loop forever:
    # 1. Small reads
    read config.json, ideas.md, insights.md, results.csv tail
    scan experiments/ frontmatters (status fields only)

    # 2. Resumption / reconciliation — idempotent, runs every iteration
    for each experiment with job_status: pending:
        probe job state via env-appropriate skill (ml-research:slurm, etc.)
        if still running:
            dispatch Experimenter in resume-monitoring mode
        elif terminated cleanly:
            dispatch Experimenter in analyze-only mode
        elif terminated abnormally:
            update job_status: crashed, record reason, continue

    # 3. Post-experiment housekeeping
    if any experiment just transitioned to a terminal state:
        write experiment file + CSV row on trunk, commit
        if job_status: succeeded && result_status: accepted:
            squash-merge experiment branch onto trunk
        # rejected / inconclusive / crashed: branch preserved, no merge

    # 4. Periodic maintenance
    if succeeded-count since last Reviewer >= 5:
        dispatch Reviewer
            apply insights delta to insights.md on trunk, commit

    # 5. Idea selection
    if ideas.md has items:
        next_idea = pop top item from ideas.md, commit on trunk
    else:
        dispatch Ideator
            next_idea = returned idea (with citations)

    # 6. Experimenter dispatch
    assign next experiment ID (auto-increment from experiments/ dir)
    create branch autoresearch/<campaign>/NNN-<slug> off trunk
    dispatch Experimenter with next_idea + branch name
        Experimenter runs its internal debug loop up to debug_cap
        returns structured summary + narrative text
    apply results on trunk:
        write experiments/NNN-<slug>.md
        append CSV row if succeeded
        commit on trunk
        if accepted → squash-merge branch
```

### Git choreography

| Actor | Branch | Writes |
|---|---|---|
| Main agent | trunk (`autoresearch/<campaign>`) | `config.json` (rarely), `ideas.md`, `insights.md`, `results.csv`, `experiments/*.md`, branch merges |
| Experimenter | experiment branch (`autoresearch/<campaign>/NNN-<slug>`) | code files only (matching `relevant_files.editable`). Does NOT touch `autoresearch/*` tracking files. |
| Ideator | none | no disk writes |
| Reviewer | none | no disk writes — returns delta; main agent applies |

**Experiment branch lifecycle:**

1. Main agent: `git checkout -b autoresearch/<campaign>/NNN-<slug>` off trunk HEAD.
2. Dispatch Experimenter on that branch.
3. Experimenter commits code changes on the branch.
4. Main agent `git checkout <trunk>`, writes experiment file + CSV row, commits on trunk.
5. If accepted: `git merge --squash autoresearch/<campaign>/NNN-<slug>` brings the code change onto trunk. Branch is preserved (not deleted — audit trail).
6. If rejected / inconclusive / crashed: branch preserved as-is, no merge. Trunk has the experiment file and CSV row; trunk does NOT have the code change.

Every experiment's code is preserved on its branch forever, regardless of outcome. Auditability requirement met in full.

**No rebasing onto `main`.** The campaign trunk is self-contained. Reconciling with `main` at the end (if ever) is a human decision outside the skill's scope.

### Monitor usage

The Experimenter uses `Monitor` inside its dispatch to stream job-state transitions (one notification per terminal state, not per-poll). The main agent does not use `Monitor` directly — it waits synchronously on the Experimenter dispatch.

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

Each has frontmatter (`name`, `description`, `tools` allowlist) plus a detailed system prompt. Main agent dispatches via the `Agent` tool with `subagent_type: "ml-research:autoresearch-<role>"`.

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
insights.md: <embedded, full — bounded ~50 lines>
Recent experiments (CSV tail, last ~20 rows): <embedded>
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
  "reasoning_short": "3% val loss improvement over baseline, stable training, no added complexity",
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
    run launch_experiment entrypoint, get job_id
    monitor job to terminal state via env-appropriate skill
    if job succeeded:
        analyze logs/metrics
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

- **`autoresearch-ideator.md`** (~400 lines): research ideation — reading past experiments, evaluating expected impact, hunting for reference implementations, duplicate-checking, writing good rationales, citation-quality rules.
- **`autoresearch-experimenter.md`** (~600 lines): implementation — localizing code changes, running entrypoints, `Monitor` patterns, crash diagnosis repertoire, fix-per-crash-type playbook, narrative-writing conventions.
- **`autoresearch-reviewer.md`** (~250 lines): synthesis — efficient scan of N experiment files, pattern identification (not restatement), pruning stale insights, grounding every insight in experiment IDs, strategic-note guidelines.

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
