---
name: audit
description: Audit a PyTorch codebase for trace/compile, numerical, autograd, distributed, and perf anti-patterns; surveys recent framework releases for modernization opportunities. Optional --dynamic mode runs framework introspection (torch._dynamo.explain, TORCH_TRACE+tlparse, autograd anomaly mode, profiler, memory snapshot, FLOP counter) on a single forward/backward. Use when the user says "audit", "lint", "review my model code for ML bugs", or before launching a long training run. Composes with slurm for cluster identification; complements (does not replace) model-training.
---

# Audit

You are auditing a PyTorch codebase for known anti-patterns and modernization opportunities. Run six phases in order. Findings without a qualifying citation are dropped.

## Invocation

```
/ml-research:audit                       # auto-detect targets, confirm, run
/ml-research:audit src/model.py          # explicit target(s); skip detection
/ml-research:audit src/ tests/integration  # multiple targets ok
/ml-research:audit --dynamic             # opt in to executing introspection tools
/ml-research:audit src/model.py --dynamic  # explicit targets + dynamic
```

`--dynamic` is the only flag in v1. With no positional args, the skill auto-detects targets (Phase 1) and asks the user to confirm. With targets supplied, detection is skipped.

## Phase 1 — Resolve targets

If positional args are present, treat them as the target list. Files are added directly; directories are recursively expanded with the glob below (excluding `tests/`, `__pycache__/`, `.venv/`, `node_modules/`, anything matching `.gitignore`).

If no args, propose a target list using these heuristics on the current working directory:

- **Editable model code:** files importing `torch.nn` or `torch` and defining `nn.Module` subclasses. Glob: `src/**/model*.py`, `src/**/net*.py`, `**/modules/*.py`.
- **Training loops:** files calling `loss.backward()` or `Trainer.fit` or `torch.distributed.init_process_group`. Glob: `src/**/train*.py`, `**/trainer*.py`, `scripts/train*.py`.
- **Distributed setup:** files calling `init_process_group`, `DistributedSampler`, `DistributedDataParallel`, `FSDP`, `DeviceMesh`.

Detect concretely:

```bash
grep -rl --include='*.py' -E '(class .*\(nn\.Module\)|class .*\(.*LightningModule\)|class .*\(.*pl\.LightningModule\)|loss\.backward\(\)|trainer\.fit|Trainer\.fit|init_process_group|DistributedDataParallel|FSDP|DeviceMesh)' src/ scripts/ 2>/dev/null
```

Present the proposal to the user as a confirmable list. Wait for confirmation or edits before proceeding to Phase 2.

If the proposal is empty, stop:

> "No PyTorch source files found under <cwd>. Pass explicit targets, e.g. `/ml-research:audit path/to/file.py`."

**Framework detection.** Only PyTorch is supported in v1. Detect with:

```bash
grep -lE '^(import torch|from torch)' <targets>
```

If no target matches, stop:

> "No `import torch` found in target files. Audit currently supports PyTorch only; reference files for other frameworks (`reference/jax.md`, `reference/lightning.md`) are not yet shipped."

## Phase 2 — Probe environment

Layered probe. Run each step; collect what works; skip what doesn't.

**(a) Hardware:**

```bash
nvidia-smi -q | head -200
lscpu | head -30
nvcc --version
scontrol show node "$HOSTNAME" 2>/dev/null
```

Pull GPU model + arch (e.g., `NVIDIA H100 80GB → Hopper`), GPU count, driver, CUDA version. CPU model + cores. CUDA toolkit version (may differ from runtime CUDA).

**(b) Cluster context (compose with `slurm` skill):**

If `which scontrol` succeeds, load the `/ml-research:slurm` skill — it identifies the cluster and reads node specs from the matching `clusters/<name>.md`. Skip if not on a cluster.

**(c) Framework + ecosystem:**

```bash
python -c "import torch.utils.collect_env as e; e.main()" 2>&1
```

This one call prints PyTorch version, CUDA, cuDNN, NCCL, OS, GPU model — primary source of truth for the framework stack.

Detect package manager and list ecosystem packages:

```bash
if [ -f pyproject.toml ] && grep -q '\[tool\.uv\]' pyproject.toml; then
  uv pip list
elif [ -f pyproject.toml ] || [ -f requirements.txt ]; then
  pip list
fi 2>/dev/null | grep -iE '^(transformer-engine|flash-attn|apex|deepspeed|xformers|triton|bitsandbytes|lightning|accelerate|torchao|tlparse) '
```

