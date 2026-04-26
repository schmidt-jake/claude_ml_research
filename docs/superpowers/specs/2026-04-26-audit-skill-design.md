# Audit skill — design

Date: 2026-04-26
Status: spec

## Motivation

The `ml-research` plugin marketplace has three skills today: `slurm` (cluster
ops), `model-training` (runtime smoke tests), `autoresearch` (long-running
experiment loop). None of them statically audits ML source code for the
recurring failure modes — graph breaks, fp16 overflow, autograd footguns,
distributed deadlocks, perf anti-patterns — nor surfaces newer framework APIs
that obviate hand-rolled implementations.

`audit` fills that gap. It reads the user's code, matches it against curated
PyTorch anti-patterns, surveys recent framework releases for modernization
opportunities the user's code is implicitly asking for, optionally runs the
framework's own introspection tools (`torch._dynamo.explain`,
`TORCH_TRACE`+`tlparse`, autograd anomaly mode, profiler, memory snapshot,
FLOP counter) on a single forward/backward, and emits a categorized
in-conversation report.

Out of scope: editing code, validating training-loop correctness end-to-end
(use `model-training`), running long autonomous loops (use `autoresearch`),
multi-rank distributed introspection (deferred — single-process only in v1).

## Architecture

```
Main agent (audit skill, monolithic orchestrator)
    │
    ├── Phase 1: resolve targets         (inline; arg → autodetect+confirm)
    ├── Phase 2: probe environment       (inline; layered: nvidia-smi → slurm → ask)
    ├── Phase 3: static audit            (inline; reads targets, matches reference/<framework>.md)
    ├── Phase 4: dispatches ──► audit-modernize  (subagent: live web research, intent-match)
    ├── Phase 5: (--dynamic) ──► audit-dynamic   (subagent: runs introspection tools)
    └── Phase 6: emit merged report      (inline; in-conversation, categorized)

plugins/ml-research/skills/audit/
    ├── SKILL.md
    └── reference/
        └── pytorch.md          # static anti-patterns + introspection runbooks (per-framework)

plugins/ml-research/agents/
    ├── audit-modernize.md      # live framework-news researcher
    └── audit-dynamic.md        # introspection-tool runner
```

The skill is monolithic for control flow and inline for the static work
(reading code is cheap and the main agent has to load it anyway). The two
context-heavy phases — live web research and running introspection tools —
are dispatched to single-purpose subagents whose contexts evaporate on
return.

### Division of responsibility

| Actor | Scope | Reads | Writes |
|---|---|---|---|
| **Main agent** | Phases 1–3, 6; dispatches 4 and (opt-in) 5 | Target files, `reference/<framework>.md`, environment-probe outputs, subagent returns | Nothing on disk; report goes to chat |
| **`audit-modernize`** | Live web research; intent-match against new APIs | Target file content (embedded by main agent), `reference/<framework>.md` modernization seeds (embedded), live `WebSearch`/`WebFetch` | Nothing on disk; structured findings return |
| **`audit-dynamic`** | Run framework introspection on one forward/backward | Target files (already embedded); user's introspection entrypoint; framework introspection tool output | `/tmp/audit-dynamic-<pid>/` for trace artifacts; structured digest return |

### Why a subagent for modernize and dynamic, but not the static categories

`autoresearch` uses one subagent per role because the loop runs indefinitely;
even a small per-iteration context cost compounds. `audit` runs once and
finishes. The only context costs that justify a subagent are the genuinely
heavy ones:

- **Modernize:** `WebSearch` and `WebFetch` against release notes, blogs, and
  GitHub. The raw HTML and the per-fetch deliberation pollute main-agent
  context, and the *result* is small (a list of findings).
- **Dynamic:** introspection tools emit multi-megabyte traces. The subagent
  parses them and returns a small digest.

The five static categories (compile, numerical, autograd, distributed, perf)
are pattern matches against `reference/<framework>.md` and run cheaply
inline.

## Invocation

```
/ml-research:audit                       # auto-detect targets, confirm, run
/ml-research:audit src/model.py          # explicit target(s); skip detection
/ml-research:audit src/ tests/integration  # multiple targets ok
/ml-research:audit --dynamic             # opt in to executing introspection tools
/ml-research:audit src/model.py --dynamic  # explicit targets + dynamic
```

