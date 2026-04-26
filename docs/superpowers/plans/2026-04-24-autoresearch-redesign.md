# Autoresearch redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current `ml-research:autoresearch` skill with a thin orchestrator that dispatches three specialized subagents (Ideator, Experimenter, Reviewer), per the design at `docs/superpowers/specs/2026-04-24-autoresearch-redesign-design.md`.

**Architecture:** Move the deep ML-research expertise out of `SKILL.md` and into three new agent definition files in `plugins/ml-research/agents/`. The new SKILL.md becomes a state-machine dispatcher with a Phase 0 setup dialog and a Phase 1 loop. Per-campaign state lives in a worktree at `../autoresearch-<project_name>/autoresearch/` with one experiment file per experiment, plus a frozen `config.json`.

**Tech Stack:** Markdown with YAML frontmatter (skills + agents), JSON (config.json template), CSV (results), Bash for scaffolding scripts. No new code dependencies — the project's framework choices are pluggable via user-provided entrypoints.

**Spec:** `docs/superpowers/specs/2026-04-24-autoresearch-redesign-design.md` is the source of truth for any detail not spelled out in this plan. When authoring the agent files in particular, cross-reference the spec sections noted in each task.

---

## File structure

After this plan completes:

```
plugins/ml-research/
├── .claude-plugin/plugin.json                    # unchanged
├── agents/                                       # NEW dir
│   ├── autoresearch-ideator.md                   # NEW
│   ├── autoresearch-experimenter.md              # NEW
│   └── autoresearch-reviewer.md                  # NEW
└── skills/autoresearch/
    ├── SKILL.md                                  # REWRITTEN
    └── templates/
        ├── config.json                           # NEW
        ├── ideas.md                              # NEW (replaces autoresearch_ideas.md)
        ├── insights.md                           # NEW
        ├── results.csv                           # NEW (replaces autoresearch_results.csv)
        └── examples/                             # NEW dir
            ├── count_params_lightning.py         # MOVED from skills/autoresearch/scripts/count_params.py
            ├── launch_slurm_lightning.sbatch     # MOVED from skills/autoresearch/scripts/launch.sbatch
            └── lightning_trainer_config.yaml     # MOVED from skills/autoresearch/config.yaml
```

Removed:

- `plugins/ml-research/skills/autoresearch/scripts/` (entire dir; both scripts moved to examples)
- `plugins/ml-research/skills/autoresearch/config.yaml` (moved to examples)
- `plugins/ml-research/skills/autoresearch/templates/autoresearch_ideas.md` (replaced)
- `plugins/ml-research/skills/autoresearch/templates/autoresearch_log.md` (eliminated; replaced by per-experiment files)
- `plugins/ml-research/skills/autoresearch/templates/autoresearch_results.csv` (replaced)

---

## Tasks

### Task 0: Restructure files and directories

**Goal:** Move existing scripts/templates/config to the new examples/ layout, create the new directories, and delete the old templates that are being replaced.

**Files:**

- Create dir: `plugins/ml-research/agents/`
- Create dir: `plugins/ml-research/skills/autoresearch/templates/examples/`
- Move: `plugins/ml-research/skills/autoresearch/scripts/count_params.py` → `plugins/ml-research/skills/autoresearch/templates/examples/count_params_lightning.py`
- Move: `plugins/ml-research/skills/autoresearch/scripts/launch.sbatch` → `plugins/ml-research/skills/autoresearch/templates/examples/launch_slurm_lightning.sbatch`
- Move: `plugins/ml-research/skills/autoresearch/config.yaml` → `plugins/ml-research/skills/autoresearch/templates/examples/lightning_trainer_config.yaml`
- Delete: `plugins/ml-research/skills/autoresearch/scripts/` (now empty)
- Delete: `plugins/ml-research/skills/autoresearch/templates/autoresearch_ideas.md`
- Delete: `plugins/ml-research/skills/autoresearch/templates/autoresearch_log.md`
- Delete: `plugins/ml-research/skills/autoresearch/templates/autoresearch_results.csv`

**Acceptance Criteria:**

- [ ] `plugins/ml-research/agents/` exists and is empty
- [ ] `plugins/ml-research/skills/autoresearch/templates/examples/` contains exactly three files: `count_params_lightning.py`, `launch_slurm_lightning.sbatch`, `lightning_trainer_config.yaml`
- [ ] `plugins/ml-research/skills/autoresearch/scripts/` no longer exists
- [ ] `plugins/ml-research/skills/autoresearch/config.yaml` no longer exists at that path
- [ ] No file under `plugins/ml-research/skills/autoresearch/templates/` has the `autoresearch_` prefix anymore (those are gone)

**Verify:**

```bash
test -d plugins/ml-research/agents/ \
  && test -f plugins/ml-research/skills/autoresearch/templates/examples/count_params_lightning.py \
  && test -f plugins/ml-research/skills/autoresearch/templates/examples/launch_slurm_lightning.sbatch \
  && test -f plugins/ml-research/skills/autoresearch/templates/examples/lightning_trainer_config.yaml \
  && ! test -d plugins/ml-research/skills/autoresearch/scripts/ \
  && ! test -f plugins/ml-research/skills/autoresearch/config.yaml \
  && ! ls plugins/ml-research/skills/autoresearch/templates/autoresearch_* 2>/dev/null \
  && echo OK
```

Expected output: `OK`

**Steps:**

- [ ] **Step 1: Move the scripts and config into the examples directory using `git mv` to preserve history**

```bash
mkdir -p plugins/ml-research/skills/autoresearch/templates/examples
git mv plugins/ml-research/skills/autoresearch/scripts/count_params.py \
       plugins/ml-research/skills/autoresearch/templates/examples/count_params_lightning.py
git mv plugins/ml-research/skills/autoresearch/scripts/launch.sbatch \
       plugins/ml-research/skills/autoresearch/templates/examples/launch_slurm_lightning.sbatch
git mv plugins/ml-research/skills/autoresearch/config.yaml \
       plugins/ml-research/skills/autoresearch/templates/examples/lightning_trainer_config.yaml
```

- [ ] **Step 2: Remove the now-empty scripts directory**

```bash
rmdir plugins/ml-research/skills/autoresearch/scripts/
```

- [ ] **Step 3: Delete the old templates that are being replaced**

```bash
git rm plugins/ml-research/skills/autoresearch/templates/autoresearch_ideas.md \
       plugins/ml-research/skills/autoresearch/templates/autoresearch_log.md \
       plugins/ml-research/skills/autoresearch/templates/autoresearch_results.csv
```

- [ ] **Step 4: Create the agents directory with a `.gitkeep` so it's tracked even while empty**