**(d) Fallback:** for anything still missing that affects the audit (e.g., GPU model unknown), ask the user once before continuing. Don't ask multiple questions; bundle them into one.

**How the environment shapes recommendations** (apply when interpreting findings, not as separate findings):

- `transformer-engine` present + Hopper GPU → consider FP8 paths.
- `flash-attn` < 3 + Hopper GPU → flag the version gap (FA3 ships proper Hopper kernels).
- `torch` < 2.4 → some `torch.compile` advice differs (default `fullgraph` behavior, `dynamic` semantics).
- No GPU + `--dynamic` → Phase 5 is skipped with a graceful message.

Persist the collected dictionary in your working memory; it feeds Phases 3, 4, and 5.

## Phase 3 — Static audit (inline)

For each target file, scan against the five categories defined in `${CLAUDE_SKILL_DIR}/reference/pytorch.md`. Read that file once at the start of Phase 3.

Emit findings of the form:

```
{ category, severity, file, line, snippet, why, fix, citation }
```

`category` ∈ {`compile`, `numerical`, `autograd`, `distributed`, `perf`}.

`severity` ∈ {`error`, `warning`, `info`}:

- **error** — correctness bug. NaN-prone, wrong-grad, distributed deadlock.
- **warning** — likely-suboptimal. Graph break, host-device sync in hot path, unguarded all-rank logging.
- **info** — tidiness. Vectorizable loops, deprecated API spelling.

`citation` is required. For static-phase findings, the citation comes from the entry's row in `reference/pytorch.md` (which itself must point to an upstream source). Findings whose reference entry has no citation are dropped silently.

**Detection technique.** Use `grep` with the patterns *already inline* in `reference/pytorch.md` — the bullets that read like regex syntax (e.g., `\.item\(\)`, `\.tolist\(\)`). Do **not** synthesize new regexes from prose-only bullets (e.g., "data-dependent control flow on tensor values"). Prose bullets describe failure modes that need an LLM read of the code or — better — a Phase 5 dynamic introspection pass; trying to grep them produces noisy false positives. If a prose bullet has no inline regex, drop it from the static phase and rely on Phase 5 to catch it (when `--dynamic` is set). When the user runs without `--dynamic`, prose-only categories are not detected this pass — note this in the report's "Run summary" so the user knows. Pattern-match conservatively: if a candidate is ambiguous (e.g., `.item()` *might* be inside a compiled region but you can't tell from grep alone), prefer false positives over false negatives at static phase — Phase 5 dynamic introspection (when run) will confirm or contradict. Note ambiguity in `why`.

**Hot-path heuristic.** Some categories (perf, distributed) only matter inside the training loop's hot path. Treat any function with `loss.backward()` or `Trainer.fit` reachable from it as hot path. Ops in `__init__`, top-level module construction, or test files are not hot path — drop perf/distributed findings on those.

Aggregate all static findings and hold them for Phase 6.

## Phase 4 — Modernize (subagent dispatch)

Dispatch `audit-modernize` once. The subagent does live web research (PyTorch release notes, blog, GitHub) and intent-matches new APIs against the user's code.

Dispatch shape:

```
subagent_type: ml-research:audit-modernize
prompt:
  Detected framework: pytorch
  Detected versions: torch=<v>, ecosystem=<...>
  Hardware: <gpu model + arch + cuda + driver>
  Target files (full content embedded):
      <file1 contents>
      ---
      <file2 contents>
      ---
      ...
  Reference seed (modernization seeds section of reference/pytorch.md):
      <embedded verbatim>
```

Embed full file content (not just paths) — the subagent can't see your filesystem.

**Validate the return.** The subagent returns JSON with `findings: [...]` and `research_summary: "..."`. Apply checks in two tiers:

*Shape checks* (failure → retry once with the prefix `"Your prior return was malformed: <reason>. Please return per the contract."`; on second failure, drop the modernize phase and log to "Skipped passes"):
- top-level object parses as JSON
- `findings` is a list (possibly empty)
- `research_summary` is a non-empty string

