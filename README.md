# ml-research

A [Claude Code plugin](https://code.claude.com/docs/en/plugins) bundling skills for ML research on HPC clusters.

## Skills

- **`slurm`** — Submit, monitor, and debug SLURM jobs; pick partitions; tune batch size; diagnose OOM/timeout/node errors.
- **`delta-cluster`** — NCSA Delta-specific guidance (partitions, charge rates, `/work` vs `/projects`, `bdhi` account). Composes with `slurm`.
- **`model-training`** — Staged test procedure to shake out a training loop before launching a full run.
- **`autoresearch`** — Autonomous iteration on model architecture, data augmentation, and objective functions via rapid small-scale experiments.

## Install

Test locally:

```bash
claude --plugin-dir /path/to/ml_research
```

Or install from a marketplace once published. Skills are namespaced as `/ml-research:<skill>` (e.g. `/ml-research:slurm`).

## Layout

```
ml_research/
├── .claude-plugin/plugin.json
└── skills/
    ├── autoresearch/
    │   ├── SKILL.md
    │   ├── config.yaml
    │   ├── scripts/
    │   └── templates/
    ├── delta-cluster/SKILL.md
    ├── model-training/SKILL.md
    └── slurm/SKILL.md
```