`--dynamic` is the only flag in v1. With no positional args, the skill
auto-detects targets (Phase 1) and asks the user to confirm. With targets
supplied, detection is skipped.

## Phase 1 — Resolve targets

If positional args are present, treat them as the target list (files or
directories — directories are recursively expanded with the glob below).

If no args, propose a target list using these heuristics:

- **Editable model code:** files importing `torch.nn` or `torch` and
  defining `nn.Module` subclasses. Glob: `src/**/model*.py`,
  `src/**/net*.py`, `**/modules/*.py`.
- **Training loops:** files calling `loss.backward()` or `Trainer.fit` or
  `torch.distributed.init_process_group`. Glob: `src/**/train*.py`,
  `**/trainer*.py`, `scripts/train*.py`.
- **Distributed setup:** files calling `init_process_group`,
  `DistributedSampler`, `DistributedDataParallel`, `FSDP`, `DeviceMesh`.

The proposal is presented as a confirmable list; the user can edit it
before Phase 2 starts.

If the proposal is empty, the skill stops with: "No PyTorch source files
found under <cwd>. Pass explicit targets, e.g. `/ml-research:audit
path/to/file.py`."

**Framework detection:** `grep -l "^import torch\|^from torch" <targets>`.
If none match, stop with: "No `import torch` found in target files. Audit
currently supports PyTorch only; reference files for other frameworks
(`reference/jax.md`, `reference/lightning.md`) are not yet shipped."

## Phase 2 — Probe environment

Layered probe. Run each step; collect what works; skip what doesn't.

**(a) Hardware:**
- `nvidia-smi -q | head -200` — GPU model, count, driver, CUDA, memory.
- `lscpu | head -30` — CPU model, sockets, cores.
- `nvcc --version` — CUDA toolkit version.
- `scontrol show node $HOSTNAME 2>/dev/null` — if SLURM, node-level info.

**(b) Cluster context (compose with `slurm` skill):**
- If `which scontrol` succeeds, load `/ml-research:slurm` to identify the
  cluster and read node specs from the matching `clusters/<name>.md`. Skip
  if not on a cluster.

**(c) Framework + ecosystem:**
- `python -c "import torch.utils.collect_env as e; e.main()"` — one call
  prints PyTorch version, CUDA, cuDNN, NCCL, OS, GPU model.
- Detect package manager: `pyproject.toml` with `[tool.uv]` → `uv pip list`;
  `pyproject.toml` only → `pip list`; neither → skip.
- Filter the package list for ML-relevant ecosystem packages that change
  recommendations: `transformer-engine`, `flash-attn`, `apex`, `deepspeed`,
  `xformers`, `triton`, `bitsandbytes`, `lightning`, `accelerate`, `torchao`,
  `tlparse`.

**(d) Fallback:** for anything still missing that affects the audit (e.g.,
GPU model unknown), ask the user once before continuing.

The collected environment dictionary feeds Phases 3, 4, and 5. Examples of
how the environment shapes recommendations:

- `transformer-engine` present + Hopper GPU → consider FP8 paths.
- `flash-attn` < 3 + Hopper GPU → flag the version gap (FA3 ships proper
  Hopper kernels).
- `torch` < 2.4 → some `torch.compile` advice differs (different default
  fullgraph behavior, different `dynamic` semantics).
- No GPU + `--dynamic` → Phase 5 is skipped with a graceful message.

## Phase 3 — Static audit (inline)

For each target file, scan against the five categories defined in
`reference/<framework>.md`. Emit findings of the form:

```
{ category, severity, file, line, snippet, why, fix, citation }
```

`category` ∈ {`compile`, `numerical`, `autograd`, `distributed`, `perf`}.
`severity` ∈ {`error`, `warning`, `info`}:

- **error**: correctness bug — NaN-prone, wrong-grad, distributed deadlock.
- **warning**: likely-suboptimal — graph break, host-device sync in hot path,
  unguarded all-rank logging.
- **info**: tidiness — vectorizable loops, deprecated API spelling.

`citation` is required. For static-phase findings, the citation comes from
the entry's row in `reference/<framework>.md` (which itself must point to an
upstream source). Findings whose reference entry has no citation are dropped.