*Content checks* (failure → drop offending findings, keep the rest, no retry):
- drop findings missing `citation`, `category`, `severity`, `file`, `line`, `snippet`, `why`, or `fix`
- drop findings whose `category != "modernize"` or `severity != "info"`
- if `len(findings) > 15` after the drops, keep the first 15 (the subagent's own ranking)

Aggregate the surviving validated findings for Phase 6.

## Phase 5 — Dynamic introspection (opt-in)

**Skip Phase 5 entirely unless `--dynamic` was passed.** When skipped, emit nothing to the report — `Modes run` line will say `static, modernize`.

When `--dynamic` is set, verify pre-requisites in this order:

**(1) Local GPU reachable:**

```bash
nvidia-smi --query-gpu=count --format=csv,noheader 2>/dev/null
```

If empty or zero, skip Phase 5. Print to the report a "Skipped passes (dynamic mode)" entry naming each introspection command the user can run themselves with the citation from `reference/pytorch.md`'s "Introspection runbooks" table. Do not dispatch the subagent.

If on a SLURM cluster with no local GPU: same skip. Do not submit an sbatch — that latency model doesn't fit a one-shot audit.

**(2) Introspection entrypoint:**

The subagent needs one of:

- **(a) Function path** `module.path:function_name` returning `(model: nn.Module, example_inputs: tuple[Tensor, ...])`.
- **(b) Standalone script** that already does one `model(*inputs).sum().backward()` on tiny inputs.

Search the target files for either. Heuristic regexes:

```bash
grep -nE '^def build_[a-z_]+\(.*\) *-> *(nn\.Module|.*Module)' <targets>
grep -nE 'def configure_model\(self' <targets>           # LightningModule
ls scripts/audit_introspection.py 2>/dev/null
ls tests/test_*forward*.py 2>/dev/null
```

When `ls scripts/audit_introspection.py` matches, **read its first line** before proposing it. If the first line equals the canonical stub docstring `"""Audit introspection entrypoint. Fill in tensor shapes and dtypes."""`, the user previously accepted a scaffold but has not filled it in — do not propose it as an entrypoint. Print a reminder ("`scripts/audit_introspection.py` exists but still has unfilled `# TODO:` markers — edit it, then re-run with `--dynamic`.") and stop Phase 5 here.

When the heuristic finds a function-path entrypoint or `audit_introspection.py` that has been hand-edited (first line ≠ the canonical stub docstring), propose it; if confirmed, encode as the entrypoint dict and proceed to dispatch.

If nothing is found, the main agent offers to scaffold `scripts/audit_introspection.py` from the user's model construction code, with `# TODO:` markers where the user fills in tensor shapes/dtypes. The user can run audit again with `--dynamic` after editing.

**(3) Dispatch `audit-dynamic`:**

```
subagent_type: ml-research:audit-dynamic
prompt:
  Environment: <full Phase 2 dictionary embedded as JSON>
  Target files (full content embedded):
      <files>
  Introspection entrypoint:
      type: function | script
      value: <module:function or path/to/script>
  Static-phase findings (relevant to dynamic checks):
      <JSON list — lets the subagent skip non-applicable passes>
```

**Validate the return.** Apply the same two-tier policy as Phase 4:

*Shape checks* (failure → retry once; on second failure, log to "Skipped passes (dynamic mode)" and continue with whatever passes did succeed):
- top-level object parses as JSON
- `findings` is a list (possibly empty)
- `passes_run`, `passes_skipped`, and `summary_metrics` are present

*Content checks* (failure → drop offending findings, keep the rest):
- drop findings missing `citation` or `evidence_path`
- drop findings whose `category` is not one of the five static categories (`compile`, `numerical`, `autograd`, `distributed`, `perf`)

Aggregate the surviving validated findings, the `passes_skipped` map, and the `summary_metrics` for Phase 6.

## Phase 6 — Report assembly

In-conversation only. Merge findings from Phases 3, 4, 5. Group by severity, then by category within each severity. Order: errors → warnings → info → skipped → summary. Empty severity sections are omitted (no "Errors (0)").

Within a severity section, order categories: `compile`, `numerical`, `autograd`, `distributed`, `perf`, `modernize`.

Format:

```
# Audit report

Scope: <comma-separated target files>
Framework: pytorch <version>
Hardware: <gpu model, count, cuda>, <cpu sketch>
Ecosystem: <flash-attn 2.5.0, transformer-engine 1.7.0, ...>   # only relevant ML packages
Modes run: static, modernize, dynamic   (or: static, modernize)

## Errors (N)
[bug-class issues — must fix; correctness or distributed-deadlock risk]

  ▸ src/model.py:142  [autograd]
    .data assignment on a Parameter — bypasses autograd registration; gradient
    will not flow through this op.
    Fix:  param.copy_(new) under torch.no_grad(), or rebind via nn.Parameter(new).
    Cite: https://pytorch.org/docs/stable/notes/autograd.html#in-place-operations-with-autograd

## Warnings (N)
[likely-suboptimal — fix when you can]

  ▸ src/train.py:88   [compile]
    print(loss.item()) inside the compiled region — graph break confirmed by
    torch._dynamo.explain (3 breaks total in this region).
    Fix:  hoist logging out of the compiled fn, or torch._dynamo.disable on
          the logging branch.
    Cite: https://pytorch.org/docs/stable/torch.compiler_troubleshooting.html#graph-breaks
    Trace: /tmp/audit-dynamic-12345/dynamo_explain.txt

## Info (N)
[modernization / tidiness — opportunistic]

  ▸ src/model.py:64   [modernize]
    Manual scaled-dot-product attention — torch ≥ 2.0 ships
    F.scaled_dot_product_attention with FlashAttention/mem-efficient backends.
    Fix:  torch.nn.functional.scaled_dot_product_attention(q, k, v, is_causal=True)
    Cite: https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html

## Skipped passes (dynamic mode)
- trace_tlparse: tlparse not installed. Install: `uv pip install tlparse`.
- flop_counter: no GEMM ops detected in target files.

## Run summary
Static:    18 findings (2 errors, 9 warnings, 7 info)
Modernize: 4 findings (0 errors, 0 warnings, 4 info) — surveyed: torch 2.4/2.5 release notes, torchao 0.5
Dynamic:   3 findings (0 errors, 3 warnings, 0 info) — passes_run: dynamo_explain, compile_logs, anomaly, profiler, memory
                                                       graph_breaks=3, host_device_syncs_per_step=7
```

Print the report. The skill ends here — no follow-up prompts to the user, no edits, no commits.

## Citation policy

Every finding (static, modernize, dynamic) must carry ≥1 citation from either:

- **Official framework sources:** `pytorch.org/docs`, `pytorch.org/blog`, `pytorch.org/tutorials`, `github.com/pytorch/pytorch` (release pages, source-code permalinks, issues, PRs), `github.com/pytorch/<satellite>`, `dev-discuss.pytorch.org`.
- **Reputable third-party:** HuggingFace docs, NVIDIA developer blogs, FlashAttention/DeepSpeed/vLLM/Lightning docs, well-known systems papers on arXiv.

Findings without a qualifying citation are dropped from the report. Static findings inherit citations from `reference/pytorch.md`; subagent findings carry their own per the agent definitions.

## Composition with other skills

- **`slurm`** — auto-loaded by Phase 2's hardware probe (cluster identification + node specs). Not used by dynamic mode.
- **`model-training`** — explicitly *not* a substitute. `audit` catches issues by reading code and running framework introspection on a single forward/backward; `model-training` validates the loop end-to-end by running it (correctness, learnability, GPU efficiency, fault tolerance). Use `audit` *before* `model-training`, not instead of it. After audit's findings are addressed, run `model-training` for an empirical pass.
- **`autoresearch`** — orthogonal. Audit is one-shot; autoresearch is a long-running loop. They don't compose.

## Out of scope

This v1 deliberately defers:

- **Multi-rank distributed introspection.** A real distributed forward requires spawning workers. Single-process only.
- **Editing user code.** Subagents are return-only. The user reads the report and decides what to act on.
- **SLURM-launched dynamic mode.** Latency model doesn't fit a one-shot audit; user runs the printed introspection commands themselves if no local GPU.
- **Frameworks other than PyTorch.** Architecture supports them via `reference/<framework>.md`; reference files are not yet authored.
- **Persistent reports.** Output is in-conversation only.

## Adding a new framework (future)

1. Author `reference/<framework>.md` with the same five categories (compile/numerical/autograd/distributed/perf), each entry citing an upstream source. Include a "Modernization seeds" section and an "Introspection runbooks" section.
2. Add a one-line entry in Phase 1's framework-detection grep (e.g., `import jax`, `import lightning`).
3. Add framework-specific introspection passes to `audit-dynamic.md` if applicable (JAX has `jax.make_jaxpr`, `jax.jit` cache stats).
4. Update this `description` line and `README.md` to list the supported frameworks.

The core skill (target resolution, report assembly, citation policy, subagent dispatch) does not change.
