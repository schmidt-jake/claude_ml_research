# ml-research

A [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) hosting plugins for ML research on HPC.

## Plugins

### `ml-research`

Skills bundle for HPC-based ML research:

- **`slurm`** — Submit, monitor, and debug SLURM jobs; pick partitions; tune batch size; diagnose OOM/timeout/node errors. Auto-detects the cluster via `scontrol` and loads the matching site reference from `slurm/clusters/` — ships with references for **NCSA Delta** (partitions, charge rates, `/work` vs `/projects`, account conventions) and **University of Utah CHPC** (account/partition/QOS triples, module system, scratch filesystems). Add another cluster by dropping a new file into `slurm/clusters/<name>.md` and updating the detection table in `slurm/SKILL.md`.
- **`model-training`** — Staged pre-flight test procedure (code correctness → learnability → GPU efficiency → fault tolerance) to shake out a training loop before launching a full run.
- **`autoresearch`** — Autonomous iteration on model architecture, data augmentation, and objective functions via rapid small-scale experiments.
- **`audit`** — Audit a PyTorch codebase for trace/compile, numerical-stability, autograd, distributed, and perf anti-patterns. Surveys recent PyTorch releases for modernization opportunities (live web research). Optional `--dynamic` mode runs `torch._dynamo.explain`, `TORCH_TRACE`+`tlparse`, autograd anomaly mode, profiler, memory snapshot, and FLOP counter on a single forward/backward, then emits a categorized report.

## Install

```shell
# GitHub shorthand
/plugin marketplace add schmidt-jake/claude_ml_research

# Or the full URL
/plugin marketplace add https://github.com/schmidt-jake/claude_ml_research

/plugin install ml-research@jschmidt
```

Once installed, skills are namespaced as `/ml-research:slurm`, `/ml-research:delta-cluster`, etc.

### Local development

```bash
claude --plugin-dir /path/to/ml_research/plugins/ml-research
```

Run `/reload-plugins` after edits.

### Validate manifests

Before pushing changes, run the [official linter](https://code.claude.com/docs/en/plugins-reference#debugging-and-development-tools) against both manifests:

```bash
claude plugin validate .                   # marketplace.json
claude plugin validate plugins/ml-research # plugin.json + skill/agent/hook frontmatter
```

A missing-`version` warning on `plugin.json` is expected — this plugin intentionally uses git-commit-SHA versioning during rapid iteration so every push delivers updates without manual bumps. See [Version management](https://code.claude.com/docs/en/plugins-reference#version-management). When the API stabilizes, switch to semver by setting `version` in `plugin.json` and tagging releases.

## Layout

```
ml_research/
├── .claude-plugin/
│   └── marketplace.json       # marketplace catalog
└── plugins/
    └── ml-research/
        ├── .claude-plugin/plugin.json
        └── skills/
            ├── autoresearch/
            ├── model-training/
            └── slurm/
                ├── SKILL.md
                └── clusters/
                    ├── chpc.md
                    └── delta.md
```