### `reference/pytorch.md` structure

```
# PyTorch audit reference

## 1. Trace / compile (torch.compile, torch.export, FX)
   - Symptoms: graph breaks, recompilations, fullgraph=True failures
   - Anti-patterns to grep for:
       * .item() / .tolist() / Python int() inside compiled regions
       * data-dependent control flow on tensor values
       * isinstance checks on tensors, dynamic shape branches without mark_dynamic
       * print / breakpoint / logging.info inside the compiled region
       * mutating module attributes inside forward
   - Recommended introspection (cite to user / hand to audit-dynamic):
       torch._dynamo.explain(model)(*example_inputs)
       TORCH_LOGS=graph_breaks,recompiles
       TORCH_TRACE=/tmp/trace tlparse /tmp/trace
   - Citations: pytorch.org/docs/stable/torch.compiler_troubleshooting.html

## 2. Numerical stability under reduced precision
   - Anti-patterns:
       * exp / log / softmax over fp16/bf16 logits without upcast
       * sum / mean reductions over very large tensors in fp16
       * eps=1e-8 in fp16 norms (below smallest representable)
       * (1 - x) for small x in fp16; use log-space or fp32 cast
       * matmul accumulators left at default when training in bf16
   - Citations: pytorch.org/docs/stable/notes/numerical_accuracy.html;
     pytorch.org/blog/accelerating-large-language-models/ (mixed precision section)

## 3. Gradient / autograd
   - Anti-patterns:
       * in-place op on a leaf tensor with requires_grad=True
       * .data assignment on a parameter
       * .detach() then expecting gradients to flow
       * retain_graph=True in a training loop (usually wrong)
       * loss.backward() called twice without zero_grad / retain_graph
       * gradient clipping after optimizer.step (order bug)
   - Citations: pytorch.org/docs/stable/notes/autograd.html#in-place-operations-on-tensors

## 4. Distributed
   - Anti-patterns:
       * unguarded print/log/save on all ranks (should rank==0)
       * dataset shuffling without DistributedSampler.set_epoch
       * .item() inside a forward hook under DDP (sync stall)
       * NCCL: missing barrier before checkpoint save, missing
         init_process_group timeout, NCCL_BLOCKING_WAIT unset
       * gradient reduction inside no_sync context but outside accumulation
   - Citations: pytorch.org/docs/stable/notes/ddp.html;
     pytorch.org/docs/stable/distributed.html#torch.distributed.barrier

## 5. Inefficient patterns
   - Anti-patterns:
       * Python for-loop over a batch dimension (vectorize)
       * stacking lists of tensors per step (use pre-alloc + index_copy_)
       * .cpu() / .numpy() inside the training loop (host-device sync)
       * cat in a hot path where stack/zeros + index works
       * nn.Linear on contiguous-after-transpose memory
   - Citations: pytorch.org/docs/stable/notes/cuda.html#asynchronous-execution

## Modernization seeds (small, hand-curated; live research extends this)
   - torch.nn.functional.scaled_dot_product_attention with backend hints
   - torch.compile + dynamic=True for variable shapes
   - torch.utils.flop_counter for shape-level profiling
   - torch.distributed.device_mesh API over manual device_ids
   - torchao.float8 on Hopper (if installed)
   - Citations: per-entry, on the line they appear
```

Every entry's row carries an inline citation URL. The static audit's "fix"
text and "citation" field are populated directly from these rows.

## Phase 4 — Modernize (subagent: `audit-modernize`)

### Dispatch shape

```
subagent_type: ml-research:audit-modernize
prompt:
  Detected framework: pytorch
  Detected versions: torch=<v>, ecosystem=<flash-attn=2.5.0, transformer-engine=1.7.0, ...>
  Hardware: <gpu model + arch + cuda + driver>
  Target files (full content embedded):
      <file1>
      ---
      <file2>
      ---
      ...
  Reference seed (modernization seeds section of reference/pytorch.md):
      <embedded>

  Task: Identify modernization opportunities. For each, return:
      { category: "modernize", severity: "info", file, line, snippet, why, fix, citation }
  Each finding requires ≥1 citation per the policy in the agent definition.
  Drop findings without one. Return at most 15 findings, ranked by impact.
```