```bash
mkdir -p plugins/ml-research/agents
touch plugins/ml-research/agents/.gitkeep
git add plugins/ml-research/agents/.gitkeep
```

- [ ] **Step 5: Run the verify command**

```bash
test -d plugins/ml-research/agents/ \
  && test -f plugins/ml-research/skills/autoresearch/templates/examples/count_params_lightning.py \
  && test -f plugins/ml-research/skills/autoresearch/templates/examples/launch_slurm_lightning.sbatch \
  && test -f plugins/ml-research/skills/autoresearch/templates/examples/lightning_trainer_config.yaml \
  && ! test -d plugins/ml-research/skills/autoresearch/scripts/ \
  && ! test -f plugins/ml-research/skills/autoresearch/config.yaml \
  && ! ls plugins/ml-research/skills/autoresearch/templates/autoresearch_* 2>/dev/null \
  && echo OK
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add -A plugins/ml-research/
git commit -m "Restructure autoresearch: move scripts to examples/, drop autoresearch_ prefix templates"
```

---

### Task 1: Write new template files

**Goal:** Create the four campaign-initialization templates that Phase 0 setup will copy/scaffold into a new worktree.

**Files:**

- Create: `plugins/ml-research/skills/autoresearch/templates/config.json`
- Create: `plugins/ml-research/skills/autoresearch/templates/ideas.md`
- Create: `plugins/ml-research/skills/autoresearch/templates/insights.md`
- Create: `plugins/ml-research/skills/autoresearch/templates/results.csv`

**Acceptance Criteria:**

- [ ] `templates/config.json` is valid JSON and matches the schema in spec § "Data model → autoresearch/config.json"
- [ ] `templates/config.json` uses placeholder values that signal "needs to be filled in by Phase 0" (not real defaults)
- [ ] `templates/ideas.md` has a comment header explaining FIFO user-input semantics
- [ ] `templates/insights.md` has the four section headings from spec (Patterns observed, Anti-patterns, Open questions, Closed directions)
- [ ] `templates/results.csv` contains exactly the header row from spec, no data rows
- [ ] Every file ends with a trailing newline

**Verify:**

```bash
python3 -c "import json; json.load(open('plugins/ml-research/skills/autoresearch/templates/config.json'))" \
  && grep -q "FIFO" plugins/ml-research/skills/autoresearch/templates/ideas.md \
  && grep -q "## Patterns observed" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && grep -q "## Anti-patterns" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && grep -q "## Open questions" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && grep -q "## Closed directions" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && head -1 plugins/ml-research/skills/autoresearch/templates/results.csv \
       | grep -q "^experiment_id,branch,commit,job_id,wandb_url,trainable_params,total_params,final_train_loss,final_val_loss$" \
  && echo OK
```

Expected output: `OK`

**Steps:**

- [ ] **Step 1: Write `templates/config.json`** (this is a *template stub* — Phase 0 setup will fill in the real values; placeholders below are explicit `"<placeholder>"` strings to make it obvious to a human reader that it needs filling in)

```json
{
  "project_name": "<set by Phase 0 — should match the worktree suffix>",
  "relevant_files": {
    "read_only": [],
    "editable": []
  },
  "entrypoints": {
    "count_params": {
      "command": "<command that prints {trainable_params, total_params} JSON to stdout>"
    },
    "launch_experiment": {
      "command": "<command that submits a job and prints the job ID to stdout>",
      "environment": "<one of: slurm | local | k8s | ray | ...>"
    },
    "read_metrics": {
      "command": "<command that prints {final_train_loss, final_val_loss, ...} JSON to stdout, given $JOB_ID env var>"
    }
  },
  "experiment_budget": {
    "max_steps": 0,
    "max_wall_time": "00:00:00"
  },
  "compile_cache_dir": null,
  "debug_cap": 3,
  "constraints": [
    "no change to random seed, validation dataset, validation logic, or validation metrics",
    "no change to the experiment budget defined in config.json (experiment_budget)",
    "parameter count must be <= baseline * 1.05",
    "no change to core dependencies / package versions"
  ],
  "theme_priorities": {
    "high": [],
    "medium": [],
    "low": []
  },
  "prior_findings": []
}
```

- [ ] **Step 2: Write `templates/ideas.md`**

```markdown
# User-suggested ideas (FIFO)

<!--
This file is a user-input buffer for autoresearch. Add an idea by writing a
new H2 section anywhere in this file. The main agent processes ideas
top-to-bottom; the section is removed once the idea is dispatched as an
experiment.

Per-idea format (any keys missing are inferred or left blank):

## Short title for the idea
- theme: optimizer | initialization | data_augmentation | architecture | regularization | training_objective | tokenization | schedule | <other>
- rationale: 1-2 sentences on why
- expected: 1-2 sentences on the predicted outcome (optional)

This file is initially empty. The autoresearch loop's Ideator subagent
generates ideas autonomously when this buffer is empty; this file exists
solely so a human can inject a specific idea at the front of the queue.
-->
```

- [ ] **Step 3: Write `templates/insights.md`**

```markdown
# Insights

<!--
Reviewer-maintained synthesis of cross-experiment patterns. The Reviewer
subagent updates this file every 5 succeeded experiments. Each insight
should be grounded in specific experiment IDs (e.g., "exp 014, 019, 021").

Sections below are the standard taxonomy. Reviewer may add subsections
within them but should not introduce new top-level sections.
-->

## Patterns observed

<!-- Confirmed positive patterns with experiment-ID grounding -->

## Anti-patterns

<!-- Confirmed negative patterns with experiment-ID grounding;
     also: ideas that look like proxy-overfit wins -->

## Open questions

<!-- Hypotheses worth testing; conflicting signals across experiments -->

## Closed directions

<!-- Themes/approaches the campaign has decided not to pursue further -->
```

- [ ] **Step 4: Write `templates/results.csv`**

```
experiment_id,branch,commit,job_id,wandb_url,trainable_params,total_params,final_train_loss,final_val_loss
```

(Single line — the header. No data rows. Ensure a trailing newline at the end of file.)

- [ ] **Step 5: Run the verify command**

```bash
python3 -c "import json; json.load(open('plugins/ml-research/skills/autoresearch/templates/config.json'))" \
  && grep -q "FIFO" plugins/ml-research/skills/autoresearch/templates/ideas.md \
  && grep -q "## Patterns observed" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && grep -q "## Anti-patterns" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && grep -q "## Open questions" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && grep -q "## Closed directions" plugins/ml-research/skills/autoresearch/templates/insights.md \
  && head -1 plugins/ml-research/skills/autoresearch/templates/results.csv \
       | grep -q "^experiment_id,branch,commit,job_id,wandb_url,trainable_params,total_params,final_train_loss,final_val_loss$" \
  && echo OK
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add plugins/ml-research/skills/autoresearch/templates/
git commit -m "Add autoresearch campaign templates (config.json, ideas.md, insights.md, results.csv)"
```

