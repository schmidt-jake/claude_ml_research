# ml-research

A [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) hosting plugins for ML research on HPC.

## Plugins

### `ml-research`

Skills bundle for HPC-based ML research:

- **`slurm`** — Submit, monitor, and debug SLURM jobs; pick partitions; tune batch size; diagnose OOM/timeout/node errors.
- **`delta-cluster`** — NCSA Delta-specific guidance (partitions, charge rates, `/work` vs `/projects`, `bdhi` account). Composes with `slurm`.
- **`model-training`** — Staged test procedure to shake out a training loop before launching a full run.
- **`autoresearch`** — Autonomous iteration on model architecture, data augmentation, and objective functions via rapid small-scale experiments.

## Install

```shell
/plugin marketplace add <github-user>/ml_research
/plugin install ml-research@jschmidt
```

Once installed, skills are namespaced as `/ml-research:slurm`, `/ml-research:delta-cluster`, etc.

### Local development

```bash
claude --plugin-dir /path/to/ml_research/plugins/ml-research
```

Run `/reload-plugins` after edits.

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
            ├── delta-cluster/
            ├── model-training/
            └── slurm/
```