### Subagent loop

1. Read PyTorch release notes for versions newer than the user's installed
   `torch` (`pytorch.org/blog`, `github.com/pytorch/pytorch/releases`,
   `dev-discuss.pytorch.org`) — focus on items that introduce new public
   APIs.
2. For each candidate new API/pattern, scan the embedded target files for
   code whose *intent* matches (manual implementations of what the new API
   now does in one call). Examples:
   - User loops over batch with manual padding → `nn.utils.rnn.pad_sequence`
     or `torch.nested`.
   - User manually sets up `device_ids` per-rank →
     `torch.distributed.device_mesh`.
   - User has a custom AMP scaler → `torch.amp.autocast` + `GradScaler`
     deprecation path.
   - User implements own attention →
     `torch.nn.functional.scaled_dot_product_attention` with backend hints.
   - User does manual Float8 quant → `torchao.float8` if Hopper.
3. For each ecosystem package installed (e.g. `transformer-engine`), check
   that package's release notes and docs the same way.
4. Discard candidates without a clear intent match.
5. Return the structured list. Each entry must have a citation URL.

### Hard rules in `audit-modernize.md`

- The subagent does not edit code. Return-only.
- Every modernize finding has `severity: "info"`. Modernization is
  opportunistic by definition; a broken/removed API is a static-phase
  finding (catalogued in `reference/pytorch.md`), not a modernization gap.
- Drop any finding whose claim is "X is faster" without a benchmark cite, or
  "X is the new way" without a release-note / docs cite.
- Cap web fetches: at most 12 per dispatch.
- Citation must be from official framework sources (docs, blog, GitHub
  repo/releases/issues/PRs) or reputable third-party (HuggingFace, NVIDIA
  blogs, FlashAttention/DeepSpeed/vLLM/Lightning docs, well-known systems
  papers).
- Return JSON-shaped object, not free-form prose.

### Return shape

```json
{
  "findings": [
    {
      "category": "modernize",
      "severity": "info",
      "file": "src/model.py",
      "line": 142,
      "snippet": "for i in range(B): out.append(F.linear(x[i], W[i]))",
      "why": "Per-batch Python loop materializes B kernel launches.",
      "fix": "torch.bmm(x, W.transpose(-1, -2)) or torch.einsum('bij,bjk->bik', x, W).",
      "citation": "https://pytorch.org/docs/stable/generated/torch.bmm.html"
    }
  ],
  "research_summary": "Surveyed: torch 2.4 release notes, torch 2.5 release notes, torchao 0.5 release. 12 fetches consumed."
}
```

Main agent validates the return: every finding has a non-empty citation;
shape matches; ≤15 findings. On malformed return: re-dispatch once with the
prefix "Your prior return was malformed: <reason>." If it fails twice, log a
single warning to the report's "Skipped passes" section and continue.

## Phase 5 — Dynamic introspection (opt-in, subagent: `audit-dynamic`)

Triggered only when the user passes `--dynamic`.

### Pre-requisites

The main agent verifies before dispatch:

1. **Local GPU reachable:** `nvidia-smi` returns at least one device. If not,
   skip Phase 5; report the introspection commands the user can run
   themselves (each with a citation), with a note that dynamic mode is
   skipped.

2. **Introspection entrypoint:** the subagent needs one of:
   - **(a) Function path** `module.path:function_name` — must return
     `(model: nn.Module, example_inputs: tuple[Tensor, ...])`.
   - **(b) Standalone script** that already does one
     `model(*inputs).sum().backward()` on tiny inputs.

   The main agent first searches the target files for such an entrypoint
   (heuristic: any `def build_*` returning an `nn.Module`, any
   `LightningModule.configure_model`, or any test under `tests/` that
   constructs the model). If found, propose it; if confirmed, use it.

   If none found, the main agent offers to scaffold
   `scripts/audit_introspection.py` from the user's model construction code,
   with a `TODO` block where the user fills in tensor shapes/dtypes. The
   user can run audit again with `--dynamic` after editing.

**No SLURM submission for v1.** A dispatched sbatch + minutes-long wait does
not fit a one-shot audit. If the user is on a SLURM cluster with no local
GPU, the skill prints the introspection commands and skips.