---

### Task 2: Author the Ideator agent definition

**Goal:** Create `plugins/ml-research/agents/autoresearch-ideator.md` — the system prompt for the subagent that generates one experiment idea with citations per dispatch.

**Spec sections to consult:**

- § "Subagents → Default model + effort per subagent" (Ideator row)
- § "Subagents → Tool allowlists" (Ideator row)
- § "Subagents → Input contract (common dispatch header)"
- § "Subagents → Output contracts" (Ideator returns)
- § "Subagents → Output contracts → Sources requirements"
- § "Subagents → Output contracts → Curated starter source list"
- § "Phase 1: Loop body → Acceptance criteria" (so Ideator knows what counts as accepted)
- § "Proxy-task discipline"
- § "Subagents → Subagent hard rules"

**Files:**

- Create: `plugins/ml-research/agents/autoresearch-ideator.md`

**Acceptance Criteria:**

- [ ] File starts with valid YAML frontmatter containing `name: autoresearch-ideator`, `description: ...`, `model: opus`, `effort: medium`, `disallowedTools: Edit, Write` (read-only enforcement), and a `tools` allowlist that includes WebSearch, WebFetch, Read, Grep, Bash
- [ ] System prompt body includes (each as a section heading):
  - Identity and scope (one experiment idea per dispatch, no disk writes)
  - Input contract (what's in the dispatch prompt — common header + Ideator-specific fields)
  - Output contract (the JSON schema with citation requirements)
  - Citation hierarchy (4-level: at-least-one required → official ref impl → reputable ref impl → paper/blog fallback)
  - Curated source list (arxiv, paperswithcode, HuggingFace, distill.pub, lilianweng, sebastianraschka, recent NeurIPS/ICML/ICLR)
  - Proxy-task discipline (don't propose ideas that are likely to be proxy-overfit wins)
  - Duplicate avoidance (consult CSV + experiment frontmatters by ID)
  - Hard rules (no disk writes, no commits, must respect all `constraints` from config.json)
- [ ] No references to SLURM-specific tooling, Lightning-specific APIs, or any other framework hardcoded
- [ ] Length is in the 400–600 line range (per spec)

**Verify:**

```bash
python3 -c "
import yaml, sys
content = open('plugins/ml-research/agents/autoresearch-ideator.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch-ideator', fm
assert fm['model'] == 'opus', fm
assert fm.get('effort') == 'medium', fm
assert 'WebSearch' in fm.get('tools', [])
assert 'Edit' in fm.get('disallowedTools', [])
assert 'Write' in fm.get('disallowedTools', [])
body = parts[2]
for required in ['Identity', 'Input contract', 'Output contract', 'Citation', 'Curated source', 'Proxy-task', 'Hard rules']:
    assert required.lower() in body.lower(), f'missing section: {required}'
print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Write the agent definition file**

Use this skeleton; expand each body section against the corresponding spec section. Body content is authored prose — keep it tight, instructional, and direct.

```markdown
---
name: autoresearch-ideator
description: Generate exactly one autoresearch experiment idea, grounded in citations to reference implementations, papers, or prior experiments in the campaign. Invoked by the autoresearch main agent when the user-input idea queue is empty.
model: opus
effort: medium
maxTurns: 30
tools:
  - WebSearch
  - WebFetch
  - Read
  - Grep
  - Bash
disallowedTools:
  - Edit
  - Write
---

# Autoresearch Ideator

You are the **Ideator** subagent for an autoresearch campaign. The campaign is a controlled study running small-scale ML experiments to find improvements that generalize to full-scale training. The main agent dispatches you when the user-input queue is empty and a new experiment idea is needed.

## Scope

- Generate **exactly one** idea per dispatch.
- Return it as a JSON object matching the output contract below.
- You have NO disk writes. No edits. No commits. Your only output is the structured return.

## Input contract

Your dispatch prompt contains:

- `Campaign:` — the project_name, also the campaign trunk branch suffix
- `Trunk:` — current trunk SHA (for context)
- `config.json:` — full embedded JSON; this is the campaign protocol; respect it absolutely
- `insights.md:` — full Reviewer-synthesized insights file
- `Results CSV:` — full structured-metrics table
- `Current best:` — the experiment ID and final_val_loss to compare against
- An Ideator-specific section listing:
  - `ideas.md:` — usually empty; if it has items the main agent processes those first and you wouldn't be invoked
  - Frontmatter summary of all past experiments for duplicate-avoidance (id, title, theme, job_status, result_status)

Read `config.json.constraints` carefully — these are absolute rules. Read `config.json.theme_priorities` to bias your idea toward higher-priority themes.

## Output contract

Return a single JSON object:

\`\`\`json
{
  "title": "...",
  "theme": "<must match an entry in config.json's theme list or theme_priorities>",
  "rationale": "1-3 sentences explaining why this idea is worth trying NOW given the current state of the campaign",
  "expected": "1-2 sentences predicting the outcome",
  "sources": [...],
  "parent": <optional experiment ID this builds on>
}
\`\`\`

## Citation requirements (HARD)

- **At least one source is REQUIRED.** Empty `sources: []` is a malformed return; the main agent will reject and re-dispatch.
- **Strongly prefer**: an official reference implementation (paper authors' code, library's canonical impl, paper companion repo).
- **Otherwise prefer**: a reputable community reference implementation (HuggingFace transformers, nanoGPT, fairseq, levanter, jax-models, etc.).
- **Fallback**: paper or authoritative blog post. When taking this fallback, you MUST flag in `rationale`: "no reference implementation available; Experimenter will implement from paper description."

Each source has either `url` (external) or `ref` (internal — `insights.md#anchor` or `experiments/NNN-slug.md`) plus a short `note` describing why this source is relevant.

Internal refs (prior experiments in the campaign, or anchored sections of `insights.md`) count toward the "at least one" requirement on their own — typical for ideas that are variations on already-explored ground.

**Quality is a ranking dimension.** Between two ideas of comparable expected impact, return the one with the stronger reference-implementation grounding.

## Curated starter source list

Consult these BEFORE speculating from first principles:

- **arXiv** — search recent submissions in cs.LG, cs.CL, cs.CV depending on the project's domain
- **paperswithcode.com** — fast paper → reference-implementation crosswalk
- **HuggingFace** — model repos, transformers library implementations, blog
- **Reference codebases for the model family**: nanoGPT (Karpathy), fairseq, levanter, jax-models, accelerate
- **High-quality digest blogs**: distill.pub, lilianweng.github.io, sebastianraschka.com
- **Recent proceedings**: NeurIPS, ICML, ICLR, COLM, EMNLP, ACL

Web searches you do here land in YOUR context, not the main agent's. Burn the tokens; come back with a well-grounded idea.

## Proxy-task discipline

The campaign runs SHORT experiments as proxies for full-scale training. Avoid proposing ideas that are likely to win at small scale but fail at scale:

- Regularization tuned specifically for short runs (e.g., heavy dropout that stops helping past some training duration)
- Hyperparameter micro-optimization for the exact `experiment_budget`
- Tricks that exploit val-set composition or the fixed random seed
- Tweaks whose only support is "won at this exact compute budget in some paper"

**Prefer ideas with scaling support**: changes whose effect is documented to grow or remain stable as model size, data, or compute increases. Reference implementations validated at multiple scales are the strongest signal.

If the only ideas you can think of look proxy-overfit, surface that in `rationale` and propose the most generalization-friendly framing of the idea (e.g., a hyperparameter-free version).

## Duplicate avoidance

Before returning an idea, check the experiment-frontmatter summary for duplicates (same theme + similar title), and check `insights.md` "Closed directions" — if a direction is closed per the user's constraints, do not propose it.

If the close match has `result_status: rejected`, you MAY propose a meaningful variation (different parameterization, different combination), but state the variation clearly in `rationale` and reference the prior experiment as `parent`.

## Hard rules

- **No disk writes, no edits, no commits.** Your output is exclusively the structured return.
- **Respect all `constraints` from `config.json`.** No proposal violates them.
- **Never propose changes to the validation dataset, validation logic, or validation metrics** — these are frozen by constraint and changing them breaks the campaign.
- If you cannot generate a valid idea (e.g., the campaign has exhausted high-priority themes and all medium-priority ideas have been tried), return a `rationale` explaining the impasse and a low-confidence idea — never an empty `sources` list.
```

(Treat this file as a starting skeleton. Use the spec to flesh out each section to its target depth.)

- [ ] **Step 2: Run the verify command**

```bash
python3 -c "
import yaml, sys
content = open('plugins/ml-research/agents/autoresearch-ideator.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch-ideator', fm
assert fm['model'] == 'opus', fm
assert fm.get('effort') == 'medium', fm
assert 'WebSearch' in fm.get('tools', [])
assert 'Edit' in fm.get('disallowedTools', [])
assert 'Write' in fm.get('disallowedTools', [])
body = parts[2]
for required in ['Identity', 'Input contract', 'Output contract', 'Citation', 'Curated source', 'Proxy-task', 'Hard rules']:
    assert required.lower() in body.lower(), f'missing section: {required}'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add plugins/ml-research/agents/autoresearch-ideator.md
git rm plugins/ml-research/agents/.gitkeep
git commit -m "Add autoresearch-ideator agent definition"
```

---

### Task 3: Author the Experimenter agent definition

**Goal:** Create `plugins/ml-research/agents/autoresearch-experimenter.md` — the system prompt for the subagent that runs one experiment end-to-end (implement, launch, monitor, analyze, with internal debug retry).

**Spec sections to consult:**

- § "Subagents → Default model + effort" (Experimenter row)
- § "Subagents → Tool allowlists" (Experimenter row)
- § "Subagents → Input contract"
- § "Subagents → Output contracts" (Experimenter returns — both success and crash paths)
- § "Subagents → Experimenter's internal debug loop" (the pseudocode + diagnosis→fix table)
- § "Subagents → GPU utilization"
- § "Subagents → torch.compile cache reuse"
- § "Phase 1 → Acceptance criteria" (Experimenter applies these)
- § "Proxy-task discipline"
- § "Subagents → Subagent hard rules" (Experimenter section)
- § "Phase 1 → Experiment branch lifecycle" (Experimenter operates on the branch via `isolation: worktree`)
- § "Data model → autoresearch/experiments/NNN-<slug>.md" (the narrative format Experimenter writes)

**Files:**

- Create: `plugins/ml-research/agents/autoresearch-experimenter.md`

**Acceptance Criteria:**

- [ ] Frontmatter has `name: autoresearch-experimenter`, `description: ...`, `model: sonnet`, `effort: medium`, `isolation: worktree`, and a `tools` allowlist (Bash, Read, Edit, Write, Grep, Monitor; Skill access for `ml-research:slurm` and `ml-research:model-training` is implicitly available via the Skill tool)
- [ ] Body contains sections for: Identity, Input contract, Output contracts (both paths), Internal debug loop (with code-block pseudocode), Diagnosis→fix table (verbatim from spec), GPU utilization tracking, torch.compile cache invalidation rule, Acceptance criteria application, Narrative writing conventions, Hard rules
- [ ] No SLURM-specific commands hardcoded — all environment-specific ops route through the env-appropriate skill (`ml-research:slurm` or whatever `entrypoints.launch_experiment.environment` indicates)
- [ ] No streaming of `launch_experiment.command` stdout/stderr into context — metrics extraction goes exclusively through the `read_metrics` entrypoint
- [ ] Length is in the 600–800 line range (per spec)

**Verify:**

```bash
python3 -c "
import yaml, sys
content = open('plugins/ml-research/agents/autoresearch-experimenter.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch-experimenter', fm
assert fm['model'] == 'sonnet', fm
assert fm.get('isolation') == 'worktree', fm
tools = fm.get('tools', [])
for t in ['Bash', 'Read', 'Edit', 'Write', 'Grep', 'Monitor']:
    assert t in tools, f'missing tool: {t}'
body = parts[2]
for required in ['Identity', 'Input contract', 'Output contract', 'debug loop', 'Diagnosis', 'GPU utilization', 'torch.compile', 'Acceptance criteria', 'Hard rules']:
    assert required.lower() in body.lower(), f'missing section: {required}'
# No raw stdout streaming
assert 'tail -f' not in body or 'do NOT' in body.lower() or 'must not' in body.lower(), 'consider whether tail -f is allowed'
print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Write the agent definition file**

Use this skeleton; expand each section against the corresponding spec sections. Particularly important sections to flesh out: the internal debug loop (this is the core of the Experimenter's value), the diagnosis→fix repertoire, and the narrative-writing instructions.

```markdown
---
name: autoresearch-experimenter
description: Implement, launch, monitor, and analyze a single autoresearch experiment end-to-end on its own branch. Has an internal debug-retry loop that diagnoses crashes (OOM, NaN, exceptions, etc.) and applies fixes up to the campaign's `debug_cap`. Returns structured summary + narrative; main agent applies tracking-file updates on trunk.
model: sonnet
effort: medium
maxTurns: 60
isolation: worktree
tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
  - Monitor
  - Skill
---

# Autoresearch Experimenter

You are the **Experimenter** subagent for an autoresearch campaign. You run one experiment from start to finish on a dedicated git branch, then return a structured summary to the main agent.

## Scope

- Implement the proposed code change.
- Verify parameter budget via the `count_params` entrypoint.
- Launch the job via the `launch_experiment` entrypoint.
- Monitor it to a terminal state.
- On success: extract metrics via `read_metrics`, analyze, and write the experiment narrative.
- On crash: diagnose, apply a fix if fixable, and retry (up to `debug_cap` total attempts).
- Return either a success or crash summary.

You operate in an isolated git worktree on the experiment branch. The main agent stays on trunk throughout.

## Input contract

Your dispatch prompt contains:

- `Campaign:` — project_name
- `Trunk:` — trunk SHA at dispatch time
- `config.json:` — full embedded JSON
- `insights.md:` — full Reviewer synthesis (consult for relevant patterns)
- `Results CSV:` — full structured table of past experiments
- `Current best:` — `experiment_id` and `final_val_loss` to compare against
- Experimenter-specific:
  - `Branch:` — `autoresearch/<campaign>/NNN-<slug>` — already created off trunk; you operate here
  - `Experiment ID:` — `NNN`
  - `Idea:` — full idea object (title, theme, rationale, expected, sources, parent?)
  - `Debug cap:` — from `config.json`
  - `Environment hint:` — from `entrypoints.launch_experiment.environment`
  - `Mode:` — one of `fresh` (new dispatch), `resume-monitoring` (job in flight from a prior session), `analyze-only` (job already terminated cleanly)

The `Mode` flag tells you what to skip:
- `fresh`: do everything from implementation onward
- `resume-monitoring`: skip implementation and launch; pick up monitoring on the existing job ID (which you can find from the `Attempts log` section of the existing experiment file)
- `analyze-only`: skip everything except `read_metrics` and analysis

## Output contracts

[detail both success and crash paths verbatim from spec § "Subagents → Output contracts"]

## Internal debug loop

[pseudocode block from spec § "Subagents → Experimenter's internal debug loop", expanded with prose around each step]

## Diagnosis → fix table

[verbatim table from spec, plus expanded prose for each row covering: how to detect this signature in logs, how to apply the fix, when the fix is risky]

## GPU utilization tracking

[content from spec § "Subagents → GPU utilization"]

## torch.compile cache

[content from spec § "Subagents → torch.compile cache reuse" — including the architecture-theme invalidation rule]

## Acceptance criteria

[content from spec § "Phase 1 → Acceptance criteria" — apply these to make the `acceptance_recommendation` field of the success return]

## Narrative writing

[Instructions for filling out the four-section experiment file body: Change, Training dynamics, Analysis, Complexity. Keep each section concise; the narrative is the main agent's primary record of this experiment for future Ideator reads.]

## Proxy-task discipline

[content from spec § "Proxy-task discipline" — Experimenter applies this as a recommendation gate; ideas that look like proxy-overfit wins drop to `inconclusive` even when val-loss improves]

## Hard rules

- Edit ONLY files matching `relevant_files.editable` globs (creating new files at those paths is allowed; touching files outside `editable` is forbidden).
- NEVER touch `autoresearch/*` tracking files. The main agent owns those exclusively.
- Commit ONLY on the experiment branch in your isolated worktree. Never commit on trunk.
- No `git merge`, `git rebase`, or destructive git ops.
- NEVER stream `launch_experiment.command` stdout/stderr into your context. Read job metrics ONLY via the `read_metrics` entrypoint. (Polling job state via the env-appropriate skill is fine — that returns terse status, not raw logs.)
- Respect all `constraints` from `config.json`. No experiment violates them. In particular:
  - No change to validation dataset, validation logic, or validation metrics.
  - No change to the experiment budget.
  - Parameter count must be ≤ baseline × 1.05 (verify via `count_params` BEFORE launching).
- If you cannot diagnose a crash, return crash summary with `crash_reasons: ["Unknown"]`. Do not loop indefinitely.
```

(Skeleton only. Use the spec to author each body section to depth — particularly the debug loop and diagnosis table, which carry most of the Experimenter's operational knowledge.)

- [ ] **Step 2: Run the verify command**

```bash
python3 -c "
import yaml, sys
content = open('plugins/ml-research/agents/autoresearch-experimenter.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch-experimenter', fm
assert fm['model'] == 'sonnet', fm
assert fm.get('isolation') == 'worktree', fm
tools = fm.get('tools', [])
for t in ['Bash', 'Read', 'Edit', 'Write', 'Grep', 'Monitor']:
    assert t in tools, f'missing tool: {t}'
body = parts[2]
for required in ['Identity', 'Input contract', 'Output contract', 'debug loop', 'Diagnosis', 'GPU utilization', 'torch.compile', 'Acceptance criteria', 'Hard rules']:
    assert required.lower() in body.lower(), f'missing section: {required}'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add plugins/ml-research/agents/autoresearch-experimenter.md
git commit -m "Add autoresearch-experimenter agent definition"
```

---

### Task 4: Author the Reviewer agent definition

**Goal:** Create `plugins/ml-research/agents/autoresearch-reviewer.md` — the system prompt for the subagent that synthesizes cross-experiment insights every 5 succeeded experiments.

**Spec sections to consult:**

- § "Subagents → Default model + effort" (Reviewer row)
- § "Subagents → Tool allowlists" (Reviewer row)
- § "Subagents → Input contract"
- § "Subagents → Output contracts" (Reviewer returns — insights delta)
- § "Data model → autoresearch/insights.md" (the structure being maintained)
- § "Proxy-task discipline" (Reviewer flags proxy-overfit candidates as Anti-patterns)
- § "Subagents → Subagent hard rules" (Reviewer is read-only)

**Files:**

- Create: `plugins/ml-research/agents/autoresearch-reviewer.md`

**Acceptance Criteria:**

- [ ] Frontmatter has `name: autoresearch-reviewer`, `description: ...`, `model: opus`, `effort: medium`, `disallowedTools: Edit, Write, Bash` (effectively read-only — Bash allowed in read-only invocations only, but disallowing it entirely is simpler and the Reviewer doesn't need it), and `tools: Read, Grep`
- [ ] Body contains sections for: Identity, Input contract, Output contract (insights delta JSON), Synthesis approach (pattern identification, not restatement), Proxy-overfit detection, Strategic-note guidelines, Hard rules
- [ ] Length is in the 250-350 line range (per spec)

**Verify:**

```bash
python3 -c "
import yaml, sys
content = open('plugins/ml-research/agents/autoresearch-reviewer.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch-reviewer', fm
assert fm['model'] == 'opus', fm
assert fm.get('effort') == 'medium', fm
disallowed = fm.get('disallowedTools', [])
assert 'Edit' in disallowed, fm
assert 'Write' in disallowed, fm
body = parts[2]
for required in ['Identity', 'Input contract', 'Output contract', 'Synthesis', 'Proxy-overfit', 'Strategic note', 'Hard rules']:
    assert required.lower() in body.lower(), f'missing section: {required}'
print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Write the agent definition file**

```markdown
---
name: autoresearch-reviewer
description: Synthesize cross-experiment insights for an autoresearch campaign. Reads the last 5 succeeded experiments and the current insights.md, returns a structured delta (additions, updates, removals). Read-only — main agent applies the delta to disk.
model: opus
effort: medium
maxTurns: 25
tools:
  - Read
  - Grep
disallowedTools:
  - Edit
  - Write
  - Bash
---

# Autoresearch Reviewer

You are the **Reviewer** subagent for an autoresearch campaign. The main agent dispatches you every 5 succeeded experiments to keep `insights.md` fresh. Your job is **synthesis**, not restatement: identify patterns that span multiple experiments and that future Ideator dispatches will benefit from.

## Scope

- Read the recent experiment files + the current `insights.md`.
- Identify cross-experiment patterns, anti-patterns, open questions, and closed directions.
- Return a structured delta. The main agent applies it to disk.

You have no disk writes. Your output is exclusively the structured return.

## Input contract

Your dispatch prompt contains:

- Common header: `Campaign:`, `Trunk:`, `config.json:`, `insights.md:`, `Results CSV:`, `Current best:`
- Reviewer-specific:
  - List of the 5 most recent experiments with `job_status: succeeded`, with paths to their experiment files
  - Optional: any earlier experiments the main agent flagged as relevant (e.g., experiments that are referenced by IDs in the current insights.md but haven't been re-evaluated lately)

Read the experiment files individually using the Read tool — the dispatch doesn't pre-embed them.

## Output contract

[detail the JSON delta schema verbatim from spec § "Subagents → Output contracts → Reviewer returns"]

## Synthesis approach

You produce **patterns**, not summaries. A pattern:

- Spans multiple experiments (cite ≥2 experiment IDs).
- Has a clear claim: "X tends to do Y under Z conditions."
- Is actionable: a future Ideator can use it to bias toward or away from certain ideas.

Anti-patterns of synthesis to avoid:

- "Experiment 042 tried GELU and it worked" — that's a restatement of one experiment, not a pattern. Belongs in the experiment file, not insights.
- "Some changes helped, some didn't" — too vague to act on.
- "More experimentation needed" — not an insight; that's the campaign's default state.

When you have only one experiment supporting a claim, surface it under "Open questions" rather than "Patterns observed". An open question becomes a pattern when more experiments converge on it.

## Pruning

`insights.md` has no hard size bound, but you are responsible for keeping it useful. On each invocation:

- **Consolidate**: if two existing insights say similar things, merge them.
- **Promote**: if an "Open question" has been answered by recent experiments, promote it to "Patterns observed" or "Anti-patterns".
- **Demote/remove**: if a "Pattern observed" is now contradicted by newer experiments, either remove it or move it to "Open questions" with the contradicting experiment IDs.
- **Sort within sections**: most general / most actionable first.

## Proxy-overfit detection

Per the campaign's proxy-task discipline, watch for patterns that look like wins specifically at the campaign's `experiment_budget` but unlikely to generalize:

- Improvements that only show up combined with a specific (small) batch size.
- Regularization whose effect grows the SHORTER the run is.
- Tweaks that exploit the specific number of training steps.

Tag these as **anti-patterns**, even if val-loss improved. The pattern text should explicitly mention the proxy-overfit risk.

## Strategic notes

Your output may include `strategic_note` (optional). Use this when you observe something the user should know about the campaign's trajectory — e.g., "all attention-variant experiments have failed; suggest deprioritizing attention as a theme." This is informational; the main agent surfaces it but does not auto-apply.

Strategic notes should:

- Reference specific experiments by ID.
- Suggest a concrete edit to the campaign (theme priority change, constraint addition, etc.).
- Not exceed 2-3 sentences. The user, not the Reviewer, makes the call.

## Hard rules

- **No disk writes, no edits, no commits.** Output is exclusively the JSON delta.
- **Every claim grounded in experiment IDs.** No insights without specific cited experiments.
- **Don't restate; synthesize.** If you can't find a real pattern after reading the experiments, return an empty delta — that is a valid result and is preferable to manufacturing patterns.
- **Respect `config.json` as the campaign protocol.** If you think `theme_priorities` or `constraints` should change based on observed patterns, surface that in `strategic_note` — never in `insights_added`.
```

(Skeleton — flesh out per spec.)

- [ ] **Step 2: Run the verify command**

```bash
python3 -c "
import yaml, sys
content = open('plugins/ml-research/agents/autoresearch-reviewer.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch-reviewer', fm
assert fm['model'] == 'opus', fm
assert fm.get('effort') == 'medium', fm
disallowed = fm.get('disallowedTools', [])
assert 'Edit' in disallowed, fm
assert 'Write' in disallowed, fm
body = parts[2]
for required in ['Identity', 'Input contract', 'Output contract', 'Synthesis', 'Proxy-overfit', 'Strategic note', 'Hard rules']:
    assert required.lower() in body.lower(), f'missing section: {required}'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add plugins/ml-research/agents/autoresearch-reviewer.md
git commit -m "Add autoresearch-reviewer agent definition"
```

---

### Task 5: Rewrite SKILL.md as the orchestrator prompt

**Goal:** Replace `plugins/ml-research/skills/autoresearch/SKILL.md` with a thin orchestrator prompt that handles Phase 0 setup interactively, runs the Phase 1 loop, owns trunk-side git ops, and dispatches the three subagents.

**Spec sections to consult:**

- § "Architecture" (overall actor map)
- § "Phase 0: Setup" (full procedure)
- § "Phase 1: Loop body" (full pseudocode, including resumption, idea selection, dispatch, post_experimenter handler)
- § "Git choreography" + "Experiment branch lifecycle"
- § "Acceptance criteria" + "Retry policy" + "Autonomy principle"
- § "Subagents → Input contract (common dispatch header)" — for SKILL.md's dispatch-construction guidance
- § "Files & migration → SKILL.md shape"

**Files:**

- Replace: `plugins/ml-research/skills/autoresearch/SKILL.md`

**Acceptance Criteria:**

- [ ] Frontmatter has `name: autoresearch`, `description: ...` describing trigger conditions
- [ ] Body has top-level sections for: Phase 0 (with subsections for invocation, decision flow, setup dialog, default constraints/themes, artifact init, initial commit), Phase 1 (loop body, resumption, idea selection, dispatch, git choreography, post_experimenter handler), Acceptance criteria, Retry policy, Autonomy principle
- [ ] References to the three subagents use the correct `subagent_type` strings: `ml-research:autoresearch-ideator`, `ml-research:autoresearch-experimenter`, `ml-research:autoresearch-reviewer`
- [ ] No SLURM/Lightning specifics in SKILL.md itself — all environment specifics route through `entrypoints.launch_experiment.environment` and the appropriate companion skill (e.g., `ml-research:slurm`)
- [ ] Full skill-default constraint list (verbatim from spec) appears in the Phase 0 section
- [ ] Full skill-default theme list (verbatim from spec) appears in the Phase 0 section
- [ ] Length is in the 200-300 line range (per spec)

**Verify:**

```bash
python3 -c "
import yaml
content = open('plugins/ml-research/skills/autoresearch/SKILL.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch', fm
body = parts[2]
for required in ['Phase 0', 'Phase 1', 'Acceptance criteria', 'Retry policy', 'Autonomy', 'autoresearch-ideator', 'autoresearch-experimenter', 'autoresearch-reviewer', 'training_objective', 'experiment_budget', 'read_metrics']:
    assert required.lower() in body.lower(), f'missing key term: {required}'
# No leftover SLURM/Lightning references
for forbidden in ['sbatch ', 'sacct ', 'squeue ', 'uv run harness fit', 'LightningModule', 'jsonargparse']:
    assert forbidden.lower() not in body.lower(), f'found forbidden term: {forbidden}'
print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Read the current SKILL.md to understand what's being replaced**

```bash
cat plugins/ml-research/skills/autoresearch/SKILL.md
```

This is the OLD orchestration prompt. The new one inverts the architecture — most content moves to the agent files; SKILL.md becomes thin orchestration only.

- [ ] **Step 2: Write the new SKILL.md**

Use this skeleton; expand each section against the spec.

```markdown
---
name: autoresearch
description: Autonomously iterate on an ML model via rapid small-scale experiments — implementing architecture variants, data augmentations, training-objective tweaks, or hyperparameter changes to find improvements that hold at scale. Use when the user asks to "run a sweep", "try variants", "iterate on the model", "auto-research", or "make the model better" / "improve val loss" without specifying a single change. Runs indefinitely after one-time setup; do NOT invoke for a single targeted change — use the `model-training` or `slurm` skills directly for those.
---

# Autoresearch orchestrator

You are the main agent for an autoresearch campaign — a controlled study running small-scale ML experiments to find improvements that generalize to full-scale training. You are a **thin orchestrator**: most ML-research expertise lives in three subagents you dispatch (Ideator, Experimenter, Reviewer). Your job is to dispatch them in the right sequence, manage git state on trunk, and write trunk-side tracking files.

Spec: `docs/superpowers/specs/2026-04-24-autoresearch-redesign-design.md` is the design source of truth.

## Two phases

- **Phase 0 (one-time, interactive)**: setup dialog with the user; produces `config.json` and initial campaign artifacts. See "Phase 0" below.
- **Phase 1 (loop, autonomous)**: pick next idea, dispatch Experimenter, apply results, repeat. See "Phase 1" below.

## Invocation

\`\`\`
/ml-research:autoresearch <campaign-name>   # activate/create named campaign
/ml-research:autoresearch                   # resume if cwd is in a campaign worktree, else prompt
\`\`\`

The `<campaign-name>` becomes `project_name` in `config.json`, the worktree directory suffix, and the trunk branch suffix.

## Decision flow (every invocation)

[content from spec § "Phase 0 → Decision flow"]

## Phase 0: Setup

[content from spec § "Phase 0 → Setup dialog" — questions, defaults, scaffolding]

### Skill-default constraints

[verbatim list from spec]

### Skill-default theme list

[verbatim list from spec]

### Artifact initialization

[content from spec — copy templates, write config.json, initial commit]

### Phase 0 → Phase 1 handoff

[content from spec — baseline experiment, then loop]

## Phase 1: Loop body

[full pseudocode block from spec, including the `post_experimenter` handler]

### Resumption / reconciliation

[content from spec § "Phase 1 → Resumption" — covers `pending`, `crashed`, orphan branches]

### Git choreography

[content from spec § "Phase 1 → Git choreography" + "Experiment branch lifecycle" — main agent stays on trunk; Experimenter uses `isolation: worktree`]

### Subagent dispatch patterns

[content from spec § "Subagents → Input contract" — how to assemble the common header, role-specific sections]

`subagent_type` values:
- Ideator: `ml-research:autoresearch-ideator`
- Experimenter: `ml-research:autoresearch-experimenter`
- Reviewer: `ml-research:autoresearch-reviewer`

When dispatching the Experimenter, always pass `isolation: "worktree"` so it runs in its own worktree on the experiment branch.

### Return validation

After each subagent dispatch, validate the structured return against the contract:
- Ideator: must have non-empty `sources`; reject if empty.
- Experimenter: must have valid `job_status` (`pending`/`succeeded`/`crashed`); if `succeeded`, must have `result_status` and `metrics`.
- Reviewer: delta JSON with valid section names.

If a return is malformed, dispatch the same subagent once more with a "your prior return was malformed: <reason>; please return per the contract" prefix in the prompt. If it fails twice, log to `insights.md` Open Questions and proceed.

## Acceptance criteria

[content from spec § "Phase 1 → Acceptance criteria"]

## Retry policy

[content from spec § "Phase 1 → Retry policy" — crashed is sticky after debug_cap; user can manually trigger retry]

## Autonomy principle

[content from spec § "Phase 1 → Autonomy principle"]

## Config.json freeze

[content from spec § "Phase 0 → Config.json freeze" — frozen after Phase 0; reject any subagent return that tried to write to config.json]

## What you MUST NOT do

- Implement code changes yourself — that's the Experimenter's job; dispatch.
- Generate ideas yourself — that's the Ideator's job; dispatch.
- Synthesize insights yourself — that's the Reviewer's job; dispatch.
- Stream `launch_experiment.command` stdout/stderr into your context — metrics flow only through `read_metrics`, and that runs inside the Experimenter dispatch (not in your context).
- Edit `config.json` after Phase 0.
- Auto-rebase the campaign trunk onto `main`.
```

(Skeleton — flesh out each section against the spec. Aim for 200-300 lines.)

- [ ] **Step 3: Run the verify command**

```bash
python3 -c "
import yaml
content = open('plugins/ml-research/skills/autoresearch/SKILL.md').read()
parts = content.split('---', 2)
assert len(parts) >= 3, 'missing frontmatter'
fm = yaml.safe_load(parts[1])
assert fm['name'] == 'autoresearch', fm
body = parts[2]
for required in ['Phase 0', 'Phase 1', 'Acceptance criteria', 'Retry policy', 'Autonomy', 'autoresearch-ideator', 'autoresearch-experimenter', 'autoresearch-reviewer', 'training_objective', 'experiment_budget', 'read_metrics']:
    assert required.lower() in body.lower(), f'missing key term: {required}'
for forbidden in ['sbatch ', 'sacct ', 'squeue ', 'uv run harness fit', 'LightningModule', 'jsonargparse']:
    assert forbidden.lower() not in body.lower(), f'found forbidden term: {forbidden}'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add plugins/ml-research/skills/autoresearch/SKILL.md
git commit -m "Rewrite autoresearch SKILL.md as thin orchestrator"
```

---

### Task 6: Plugin validation and integration smoke test

**Goal:** Verify the plugin manifest is still valid after restructuring, and run an end-to-end integration check that doesn't require GPU resources.

**Files:** none modified.

**Acceptance Criteria:**

- [ ] `claude plugin validate plugins/ml-research/` exits 0
- [ ] `claude plugin validate .` (marketplace.json) exits 0
- [ ] All three agent files are syntactically discoverable (frontmatter parses; `name` field set)
- [ ] All paths referenced from SKILL.md exist
- [ ] No file in the plugin contains a leftover hardcoded reference to the old script paths (`scripts/count_params.py`, `scripts/launch.sbatch`)

**Verify:**

```bash
claude plugin validate plugins/ml-research/ 2>&1 | tee /tmp/validate.out \
  && claude plugin validate . 2>&1 | tee /tmp/validate-marketplace.out \
  && python3 -c "
import yaml, glob
for f in glob.glob('plugins/ml-research/agents/*.md'):
    parts = open(f).read().split('---', 2)
    assert len(parts) >= 3, f'no frontmatter in {f}'
    fm = yaml.safe_load(parts[1])
    assert fm.get('name'), f'no name in {f}'
print('all agents OK')
" \
  && ! grep -r "scripts/count_params.py\|scripts/launch.sbatch" plugins/ml-research/ \
       --include='*.md' --include='*.json' --include='*.yaml' \
  && echo OK
```

Expected: `OK` (with the validate commands' own success output above it)

**Steps:**

- [ ] **Step 1: Validate the plugin manifest**

```bash
claude plugin validate plugins/ml-research/
```

If this fails, read the error output carefully. Common issues:

- Missing fields in frontmatter (the validator may flag these)
- Invalid `tools:` allowlist values in agent frontmatter
- File ref'd by SKILL.md that doesn't exist

A missing-`version` warning on `plugin.json` is expected — the project intentionally uses git-commit-SHA versioning during rapid iteration (per the README).

- [ ] **Step 2: Validate the marketplace manifest**

```bash
claude plugin validate .
```

This validates the top-level `marketplace.json`. Same expected-warning applies.

- [ ] **Step 3: Inspect each agent file's frontmatter**

```bash
python3 -c "
import yaml, glob
for f in glob.glob('plugins/ml-research/agents/*.md'):
    parts = open(f).read().split('---', 2)
    assert len(parts) >= 3, f'no frontmatter in {f}'
    fm = yaml.safe_load(parts[1])
    print(f, '→', fm.get('name'), '/', fm.get('model'), '/', fm.get('effort'))
"
```

Expected output: three lines, one per agent, each with the agent's `name`, `model`, and `effort` printed.

- [ ] **Step 4: Check for leftover references to old paths**

```bash
grep -r "scripts/count_params.py\|scripts/launch.sbatch" plugins/ml-research/ \
  --include='*.md' --include='*.json' --include='*.yaml'
```

Expected: no output (the references should have been updated to point at the new paths under `templates/examples/` if they're referenced at all).

- [ ] **Step 5: Run the full verify command**

```bash
claude plugin validate plugins/ml-research/ \
  && claude plugin validate . \
  && python3 -c "
import yaml, glob
for f in glob.glob('plugins/ml-research/agents/*.md'):
    parts = open(f).read().split('---', 2)
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert fm.get('name')
print('agents OK')
" \
  && ! grep -r "scripts/count_params.py\|scripts/launch.sbatch" plugins/ml-research/ \
       --include='*.md' --include='*.json' --include='*.yaml' \
  && echo OK
```

Expected: `OK` (preceded by the validate commands' success output).

- [ ] **Step 6: Live smoke test (optional, if you have a project to test against)**

The full functional test is to invoke the skill in a real project with GPU access:

```bash
cd /path/to/some/ml/project
/ml-research:autoresearch test-campaign
```

Walk through Phase 0 setup interactively. If the dialog flows, `config.json` is generated, and the baseline (experiment 001) dispatches an Experimenter that returns successfully, the integration is good. This step requires a real project + GPU and may be skipped if such an environment isn't available; the static checks in steps 1-4 are sufficient for the plan to be considered done.

- [ ] **Step 7: Commit any final adjustments and push**

If validation revealed issues you fixed:

```bash
git add -A
git commit -m "Address plugin validation issues"
```

If everything passed without changes, skip this step. Either way, the implementation plan is complete.

---

## Self-review checklist (run after writing all task content)

- [ ] Every spec section has a corresponding task — config.json, frontmatter schema, CSV, ideas.md, insights.md, all three subagents, Phase 0 dialog, Phase 1 loop, git choreography, debug loop, GPU monitoring, torch.compile cache, proxy-task discipline, acceptance criteria, retry policy, autonomy.
- [ ] No "TBD", "TODO", or "fill in later" anywhere.
- [ ] Cross-task type consistency: subagent names (`autoresearch-ideator/experimenter/reviewer`) appear identically in tasks 2-5 and the verify scripts.
- [ ] Each task's verify command is concrete and runnable.
- [ ] Files paths are absolute-from-repo-root and consistent across tasks.