### Dispatch shape

```
subagent_type: ml-research:audit-dynamic
prompt:
  Environment: <full Phase 2 dictionary embedded>
  Target files (full content embedded):
      <files>
  Introspection entrypoint:
      type: function | script
      value: <module:function or path/to/script>
  Static-phase findings (relevant to dynamic checks):
      <embedded; lets the subagent skip passes that don't apply, e.g.
       skip dynamo if no torch.compile call exists>

  Task: Run the introspection passes listed in the agent definition,
  conditional on applicability. Return a digest with parsed findings and
  evidence paths. Citations required per policy.
```

### Introspection passes

| Pass | Command sketch | Catches | Citation |
|---|---|---|---|
| `dynamo_explain` | `torch._dynamo.explain(model)(*ex)` | graph breaks, reasons, suggested fixes | pytorch.org/docs/stable/torch.compiler_troubleshooting.html |
| `compile_logs` | `TORCH_LOGS=graph_breaks,recompiles python harness.py` | recompilation triggers, dynamic-shape misses | same |
| `trace_tlparse` | `TORCH_TRACE=/tmp/t python harness.py && tlparse /tmp/t` | full compile timeline, kernel fusions missed | github.com/pytorch/tlparse |
| `anomaly` | `with torch.autograd.detect_anomaly(): loss.backward()` | NaN/inf in grad, in-place leaf modification | pytorch.org/docs/stable/autograd.html#anomaly-detection |
| `profiler` | `torch.profiler.profile(...)` over 5 steps | top ops by self-CUDA time, host↔device syncs (`aten::item`/`aten::nonzero` in hot path) | pytorch.org/docs/stable/profiler.html |
| `memory` | `torch.cuda.memory._record_memory_history()` then `_dump_snapshot()` | allocator fragmentation, peak allocations, leaks | pytorch.org/docs/stable/torch_cuda_memory.html |
| `flop_counter` | `with FlopCounterMode(): model(*ex)` | per-op FLOPs vs. peak; under-utilized GEMMs | github.com/pytorch/pytorch source for `torch.utils.flop_counter` |

Each pass is conditional on the static findings:

- Skip `dynamo_explain`, `compile_logs`, `trace_tlparse` if no
  `torch.compile` / `@torch.compile` / `torch._dynamo` call exists in
  targets.
- Skip `anomaly` if no `loss.backward()` reachable from the entrypoint.
- Skip `flop_counter` if no `nn.Linear`/`nn.Conv*`/`F.linear`/`F.conv*` /
  `@` / `bmm`/`einsum` in targets.

### Hard rules in `audit-dynamic.md`

- Each pass runs as a separate subprocess wrapped in `timeout 90s`. A hung
  pass is dropped with a one-line note in `passes_skipped`; it never blocks
  the whole subagent.
- Total wall-clock cap ~5 minutes.
- Artifacts go to `/tmp/audit-dynamic-<pid>/`. Trace files larger than 100 MB
  are truncated (or summarized + deleted) before return; the digest still
  references the path for user inspection.
- Citation rule applies. Default citation per pass is the row above.
- Do not edit user code.

### Return shape

```json
{
  "passes_run": ["dynamo_explain", "compile_logs", "anomaly", "profiler", "memory"],
  "passes_skipped": {"trace_tlparse": "tlparse not installed", "flop_counter": "no GEMM in graph"},
  "findings": [
    {
      "category": "compile",
      "severity": "warning",
      "file": "src/model.py",
      "line": 87,
      "snippet": "if mask.sum().item() > 0:",
      "why": "Graph break: data-dependent control flow on a tensor value (.item() forces a sync and exits the compiled region). Dynamo confirms break here.",
      "fix": "Use torch.where or mask.any() with a non-data-dependent branch.",
      "citation": "https://pytorch.org/docs/stable/torch.compiler_troubleshooting.html#graph-breaks",
      "evidence_path": "/tmp/audit-dynamic-12345/dynamo_explain.txt"
    }
  ],
  "summary_metrics": {
    "graph_breaks": 3,
    "recompiles": 1,
    "peak_gpu_mem_mb": 4823,
    "host_device_syncs_per_step": 7
  }
}
```

Main agent applies the same return validation as Phase 4.

## Phase 6 — Report assembly

In-conversation only. Merge findings from Phases 3, 4, 5. Group by
**severity → category**. Order: errors → warnings → info → skipped → summary.
Empty sections are omitted.

```
# Audit report

Scope: <comma-separated target files or globs>
Framework: pytorch <version>
Hardware: <gpu model, count, cuda>, <cpu sketch>
Ecosystem: <flash-attn 2.5.0, transformer-engine 1.7.0, ...>
Modes run: static, modernize, dynamic   (or: static, modernize)

## Errors (N)
[bug-class issues — must fix; correctness or distributed-deadlock risk]

  ▸ src/model.py:142  [autograd]
    .data assignment on a Parameter — bypasses autograd registration; gradient
    will not flow through this op.
    Fix:  param.copy_(new) under torch.no_grad(), or rebind via nn.Parameter(new).
    Cite: https://pytorch.org/docs/stable/notes/autograd.html#in-place-operations-on-tensors

  ▸ ...

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
- trace_tlparse: tlparse not installed.  Install: `uv pip install tlparse`.

## Run summary
Static:    18 findings (2 errors, 9 warnings, 7 info)
Modernize: 4 findings (0 errors, 0 warnings, 4 info) — surveyed: torch 2.4/2.5 release notes, torchao 0.5
Dynamic:   3 findings (0 errors, 3 warnings, 0 info) — passes_run: dynamo_explain, compile_logs, anomaly, profiler, memory
                                                       graph_breaks=3, host_device_syncs_per_step=7
```

## Citation policy (applied at every phase)

Every finding (static, modernize, dynamic) must carry ≥1 citation from
either:

- **(a) Official framework sources:** docs (pytorch.org/docs), official blog
  (pytorch.org/blog), GitHub repo (issues/PRs/release notes/source code
  comments), framework dev forum.
- **(b) Reputable third-party:** library implementation/docs (HuggingFace
  transformers, NVIDIA/apex, Lightning, FlashAttention, DeepSpeed, vLLM,
  NVIDIA technical blogs), well-known systems papers, kernel-author
  write-ups.

Findings without a qualifying citation are dropped from the report. The
main agent enforces this on subagent returns; the reference file enforces it
on static-phase findings.

## Composition with other skills

- **`slurm`** — auto-loaded only by Phase 2's hardware probe (cluster
  identification + node specs from `clusters/<name>.md`). Not used by
  dynamic mode.
- **`model-training`** — explicitly *not* a substitute. SKILL.md says: audit
  catches issues by reading code and running framework introspection on a
  single forward/backward; `model-training` validates correctness,
  learnability, GPU efficiency, and fault tolerance by running an actual
  training loop. Use `audit` before `model-training`, not instead of it.
- **`autoresearch`** — orthogonal. Audit is one-shot; autoresearch is a
  long-running loop.

## Extension: adding a new framework

Adding `reference/jax.md` or `reference/lightning.md` later requires:

1. Author the reference file with the same five categories
   (compile/numerical/autograd/distributed/perf), each entry citing an
   upstream source.
2. Add a one-line entry in Phase 2's framework-detection table mapping a
   grep pattern (`import jax`, `import lightning`) to the reference file.
3. Add framework-specific introspection passes to `audit-dynamic.md` if
   applicable (JAX has `jax.make_jaxpr`, `jax.jit` cache stats, etc.).
4. Update the SKILL.md description string to list the supported
   frameworks.

The core skill (target resolution, report assembly, citation policy,
subagent dispatch) does not change.

## Out of scope for v1

- **Multi-rank distributed introspection.** A real distributed forward
  requires spawning workers, and the failure modes (NCCL hangs, rank-zero
  divergence) are different from single-process. Defer.
- **Editing user code.** Subagents are return-only. The user reads the
  report and decides what to act on. A future "apply fix" mode could be a
  separate skill.
- **SLURM-launched dynamic mode.** Latency model doesn't fit a one-shot
  audit.
- **Frameworks other than PyTorch.** Architecture supports them; reference
  files are not yet authored.
- **Persistent reports.** Output is in-conversation only. If the user wants
  a file, they can copy-paste; or a future flag can add file output.
