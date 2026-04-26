# Audit skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new `audit` skill in the `ml-research` plugin that audits PyTorch codebases for compile/numerical/autograd/distributed/perf issues, surveys recent framework releases for modernization opportunities, optionally runs framework introspection tools, and emits a categorized in-conversation report — per the design at `docs/superpowers/specs/2026-04-26-audit-skill-design.md`.

**Architecture:** Monolithic skill (`skills/audit/SKILL.md`) for the six-phase orchestration; per-framework anti-patterns and citations in `skills/audit/reference/<framework>.md` (PyTorch only in v1); two subagents (`agents/audit-modernize.md`, `agents/audit-dynamic.md`) handling the context-heavy live-research and introspection-execution phases respectively.

**Tech Stack:** Markdown with YAML frontmatter (skill + agents), no Python or build steps. Verification is by `claude plugin validate` plus YAML/markdown structure checks.

**Spec:** `docs/superpowers/specs/2026-04-26-audit-skill-design.md` is the source of truth. Each task's authoring step references the spec sections that govern its file. When the plan and spec disagree, the spec wins.

---

## File structure

After this plan completes:

```
plugins/ml-research/
├── .claude-plugin/plugin.json                # MODIFIED (description + keywords)
├── agents/
│   ├── autoresearch-experimenter.md          # unchanged
│   ├── autoresearch-ideator.md               # unchanged
│   ├── autoresearch-reviewer.md              # unchanged
│   ├── audit-modernize.md                    # NEW
│   └── audit-dynamic.md                      # NEW
└── skills/
    ├── autoresearch/                         # unchanged
    ├── model-training/                       # unchanged
    ├── slurm/                                # unchanged
    └── audit/                                # NEW
        ├── SKILL.md                          # NEW
        └── reference/
            └── pytorch.md                    # NEW

.claude-plugin/marketplace.json               # MODIFIED (description + tags)
README.md                                     # MODIFIED (skill listing)
```

No files are deleted. Existing skills are unchanged.

---

## Tasks

### Task 0: Scaffold directories and update marketplace metadata

**Goal:** Create the empty `audit` skill directory tree, mention the new skill in the plugin/marketplace metadata and the README. No skill content yet — that comes in later tasks.

**Files:**

- Create dir: `plugins/ml-research/skills/audit/`
- Create dir: `plugins/ml-research/skills/audit/reference/`
- Modify: `plugins/ml-research/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`

**Acceptance Criteria:**

- [ ] `plugins/ml-research/skills/audit/reference/` exists.
- [ ] `plugins/ml-research/.claude-plugin/plugin.json` description references "audit" and `keywords` includes `"audit"`.
- [ ] `.claude-plugin/marketplace.json` plugin description and tags include audit.
- [ ] `README.md`'s `### \`ml-research\`` section lists `**\`audit\`**` with a one-line summary.
- [ ] `claude plugin validate plugins/ml-research` reports no errors (a missing `version` warning is expected; see the project README).

**Verify:**

```bash
test -d plugins/ml-research/skills/audit/reference/ \
  && grep -q '"audit"' plugins/ml-research/.claude-plugin/plugin.json \
  && grep -q '"audit"' .claude-plugin/marketplace.json \
  && grep -q '\*\*`audit`\*\*' README.md \
  && echo OK
```

Expected: `OK`. Then run `claude plugin validate plugins/ml-research` and confirm only the expected `version` warning.

**Steps:**

- [ ] **Step 1: Create the directory tree**

```bash
mkdir -p plugins/ml-research/skills/audit/reference
```

- [ ] **Step 2: Update `plugins/ml-research/.claude-plugin/plugin.json`**

Replace the file with:

```json
{
  "name": "ml-research",
  "description": "Claude Code skills for ML research on HPC: SLURM job orchestration (with built-in references for NCSA Delta and University of Utah CHPC), training-loop verification, autonomous research iteration, and PyTorch code audit.",
  "author": {
    "name": "Jake Schmidt",
    "email": "schmidt.jake.c@gmail.com"
  },
  "homepage": "https://github.com/schmidt-jake/claude_ml_research",
  "repository": "https://github.com/schmidt-jake/claude_ml_research",
  "license": "MIT",
  "keywords": [
    "slurm",
    "hpc",
    "ml",
    "gpu",
    "pytorch",
    "pytorch-lightning",
    "ncsa-delta",
    "chpc",
    "training",
    "autoresearch",
    "audit"
  ]
}
```

- [ ] **Step 3: Update `.claude-plugin/marketplace.json`**

Replace the file with:

```json
{
  "name": "jschmidt",
  "owner": {
    "name": "Jake Schmidt",
    "email": "schmidt.jake.c@gmail.com"
  },
  "metadata": {
    "description": "Plugins for ML research on HPC clusters — SLURM job orchestration, site-specific guidance, training loop verification, autonomous experiment iteration, and PyTorch code audit."
  },
  "plugins": [
    {
      "name": "ml-research",
      "source": "./plugins/ml-research",
      "description": "Claude Code skills for ML research on HPC: SLURM job orchestration (with built-in references for NCSA Delta and University of Utah CHPC), training-loop verification, autonomous research iteration, and PyTorch code audit.",
      "category": "ml-research",
      "tags": ["slurm", "hpc", "ml", "gpu", "pytorch", "pytorch-lightning", "ncsa-delta", "chpc", "audit"]
    }
  ]
}
```

- [ ] **Step 4: Update `README.md` to list the new skill**

Inside the `### \`ml-research\`` section's bullet list (after the `**\`autoresearch\`**` bullet), add:

```markdown
- **`audit`** — Audit a PyTorch codebase for trace/compile, numerical-stability, autograd, distributed, and perf anti-patterns. Surveys recent PyTorch releases for modernization opportunities (live web research). Optional `--dynamic` mode runs `torch._dynamo.explain`, `TORCH_TRACE`+`tlparse`, autograd anomaly mode, profiler, memory snapshot, and FLOP counter on a single forward/backward, then emits a categorized report.
```

- [ ] **Step 5: Validate the manifests**

```bash
claude plugin validate .
claude plugin validate plugins/ml-research
```

Expected: only the documented `version` warning on `plugins/ml-research`. Any other warning or error must be fixed before proceeding.

- [ ] **Step 6: Commit**

```bash
git add plugins/ml-research/skills/audit \
        plugins/ml-research/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json \
        README.md
git commit -m "$(cat <<'EOF'
Scaffold audit skill directory and update marketplace metadata

Add empty plugins/ml-research/skills/audit/{,reference/} and announce
the new skill in plugin.json, marketplace.json, and README.md. SKILL.md
and reference content land in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1: Author `reference/pytorch.md`

**Goal:** Create the per-framework anti-pattern + introspection-runbook reference. The skill's static audit (Phase 3) reads this file and pattern-matches the listed anti-patterns against target files; the modernize subagent reads the "Modernization seeds" section as research seeds; the dynamic subagent reads the "Introspection runbooks" section to know how to invoke each pass.

Spec sections that govern this file: §"Phase 3 — Static audit" (categories, anti-pattern bullets, citation rule) and §"Citation policy" (every entry needs ≥1 cite).

**Files:**

- Create: `plugins/ml-research/skills/audit/reference/pytorch.md`

**Acceptance Criteria:**

- [ ] File exists.
- [ ] Five top-level `## N. <category>` headings: `Trace / compile`, `Numerical stability under reduced precision`, `Gradient / autograd`, `Distributed`, `Inefficient patterns`.
- [ ] Each category section has a `Symptoms`/`Anti-patterns`/`Citations` block; the `Citations:` line has at least one URL.
- [ ] A `## Modernization seeds` section exists with at least five entries, each with an inline citation URL.
- [ ] An `## Introspection runbooks` section exists, listing each of the seven dynamic passes (`dynamo_explain`, `compile_logs`, `trace_tlparse`, `anomaly`, `profiler`, `memory`, `flop_counter`) with command sketch and citation.
- [ ] No occurrence of `TBD`, `TODO`, `FIXME`, or `XXX`.

**Verify:**

```bash
F=plugins/ml-research/skills/audit/reference/pytorch.md
test -f "$F" \
  && grep -c '^## [1-5]\.' "$F" | grep -q '^5$' \
  && grep -q '^## Modernization seeds' "$F" \
  && grep -q '^## Introspection runbooks' "$F" \
  && for pass in dynamo_explain compile_logs trace_tlparse anomaly profiler memory flop_counter; do \
       grep -q "$pass" "$F" || { echo "missing: $pass"; exit 1; }; \
     done \
  && ! grep -E '\b(TBD|TODO|FIXME|XXX)\b' "$F" \
  && echo OK
```

Expected: `OK`.

**Steps:**

- [ ] **Step 1: Write `plugins/ml-research/skills/audit/reference/pytorch.md`**

Use this content. The exact bullet wording can be lightly polished but the structure (five categories, Symptoms/Anti-patterns/Citations under each, Modernization seeds, Introspection runbooks) and every citation URL listed below must be preserved.

````markdown
# PyTorch audit reference

Anti-patterns for PyTorch code, organized by category. The `audit` skill's static phase reads this file and grep-matches the listed anti-patterns against target files. Each entry must have at least one citation; entries without a citation are dropped from the audit report.

Citation tiers (see SKILL.md "Citation policy" for the canonical definition):

- **Official:** `pytorch.org/docs`, `pytorch.org/blog`, `github.com/pytorch/pytorch` (issues, PRs, release notes, source).
- **Reputable third-party:** HuggingFace transformers docs, NVIDIA technical blogs, FlashAttention/DeepSpeed/vLLM/Lightning docs, well-known systems papers.

---

## 1. Trace / compile (torch.compile, torch.export, FX)

**Symptoms:** graph breaks, recompilations, `fullgraph=True` failures, slow first-step compile that doesn't amortize, "skipping cudagraphs" logs.

**Anti-patterns to grep for:**

- `\.item\(\)`, `\.tolist\(\)`, `int\(.*tensor`, `float\(.*tensor` inside a function decorated with `@torch.compile` or wrapped in `torch.compile(...)`.
- Data-dependent control flow on tensor values (`if x.sum() > 0:`, `while x.any():`).
- `isinstance(t, torch.Tensor)` checks inside compiled regions.
- Dynamic-shape branches without `torch._dynamo.mark_dynamic(t, dim)` — recompilation on every shape change.
- `print(...)`, `breakpoint()`, `logging.info(...)` inside the compiled region.
- Mutating module attributes inside `forward` (`self.cache.append(...)`, `self.counter += 1`).
- `tensor.numpy()` inside compiled code (forces graph break and host sync).

**Recommended introspection (cite to user / hand to audit-dynamic):**

```python
torch._dynamo.explain(model)(*example_inputs)   # graph breaks + reasons
TORCH_LOGS=graph_breaks,recompiles python script.py
TORCH_TRACE=/tmp/trace python script.py && tlparse /tmp/trace
```

**Citations:**

- https://pytorch.org/docs/stable/torch.compiler_troubleshooting.html
- https://pytorch.org/docs/stable/generated/torch.compile.html
- https://github.com/meta-pytorch/tlparse

---

## 2. Numerical stability under reduced precision

**Symptoms:** `NaN`/`Inf` in loss, mid-training divergence, gradient norms that explode under bf16/fp16 but are stable in fp32.

**Anti-patterns to grep for:**

- `F.softmax(x, ...)`, `torch.exp(x)`, `torch.log(x)`, `(-x).exp()` where `x` is a logit tensor in fp16/bf16 without an explicit `x.float()` upcast.
- `tensor.sum()` / `tensor.mean()` / `tensor.var()` over very large tensors (e.g., loss reduction over a long sequence) where the tensor is fp16. fp16 sums overflow (5-bit exponent saturates at ~65504, 10 mantissa bits); bf16 sums don't overflow but lose precision (8-bit exponent, only 7 mantissa bits) for large reductions. Upcast the accumulator to fp32 (`x.float().sum()`) for both.
- `eps=1e-8` (or smaller) in normalization layers (`LayerNorm`, `BatchNorm`, `RMSNorm`) when running in fp16 — `1e-8` is below fp16's smallest normal (`6e-5`).
- `(1 - x)` for very small `x` in fp16 — catastrophic cancellation; use log-space or upcast.
- Training in fp32 (or running fp32 fallback paths under autocast) without enabling TF32 — on Ampere+ you leave matmul throughput on the table. Use `torch.set_float32_matmul_precision('high')` (PyTorch ≥ 2.0) or, on PyTorch ≥ 2.9, the successor `torch.backends.cuda.matmul.fp32_precision = "tf32"`. (TF32 only affects fp32 ops; it is a no-op for bf16/fp16 matmuls.)
- Using `torch.cuda.amp.GradScaler` when training is bf16 — `GradScaler` is fp16-only and is a no-op (and deprecated) under bf16.

**Citations:**

- https://pytorch.org/docs/stable/notes/numerical_accuracy.html
- https://pytorch.org/docs/stable/amp.html
- https://pytorch.org/blog/accelerating-large-language-models/

---

## 3. Gradient / autograd

**Symptoms:** `RuntimeError: a leaf Variable that requires grad is being used in an in-place operation`, gradients of `None`, gradients that don't flow through a path you expected.

**Anti-patterns to grep for:**

- In-place ops on a leaf tensor with `requires_grad=True` (e.g., `param.add_(...)`, `param.mul_(...)`, `param.copy_(...)` outside a `torch.no_grad()` block).
- `param.data = something` — bypasses autograd registration; set the parameter via `param.copy_(...)` under `torch.no_grad()` or rebind via `setattr(module, name, nn.Parameter(...))`.
- `tensor.detach()` then expecting gradients to flow downstream.
- `loss.backward(retain_graph=True)` inside a regular training loop (almost always a bug — usually means the user wanted `.detach()` somewhere).
- Two `loss.backward()` calls without an intervening `optimizer.zero_grad()` and without `retain_graph=True`, *outside an explicit gradient-accumulation pattern* (will error or silently accumulate; legitimate when accumulation is intended).
- `torch.nn.utils.clip_grad_norm_(params, ...)` called *after* `optimizer.step()` (clips on the next iter's pre-step grads, not this step's).
- `torch.autograd.grad(...)` with `create_graph=True` in a training loop without realizing the higher-order graph is retained.

**Citations:**

- https://pytorch.org/docs/stable/notes/autograd.html#in-place-operations-with-autograd
- https://pytorch.org/docs/stable/autograd.html
- https://pytorch.org/docs/stable/notes/autograd.html#in-place-correctness-checks

---

## 4. Distributed

**Symptoms:** NCCL hangs, rank-zero divergence, `RuntimeError: NCCL communicator was aborted`, training that runs single-rank but deadlocks at multi-rank, log/checkpoint files corrupted by overlapping writes.

**Anti-patterns to grep for:**

- `print(...)`, `logger.info(...)`, `wandb.log(...)`, `torch.save(...)` calls without a `if rank == 0:` guard. (Distributed-aware loggers like Lightning's `self.log` are exempt — they handle rank-0 internally.)
- `DataLoader(..., shuffle=True, ...)` under DDP without `DistributedSampler` (each rank shuffles independently → duplicate sampling).
- `DistributedSampler` constructed but `sampler.set_epoch(epoch)` not called per epoch — same shuffle every epoch.
- `tensor.item()` or `tensor.cpu()` inside a hook running on every rank under DDP — turns a non-blocking op into a sync that stalls the cohort.
- `torch.distributed.init_process_group(...)` without an explicit `timeout=timedelta(minutes=N)` argument — the NCCL default is 10 min (PyTorch 2.x), which is usually too short for long-haul collectives like FSDP all-gathers under heavy load. Set explicitly so behavior is portable across versions.
- Missing `dist.barrier()` before `torch.save(checkpoint, ...)` on rank 0 (other ranks may exit before save completes, killing the rank-0 process via SIGCHLD on some launchers).
- `model.no_sync()` context wrapping more than the gradient-accumulation chunk (gradients land in the wrong buckets).
- Bare `model = DistributedDataParallel(model)` without `device_ids=[local_rank]` — DDP auto-detects but only correctly when the model is already on the right device.

**Citations:**

- https://pytorch.org/docs/stable/notes/ddp.html
- https://pytorch.org/docs/stable/distributed.html
- https://pytorch.org/tutorials/intermediate/ddp_tutorial.html
- https://github.com/pytorch/pytorch/blob/main/torch/distributed/distributed_c10d.py

---

## 5. Inefficient patterns

**Symptoms:** GPU utilization < 70% in a compute-bound run, host↔device sync events in `torch.profiler` traces, peak memory much larger than steady-state.

**Anti-patterns to grep for:**

- `for i in range(B): out.append(model(x[i]))` — Python loop over a batch dimension. Vectorize with batched ops (`torch.bmm`, `torch.einsum`, `torch.vmap`).
- Building a list of tensors per training step and `torch.cat`/`torch.stack`-ing at the end. Pre-allocate `out = torch.empty(B, ...)` and `out[i].copy_(...)`.
- `tensor.cpu()`, `tensor.numpy()`, `tensor.tolist()` inside the training loop's hot path — forces a host-device sync.
- `.item()` calls used for control flow (`if loss.item() < threshold:`) — sync. Move outside the hot path or compare on-device.
- `torch.cat([a, b, c])` in a hot path where `out = torch.empty((sum_lens, ...)); out[:len_a] = a; ...` would avoid an alloc.
- `tensor.contiguous()` called speculatively without checking `tensor.is_contiguous()` first (may or may not be a copy depending on layout).
- Using `nn.Linear` on input that has been `.transpose()`d but not `.contiguous()`-ified — cuBLAS may pick a slow path.
- DataLoader with `num_workers=0` in a CPU-bound preprocessing pipeline.
- DataLoader with `pin_memory=False` when the receiving device is CUDA.
- `optimizer.zero_grad(set_to_none=False)` — defeats the PyTorch ≥ 2.0 default (which sets grads to None) and reintroduces the slow zero-fill path; can also mask gradient-skipping bugs by leaving stale zero tensors around.

**Citations:**

- https://pytorch.org/docs/stable/notes/cuda.html#asynchronous-execution
- https://pytorch.org/tutorials/recipes/recipes/tuning_guide.html
- https://pytorch.org/docs/stable/data.html

---

## Modernization seeds

Hand-curated seed list for the `audit-modernize` subagent. The subagent uses these as starting points and extends them via live web research against PyTorch release notes and blog. Each entry has an inline citation.

- **`torch.nn.functional.scaled_dot_product_attention`** — Replaces hand-rolled `softmax(qk/√d)v` attention; auto-selects FlashAttention / mem-efficient / math backends. https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html
- **`torch.compile(model, dynamic=True)`** — Avoids per-shape recompilation when input shapes vary. https://pytorch.org/docs/stable/torch.compiler_dynamic_shapes.html
- **`torch.utils.flop_counter.FlopCounterMode`** — Per-op FLOP counting; identifies under-utilized GEMMs. https://github.com/pytorch/pytorch/blob/main/torch/utils/flop_counter.py
- **`torch.distributed.device_mesh`** — Modern multi-dim parallelism API; supersedes manual `device_ids` construction. https://pytorch.org/docs/stable/distributed.html#torch.distributed.device_mesh
- **`torch.amp.autocast` (top-level)** — Device-agnostic autocast; replaces `torch.cuda.amp.autocast`. https://pytorch.org/docs/stable/amp.html
- **`torch.nested`** — Native ragged batches; replaces manual padding + masking for variable-length sequences. https://pytorch.org/docs/stable/nested.html
- **`torchao.float8`** — FP8 training on Hopper+ when `torchao` is installed. https://github.com/pytorch/ao
- **`torch.cuda.memory._record_memory_history` + `_dump_snapshot`** — Memory allocator visualization replacing custom hooks. https://pytorch.org/docs/stable/torch_cuda_memory.html
- **`torch.set_float32_matmul_precision('high')`** — Enables TF32 on Ampere+; replaces the legacy `torch.backends.cuda.matmul.allow_tf32` knob. https://pytorch.org/docs/stable/generated/torch.set_float32_matmul_precision.html

---

## Introspection runbooks

Each pass listed here is a candidate for `audit-dynamic` to run when its applicability conditions are met. The subagent's agent definition encodes the applicability conditions and parsing logic; this section is the source-of-truth for the *commands*.

| Pass | Command sketch | Catches | Citation |
|---|---|---|---|
| `dynamo_explain` | `torch._dynamo.explain(model)(*ex)` | graph breaks, reasons, suggested fixes | https://pytorch.org/docs/stable/torch.compiler_troubleshooting.html |
| `compile_logs` | `TORCH_LOGS=graph_breaks,recompiles python harness.py` | recompilation triggers, dynamic-shape misses | https://pytorch.org/docs/stable/logging.html |
| `trace_tlparse` | `TORCH_TRACE=/tmp/t python harness.py && tlparse /tmp/t` | full compile timeline, kernel fusions missed | https://github.com/meta-pytorch/tlparse |
| `anomaly` | `with torch.autograd.detect_anomaly(): loss.backward()` | NaN/inf in grad, in-place leaf modification | https://pytorch.org/docs/stable/autograd.html#debugging-and-anomaly-detection |
| `profiler` | `with torch.profiler.profile(...) as p: ... ; p.key_averages().table(...)` | top ops by self-CUDA time, host↔device syncs | https://pytorch.org/docs/stable/profiler.html |
| `memory` | `torch.cuda.memory._record_memory_history()` then `_dump_snapshot(path)` | allocator fragmentation, peak allocations, leaks | https://pytorch.org/docs/stable/torch_cuda_memory.html |
| `flop_counter` | `with FlopCounterMode() as f: model(*ex)` | per-op FLOPs vs. peak; under-utilized GEMMs | https://github.com/pytorch/pytorch/blob/main/torch/utils/flop_counter.py |
````

- [ ] **Step 2: Validate the file structure**

```bash
F=plugins/ml-research/skills/audit/reference/pytorch.md
grep -c '^## [1-5]\.' "$F"               # expect 5
grep -c '^## Modernization seeds' "$F"    # expect 1
grep -c '^## Introspection runbooks' "$F" # expect 1
for pass in dynamo_explain compile_logs trace_tlparse anomaly profiler memory flop_counter; do
  grep -q "$pass" "$F" && echo "$pass OK"
done
```

Expected: `5`, `1`, `1`, then seven `... OK` lines.

- [ ] **Step 3: Commit**

```bash
git add plugins/ml-research/skills/audit/reference/pytorch.md
git commit -m "$(cat <<'EOF'
Add audit reference: PyTorch anti-patterns and introspection runbooks

Five categories (compile/numerical/autograd/distributed/perf) with
grep-able anti-pattern bullets and citation URLs for each. Modernization
seeds for the audit-modernize subagent. Introspection runbooks table for
audit-dynamic with command sketches and citation links.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Author `agents/audit-modernize.md`

**Goal:** Create the modernize subagent definition. The agent does live web research against PyTorch release notes, blog, and GitHub, intent-matches against the user's target files, and returns a structured findings list with mandatory citations.

Spec sections governing this file: §"Phase 4 — Modernize" (dispatch shape, subagent loop, hard rules, return shape); §"Citation policy".

**Files:**

- Create: `plugins/ml-research/agents/audit-modernize.md`

**Acceptance Criteria:**

- [ ] Frontmatter `name: audit-modernize`, `model: opus`, tools include `WebSearch`, `WebFetch`, `Read`, `Grep`, `Bash`; `disallowedTools` includes `Edit` and `Write`.
- [ ] Body has sections: Identity, Input contract, Output contract, Subagent loop, Citation policy, Hard rules, Example return.
- [ ] Hard rules section explicitly states: every finding has `severity: "info"`; ≤15 findings; ≤12 web fetches; no code edits.
- [ ] No occurrence of `TBD`, `TODO`, `FIXME`, or `XXX`.

**Verify:**

```bash
F=plugins/ml-research/agents/audit-modernize.md
test -f "$F" \
  && python3 - <<'PY'
import yaml
content = open("plugins/ml-research/agents/audit-modernize.md").read()
parts = content.split("---", 2)
assert len(parts) == 3, "missing frontmatter"
fm = yaml.safe_load(parts[1])
assert fm["name"] == "audit-modernize"
assert fm["model"] == "opus"
assert {"WebSearch", "WebFetch", "Read", "Grep", "Bash"}.issubset(set(fm.get("tools", [])))
assert {"Edit", "Write"}.issubset(set(fm.get("disallowedTools", [])))
body = parts[2].lower()
for s in ("identity", "input contract", "output contract", "subagent loop",
          "citation policy", "hard rules", "example return"):
    assert s in body, f"missing section: {s}"
print("OK")
PY
```

Expected: `OK`.

**Steps:**

- [ ] **Step 1: Write `plugins/ml-research/agents/audit-modernize.md`**

````markdown
---
name: audit-modernize
description: Identify modernization opportunities in a PyTorch codebase by surveying recent framework releases (release notes, official blog, GitHub) and intent-matching new public APIs against hand-rolled implementations in the user's target files. Returns a structured findings list with mandatory citations. Invoked by the audit skill in Phase 4.
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

# Audit Modernize

You are the **Modernize** subagent for the `audit` skill. The main agent dispatches you with a snapshot of the user's target files and the detected PyTorch + ecosystem versions. Your job is to identify *places in the user's code where the intent matches a newer or better PyTorch API* — manual implementations of what a newer release now does in one well-tested call.

You do live web research; the main agent does not. Your context burns the WebSearch/WebFetch tokens so the main agent's stays clean. You return a structured JSON object and nothing else. You write nothing to disk.

## Identity

You are not auditing for bugs (that is the static phase, which the main agent runs inline). You are not running framework introspection (that is the dynamic subagent). Your sole job: "this code is doing X by hand; PyTorch ≥ Y now ships Z that does exactly this."

A modernize finding is opportunistic, not corrective. The user's code works. You're identifying where they could simplify, gain a fast path, or follow current best practice.

**One pass per dispatch.** You return a list — at most 15 entries, ranked by impact. You do not return prose, do not return commentary, do not return findings without citations.

**No disk writes.** No file edits. No commits. Your only output is the structured JSON described in the output contract. The `Edit` and `Write` tools are excluded from your tool allowlist.

**Why Opus for this role:** Modernization research is high-leverage and infrequent (one dispatch per audit). Distinguishing a real intent match from a superficial pattern match requires careful reading of both the user's code and the new API's docs.

## Input contract

Your dispatch prompt contains:

- `Detected framework:` — always `pytorch` in v1.
- `Detected versions:` — `torch=<v>` plus an ecosystem dict (e.g. `flash-attn=2.5.0`, `transformer-engine=1.7.0`, `torchao=0.5.0`).
- `Hardware:` — GPU model + arch (e.g., `NVIDIA H100 80GB (Hopper)`), CUDA version, driver version.
- `Target files (full content embedded):` — the user's files, separated by `---` delimiters. Read these for intent matching.
- `Reference seed:` — the "Modernization seeds" section of `reference/pytorch.md`, embedded verbatim. Use as a starting list of APIs to look for; extend via live research.

## Output contract

Return a single JSON object as your final message. The main agent parses this; structure must be exact.

```json
{
  "findings": [
    {
      "category": "modernize",
      "severity": "info",
      "file": "src/model.py",
      "line": 142,
      "snippet": "for i in range(B): out.append(F.linear(x[i], W[i]))",
      "why": "Per-batch Python loop over a batched matmul; B kernel launches where one suffices.",
      "fix": "torch.bmm(x, W.transpose(-1, -2)) — one batched GEMM.",
      "citation": "https://pytorch.org/docs/stable/generated/torch.bmm.html"
    }
  ],
  "research_summary": "Surveyed: torch 2.4 release notes, torch 2.5 release notes, torchao 0.5 release. 12 fetches consumed."
}
```

**Field-by-field:**

- `category` — always `"modernize"`. (The main agent groups findings by category in the report.)
- `severity` — always `"info"`. Modernization is opportunistic by definition. A broken/removed API is a static-phase finding (catalogued in `reference/pytorch.md`), not a modernization gap.
- `file` — relative path from repo root, matching one of the embedded target files.
- `line` — 1-indexed line number where the snippet starts.
- `snippet` — one to three lines from the user's code, copied verbatim. Truncate longer regions with `...` if needed.
- `why` — one sentence explaining what the user's code is doing and why a newer API supersedes it.
- `fix` — one short sentence with the replacement. Code goes inline. No multi-paragraph explanations.
- `citation` — exactly one URL. Must satisfy the citation policy below.

**`research_summary`** (string, required) — one short sentence naming the sources you consulted and the fetch count. The main agent surfaces this in the audit report's "Run summary" so the user knows what was reviewed.

## Subagent loop

1. **Identify newer-than-installed APIs.** Read the PyTorch release-notes pages for every minor version above the user's installed `torch`. Start at `https://github.com/pytorch/pytorch/releases` and `https://pytorch.org/blog/`. Focus on items that introduce *new public APIs* (not bug fixes, not perf-only changes, not internal refactors). Record candidate APIs.

2. **Intent-match against the user's targets.** For each candidate API, scan the embedded target files for code whose *intent* matches a manual implementation of that API. Examples of intent-matches:
   - User loops over a batch with manual padding → `torch.nested` or `torch.nn.utils.rnn.pad_sequence`.
   - User manually constructs `device_ids` per-rank → `torch.distributed.device_mesh`.
   - User has a custom AMP scaler or rolls their own `torch.cuda.amp.autocast` plumbing → `torch.amp.autocast` (top-level, device-agnostic).
   - User implements own `softmax(qk/√d)v` attention → `torch.nn.functional.scaled_dot_product_attention` with backend hints.
   - User does manual FP8 quant on Hopper → `torchao.float8` (when `torchao` is in the ecosystem dict).
   - User computes per-op FLOPs by hand → `torch.utils.flop_counter.FlopCounterMode`.
   - User imports `torch.cuda.amp.autocast` → `torch.amp.autocast` (device-agnostic top-level).

3. **Also survey installed ecosystem packages.** For each ecosystem package in the dispatch's `ecosystem=...` dict (`transformer-engine`, `flash-attn`, `apex`, `deepspeed`, `xformers`, `triton`, `bitsandbytes`, `lightning`, `accelerate`, `torchao`), read that project's release notes and docs the same way. A user who installed `torchao` but doesn't import `torchao.float8` on Hopper hardware is leaving FP8 throughput on the table.

4. **Discard candidates without a clear intent match.** If you can't point to a specific snippet in the embedded target files where the user is manifestly doing manual-X, drop the candidate. Do not return findings on the form "you should consider X" without code evidence.

5. **Rank by impact.** Order findings by expected throughput/maintenance impact (high to low). Cap at 15.

6. **Return the structured list.** Each entry must satisfy the citation policy.

You should expect to do 4–10 web fetches in a typical dispatch. The hard cap is 12 (see Hard rules).

## Citation policy

Every finding must carry exactly one citation URL. Acceptable sources:

- **Official:**
  - `https://pytorch.org/docs/...`
  - `https://pytorch.org/blog/...`
  - `https://pytorch.org/tutorials/...`
  - `https://github.com/pytorch/pytorch/...` (release pages, source-code permalinks, issues, PRs)
  - `https://github.com/pytorch/<satellite>/...` (`pytorch/ao`, `pytorch/tlparse`, `pytorch/torchtune`, etc.)
  - `https://dev-discuss.pytorch.org/...`

- **Reputable third-party:**
  - HuggingFace docs (`huggingface.co/docs/...`)
  - NVIDIA developer blogs (`developer.nvidia.com/blog/...`)
  - FlashAttention (`https://github.com/Dao-AILab/flash-attention/...`)
  - DeepSpeed docs (`https://www.deepspeed.ai/...`)
  - vLLM (`https://docs.vllm.ai/...`)
  - Lightning (`https://lightning.ai/docs/...`)
  - Well-known systems papers on arXiv (cs.LG, cs.DC) when introducing a technique that's also in PyTorch.

**Not acceptable at any tier:** personal blog posts of unknown provenance, Reddit, Twitter/X, Wikipedia, "I recall reading that…". If you can't find a qualifying citation for a candidate finding, drop it — even if it would otherwise be a strong recommendation.

When the cleanest citation is a release-notes line item, link directly to that release page (e.g., `https://github.com/pytorch/pytorch/releases/tag/v2.5.0`). When the cleanest is the API doc, link the docs URL.

## Hard rules

- **Every finding has `severity: "info"`.** Modernization is opportunistic. A broken/removed API is a static-phase finding catalogued in `reference/pytorch.md` — not your concern.
- **No code edits.** You may not call `Edit` or `Write`. The user reads the audit report and decides what to act on.
- **Drop findings without a citation.** No "X is faster" without a benchmark cite. No "X is the new way" without a release-note or docs cite. If in doubt, drop it.
- **Cap web fetches at 12 per dispatch.** Beyond that, the modernization sweep is fine to be incomplete — the audit is one-shot.
- **At most 15 findings, ranked by impact.** A long undifferentiated list dilutes the report.
- **Return JSON, not prose.** Your final message is the JSON object only. No "Here are the findings:" preamble.

## Example return

For a project pinned at `torch==2.2.0` running on H100 with `torchao==0.5.0` and `flash-attn==2.5.0` installed, a representative return:

```json
{
  "findings": [
    {
      "category": "modernize",
      "severity": "info",
      "file": "src/attention.py",
      "line": 64,
      "snippet": "scores = (q @ k.transpose(-2, -1)) / math.sqrt(d_k)\nscores = scores.masked_fill(mask == 0, -1e9)\nattn = F.softmax(scores, dim=-1)\nout = attn @ v",
      "why": "Hand-rolled scaled-dot-product attention; PyTorch ships F.scaled_dot_product_attention which auto-selects FlashAttention on Hopper.",
      "fix": "out = F.scaled_dot_product_attention(q, k, v, attn_mask=(mask == 0), is_causal=False)",
      "citation": "https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html"
    },
    {
      "category": "modernize",
      "severity": "info",
      "file": "src/train.py",
      "line": 22,
      "snippet": "from torch.cuda.amp import autocast, GradScaler",
      "why": "torch.cuda.amp.autocast is now a thin wrapper around the device-agnostic torch.amp.autocast; the top-level form generalizes across CPU/CUDA/MPS.",
      "fix": "from torch.amp import autocast, GradScaler  # autocast(device_type='cuda', ...)",
      "citation": "https://pytorch.org/docs/stable/amp.html"
    },
    {
      "category": "modernize",
      "severity": "info",
      "file": "src/model.py",
      "line": 188,
      "snippet": "x = torch.cat([model(xi) for xi in batch.split(1)], dim=0)",
      "why": "Per-sample loop over a batched model call.",
      "fix": "x = model(batch)  — vectorized; one kernel launch instead of B.",
      "citation": "https://pytorch.org/tutorials/recipes/recipes/tuning_guide.html"
    }
  ],
  "research_summary": "Surveyed: torch 2.3/2.4/2.5 release notes, pytorch.org/blog (Aug-Dec 2024), torchao 0.5 README, flash-attn README. 9 fetches consumed."
}
```
````

- [ ] **Step 2: Validate frontmatter and structure**

Run the `python3` block from the Verify section above. Expected: `OK`.

- [ ] **Step 3: Confirm the manifest still validates**

```bash
claude plugin validate plugins/ml-research
```

Only the documented `version` warning is acceptable.

- [ ] **Step 4: Commit**

```bash
git add plugins/ml-research/agents/audit-modernize.md
git commit -m "$(cat <<'EOF'
Add audit-modernize agent definition

Subagent that surveys recent PyTorch releases (and ecosystem packages)
for new public APIs and intent-matches them against the user's target
files. Returns at most 15 info-severity findings, each with a mandatory
citation. No code edits, no disk writes; ≤12 web fetches per dispatch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Author `agents/audit-dynamic.md`

**Goal:** Create the dynamic-introspection subagent definition. The agent runs PyTorch's own introspection tools (dynamo explain, compile logs, tlparse, autograd anomaly mode, profiler, memory snapshot, FLOP counter) on a single forward/backward of the user's model and returns a structured digest.

Spec sections governing this file: §"Phase 5 — Dynamic introspection" (pre-requisites, dispatch shape, pass list, hard rules, return shape); §"Citation policy".

**Files:**

- Create: `plugins/ml-research/agents/audit-dynamic.md`

**Acceptance Criteria:**

- [ ] Frontmatter `name: audit-dynamic`, `model: sonnet`, tools include `Bash`, `Read`, `Edit`, `Write`, `Grep`; `Edit`/`Write` are present (this agent scaffolds an introspection harness file under `/tmp/audit-dynamic-<pid>/`).
- [ ] Body has sections: Identity, Input contract, Output contract, Pass list, Conditional skip rules, Hard rules, Example return.
- [ ] Pass list mentions all seven passes by name.
- [ ] Hard rules section states: each pass `timeout 90s`; total wall-clock ≤5 min; artifacts under `/tmp/audit-dynamic-<pid>/`; no edits to user code.
- [ ] No occurrence of `TBD`, `TODO`, `FIXME`, or `XXX`.

**Verify:**

```bash
F=plugins/ml-research/agents/audit-dynamic.md
test -f "$F" \
  && python3 - <<'PY'
import yaml
content = open("plugins/ml-research/agents/audit-dynamic.md").read()
parts = content.split("---", 2)
assert len(parts) == 3
fm = yaml.safe_load(parts[1])
assert fm["name"] == "audit-dynamic"
assert fm["model"] == "sonnet"
assert {"Bash", "Read", "Edit", "Write", "Grep"}.issubset(set(fm.get("tools", [])))
body = parts[2].lower()
for s in ("identity", "input contract", "output contract", "pass list",
          "conditional skip", "hard rules", "example return"):
    assert s in body, f"missing section: {s}"
for p in ("dynamo_explain", "compile_logs", "trace_tlparse", "anomaly",
          "profiler", "memory", "flop_counter"):
    assert p in body, f"missing pass: {p}"
print("OK")
PY
```

Expected: `OK`.

**Steps:**

- [ ] **Step 1: Write `plugins/ml-research/agents/audit-dynamic.md`**

````markdown
---
name: audit-dynamic
description: Run PyTorch introspection tools (torch._dynamo.explain, TORCH_TRACE+tlparse, autograd anomaly mode, torch.profiler, torch.cuda.memory snapshot, FlopCounterMode) on a single forward/backward of the user's model. Parses the outputs and returns a structured digest with citation-bearing findings. Invoked by the audit skill in Phase 5 only when the user passes --dynamic and a local GPU is reachable.
model: sonnet
effort: medium
maxTurns: 40
tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
---

# Audit Dynamic

You are the **Dynamic** subagent for the `audit` skill. The main agent dispatches you only when the user has passed `--dynamic` and a local CUDA GPU is reachable. You construct the user's model, run a single forward/backward through several introspection passes, parse the outputs, and return a structured digest.

You write a small Python harness file to `/tmp/audit-dynamic-<pid>/harness.py`, run each pass as a separate timeout-bounded subprocess, and parse the resulting traces/logs. The user's source code is read-only — you do not edit it.

## Identity

You execute introspection tools; you do not read code for static patterns (the main agent already did Phase 3 inline) and you do not do web research (that was Phase 4). Your scope is bounded: scaffold a harness, run the passes that apply, parse outputs into structured findings.

The introspection tools emit large, noisy outputs (`TORCH_TRACE` traces are megabytes; `torch.profiler` chrome traces are larger still). Your job is to extract the actionable findings and return a small digest. The main agent never sees the raw traces — only your parsed digest plus paths to the saved artifacts on disk for the user to inspect later.

**No edits to user code.** You may write to `/tmp/audit-dynamic-<pid>/` and to `scripts/audit_introspection.py` *only* if the dispatch indicates the entrypoint is a stub the main agent created and your job is to fill in inferred shapes/dtypes. (See Input contract.) Otherwise, all writes go to `/tmp/audit-dynamic-<pid>/`.

## Input contract

Your dispatch prompt contains:

- `Environment:` — full Phase 2 dictionary: `torch_version`, `cuda_version`, `cudnn_version`, `nccl_version`, `gpu_model`, `gpu_arch` (e.g., `Hopper`), `gpu_count`, ecosystem-package versions.
- `Target files (full content embedded):` — the user's source, separated by `---`. Read for context only; do not edit.
- `Introspection entrypoint:`
  - `type: function | script`
  - `value: <module:function | path/to/script>`
  - For `type: function`: the value names a Python callable returning `(model: nn.Module, example_inputs: tuple[Tensor, ...])`. The harness imports and calls it.
  - For `type: script`: the value is a path to a standalone script that already does one `model(*inputs).sum().backward()` on tiny inputs. The harness imports it as a module (using `runpy.run_path`) and wraps the relevant ops with introspection.
- `Static-phase findings (relevant to dynamic checks):` — JSON list of static findings already produced by the main agent. Use this to skip non-applicable passes (see Conditional skip rules).

## Output contract

Return a single JSON object as your final message.

```json
{
  "passes_run": ["dynamo_explain", "compile_logs", "anomaly", "profiler", "memory"],
  "passes_skipped": {
    "trace_tlparse": "tlparse not installed",
    "flop_counter": "no GEMM ops in graph"
  },
  "findings": [
    {
      "category": "compile",
      "severity": "warning",
      "file": "src/model.py",
      "line": 87,
      "snippet": "if mask.sum().item() > 0:",
      "why": "Graph break: data-dependent control flow on a tensor value (.item() forces a sync and exits the compiled region). Confirmed by torch._dynamo.explain.",
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

**Field-by-field:**

- `passes_run` — array of pass IDs that completed successfully.
- `passes_skipped` — object mapping pass ID → one-line reason (missing dependency, not applicable, timed out).
- `findings` — array of finding objects. `category` is one of `compile`, `numerical`, `autograd`, `distributed`, `perf`. `severity` is one of `error`, `warning`, `info` per the static-phase definitions. Same shape as static findings but with an additional `evidence_path` field pointing into `/tmp/audit-dynamic-<pid>/`.
- `summary_metrics` — object with quantitative summaries the report surfaces in the "Run summary" line. Keys: `graph_breaks`, `recompiles`, `peak_gpu_mem_mb`, `host_device_syncs_per_step`. Omit a key if the relevant pass was skipped.

## Pass list

Each pass below is a candidate. Conditional skip rules in the next section say when to drop a pass. The runbook commands come from `plugins/ml-research/skills/audit/reference/pytorch.md` "Introspection runbooks" — that is the source of truth for invocation; this section repeats them for convenience and adds parsing logic.

### `dynamo_explain`

Wrap the model construction in a small harness:

```python
import torch
model, inputs = build_for_introspection()  # or wrap script entrypoint
explanation = torch._dynamo.explain(model)(*inputs)
print(explanation)
```

Save stdout to `/tmp/audit-dynamic-<pid>/dynamo_explain.txt`. Parse: count graph breaks; for each break, capture the `Reason`, source line (file:line), and suggested fix from the explanation. Emit one finding per distinct break (not per occurrence).

Citation: https://pytorch.org/docs/stable/torch.compiler_troubleshooting.html

### `compile_logs`

Run the harness with logging on:

```bash
TORCH_LOGS=graph_breaks,recompiles,recompiles_verbose \
  python /tmp/audit-dynamic-<pid>/harness.py 2> /tmp/audit-dynamic-<pid>/compile_logs.txt
```

Parse: extract recompilation triggers (`Recompiling function ...`) and their reasons. Emit one finding per distinct recompilation cause.

Citation: https://pytorch.org/docs/stable/logging.html

### `trace_tlparse`

```bash
TORCH_TRACE=/tmp/audit-dynamic-<pid>/trace \
  python /tmp/audit-dynamic-<pid>/harness.py
tlparse /tmp/audit-dynamic-<pid>/trace -o /tmp/audit-dynamic-<pid>/tlparse-report.html
```

If `tlparse` is not on `$PATH`, skip (`passes_skipped`). Parse `index.html` for headline metrics: total compile time, kernel-fusion count, missed fusions. Emit findings for missed-fusion clusters, per-pass compile-time outliers.

Citation: https://github.com/meta-pytorch/tlparse

### `anomaly`

Wrap the harness's forward+backward:

```python
with torch.autograd.detect_anomaly():
    out = model(*inputs)
    loss = out.sum() if out.requires_grad else out.float().sum()
    loss.backward()
```

Save the tracelog to `/tmp/audit-dynamic-<pid>/anomaly.txt`. Parse for: in-place leaf-tensor errors, NaN/inf in any backward op, function-name + offending op for each. Emit one finding per distinct anomaly.

Citation: https://pytorch.org/docs/stable/autograd.html#debugging-and-anomaly-detection

### `profiler`

```python
with torch.profiler.profile(
    activities=[torch.profiler.ProfilerActivity.CPU,
                torch.profiler.ProfilerActivity.CUDA],
    schedule=torch.profiler.schedule(wait=1, warmup=1, active=3),
    record_shapes=True,
) as prof:
    for _ in range(5):
        out = model(*inputs)
        loss = out.sum() if out.requires_grad else out.float().sum()
        loss.backward()
        prof.step()

prof.export_chrome_trace("/tmp/audit-dynamic-<pid>/profiler.json")
print(prof.key_averages().table(sort_by="self_cuda_time_total", row_limit=20))
```

Parse stdout: top ops by self-CUDA time. Detect host-device-sync ops (`aten::item`, `aten::nonzero`, `aten::_local_scalar_dense`, `cudaStreamSynchronize`) — count per training step.

Citation: https://pytorch.org/docs/stable/profiler.html

### `memory`

```python
torch.cuda.memory._record_memory_history(max_entries=1_000_000)
out = model(*inputs)
loss = out.sum() if out.requires_grad else out.float().sum()
loss.backward()
torch.cuda.memory._dump_snapshot("/tmp/audit-dynamic-<pid>/memory.pickle")
torch.cuda.memory._record_memory_history(enabled=None)
print(torch.cuda.memory_summary())
```

Parse stdout `torch.cuda.memory_summary()`: capture peak allocated, peak reserved, allocator fragmentation ratio (reserved-but-not-allocated). The `.pickle` is for the user's offline inspection (loadable in `pytorch.org/memory_viz`); reference its path in `evidence_path`.

Citation: https://pytorch.org/docs/stable/torch_cuda_memory.html

### `flop_counter`

```python
from torch.utils.flop_counter import FlopCounterMode
with FlopCounterMode(model) as fc:
    out = model(*inputs)
    if out.requires_grad:
        out.sum().backward()
print(fc.flop_counts)
```

Parse: per-module FLOP totals. Compare against GPU peak (lookup from `gpu_model` in the dispatch's `Environment`); flag GEMMs that under-utilize peak by >10× (likely too small a problem size for the device).

Citation: https://github.com/pytorch/pytorch/blob/main/torch/utils/flop_counter.py

## Conditional skip rules

The static-phase findings tell you what's actually present in the user's code. Skip passes whose preconditions are unmet — running them anyway just produces noise.

- Skip `dynamo_explain`, `compile_logs`, `trace_tlparse` if no `torch.compile`, `@torch.compile`, or `torch._dynamo` reference appears in any target file. Detect by grepping the embedded target files.
- Skip `anomaly` if no `loss.backward()` (or `.backward()`) is reachable from the entrypoint. For `type: function` entrypoints, the function returns only `(model, inputs)` — wrap them yourself with `out.sum().backward()`. Skip only if the model's `forward` produces no tensor that requires grad.
- Skip `flop_counter` if no `nn.Linear`, `nn.Conv*`, `F.linear`, `F.conv*`, `@`, `torch.bmm`, `torch.einsum` appears in the target files (no GEMM ops to count).
- Skip `trace_tlparse` if `tlparse` is not on `$PATH` (`which tlparse` returns nonzero). Note in `passes_skipped`: `"tlparse not installed; install with: uv pip install tlparse"`.

`profiler` and `memory` always apply (they're agnostic to the model's structure).

## Hard rules

- **Each pass runs in its own subprocess wrapped in `timeout 90s`.** Use `bash -c 'timeout 90s python harness_<pass>.py'` or equivalent. A timed-out pass is added to `passes_skipped` with the reason `"timed out (90s)"`. Never block another pass.
- **Total wall-clock cap: 5 minutes.** If you've consumed 4 minutes of wall time and have remaining passes, emit them as `passes_skipped: {"<pass>": "wall-clock budget exhausted"}` and return.
- **All artifacts under `/tmp/audit-dynamic-<pid>/`.** Create the directory at the start. Filenames: `harness.py`, `dynamo_explain.txt`, `compile_logs.txt`, `trace/`, `tlparse-report.html`, `anomaly.txt`, `profiler.json`, `memory.pickle`. Reference these paths in `evidence_path` fields.
- **Truncate or summarize trace files >100 MB.** A `TORCH_TRACE` directory or a `profiler.json` over 100 MB is too big for the user to inspect comfortably; replace it with a summary text file and note "truncated; original was N MB" in the corresponding finding's `why`.
- **No edits to user code.** Read-only. Your harness file lives under `/tmp/audit-dynamic-<pid>/`. If the dispatch's `Introspection entrypoint` is `type: script` and points to a `scripts/audit_introspection.py` stub the main agent created, you may *fill in inferred shapes/dtypes only when explicitly told to in the dispatch prompt* — otherwise treat scripts as read-only.
- **Citation per finding.** Use the runbook's citation as the default; if a parsed output points at a more specific doc URL, prefer that.
- **Return JSON, not prose.** Final message is the JSON object. No "Here is the digest:" preamble.

## Example return

```json
{
  "passes_run": ["dynamo_explain", "compile_logs", "anomaly", "profiler", "memory"],
  "passes_skipped": {
    "trace_tlparse": "tlparse not installed; install with: uv pip install tlparse",
    "flop_counter": "no GEMM ops detected in target files"
  },
  "findings": [
    {
      "category": "compile",
      "severity": "warning",
      "file": "src/model.py",
      "line": 87,
      "snippet": "if mask.sum().item() > 0:",
      "why": "Graph break — data-dependent control flow forces a host sync and exits the compiled region. Dynamo confirms 3 breaks at this site.",
      "fix": "Replace with torch.where or with mask.any() in a non-data-dependent branch.",
      "citation": "https://pytorch.org/docs/stable/torch.compiler_troubleshooting.html#graph-breaks",
      "evidence_path": "/tmp/audit-dynamic-12345/dynamo_explain.txt"
    },
    {
      "category": "perf",
      "severity": "warning",
      "file": "src/data.py",
      "line": 142,
      "snippet": "loss_val = loss.item()  # for logging",
      "why": "Profiler shows aten::_local_scalar_dense triggered 7 times per training step; each call forces a host-device sync.",
      "fix": "Defer logging by accumulating loss tensor on-device and converting once per epoch, or move the logger off the hot path.",
      "citation": "https://pytorch.org/docs/stable/profiler.html",
      "evidence_path": "/tmp/audit-dynamic-12345/profiler.json"
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
````

- [ ] **Step 2: Validate frontmatter and structure**

Run the `python3` block from the Verify section above. Expected: `OK`.

- [ ] **Step 3: Confirm the manifest still validates**

```bash
claude plugin validate plugins/ml-research
```

Only the documented `version` warning is acceptable.

- [ ] **Step 4: Commit**

```bash
git add plugins/ml-research/agents/audit-dynamic.md
git commit -m "$(cat <<'EOF'
Add audit-dynamic agent definition

Subagent that runs torch._dynamo.explain, TORCH_TRACE+tlparse, autograd
anomaly mode, torch.profiler, torch.cuda.memory snapshot, and
FlopCounterMode on a single forward/backward via a scaffolded harness in
/tmp/audit-dynamic-<pid>/. Each pass timeout-bounded; total wall ≤5 min.
Returns a digest of parsed findings + summary metrics; raw traces stay on
disk for user inspection.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Author `skills/audit/SKILL.md`

**Goal:** Create the main skill file. The skill orchestrates six phases inline (target resolution, environment probe, static audit, modernize dispatch, optional dynamic dispatch, report assembly) and dispatches to the two subagents from Tasks 2–3.

Spec sections governing this file: §"Invocation", §"Phase 1" through §"Phase 6", §"Citation policy", §"Composition with other skills", §"Out of scope for v1".

**Files:**

- Create: `plugins/ml-research/skills/audit/SKILL.md`

**Acceptance Criteria:**

- [ ] Frontmatter `name: audit`, with a `description` that includes the words `audit`, `pytorch`, `torch._dynamo.explain`, `TORCH_TRACE`, `tlparse`, `--dynamic`, and trigger keywords (`lint`, `review my model`).
- [ ] Body has six phase headings: `## Phase 1`, `## Phase 2`, `## Phase 3`, `## Phase 4`, `## Phase 5`, `## Phase 6`.
- [ ] Body has a `## Citation policy` section.
- [ ] Body has a `## Composition with other skills` section that names `slurm`, `model-training`, `autoresearch`.
- [ ] Body has an `## Out of scope` section.
- [ ] No occurrence of `TBD`, `TODO`, `FIXME`, or `XXX`.

**Verify:**

```bash
F=plugins/ml-research/skills/audit/SKILL.md
test -f "$F" \
  && python3 - <<'PY'
import yaml
content = open("plugins/ml-research/skills/audit/SKILL.md").read()
parts = content.split("---", 2)
assert len(parts) == 3
fm = yaml.safe_load(parts[1])
assert fm["name"] == "audit"
desc = fm["description"]
for s in ("audit", "pytorch", "torch._dynamo.explain", "TORCH_TRACE",
          "tlparse", "--dynamic", "lint", "review my model"):
    assert s in desc.lower() or s in desc, f"missing in description: {s}"
body = parts[2]
for h in ("## Phase 1", "## Phase 2", "## Phase 3", "## Phase 4",
          "## Phase 5", "## Phase 6", "## Citation policy",
          "## Composition with other skills", "## Out of scope"):
    assert h in body, f"missing heading: {h}"
for s in ("slurm", "model-training", "autoresearch"):
    assert s in body, f"composition section missing skill: {s}"
print("OK")
PY
```

Expected: `OK`.

**Steps:**

- [ ] **Step 1: Write `plugins/ml-research/skills/audit/SKILL.md`**

````markdown
---
name: audit
description: Audit a PyTorch codebase for trace/compile issues, numerical instability under reduced precision, gradient/autograd bugs, distributed pitfalls, and inefficient patterns. Surveys recent framework releases (live web research) for modernization opportunities. Optional --dynamic mode runs torch._dynamo.explain, TORCH_TRACE+tlparse, autograd anomaly mode, profiler, memory snapshot, and FLOP counter on a single forward/backward. Use when the user says "audit", "lint", "review my model code for ML bugs", "what could go wrong here", or before launching a long training run. Composes with the slurm skill for cluster hardware identification; complements but does not replace model-training (which validates the loop end-to-end by running it).
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
grep -rl --include='*.py' -E '(class .*\(nn\.Module\)|loss\.backward\(\)|init_process_group|DistributedDataParallel|FSDP|DeviceMesh)' src/ scripts/ 2>/dev/null
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

**Detection technique.** Use `grep` with the patterns from each category in `reference/pytorch.md`. Pattern-match conservatively: if a candidate is ambiguous (e.g., `.item()` *might* be inside a compiled region but you can't tell from grep alone), prefer false positives over false negatives at static phase — Phase 5 dynamic introspection (when run) will confirm or contradict. Note ambiguity in `why`.

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

**Validate the return.** The subagent returns JSON with `findings: [...]` and `research_summary: "..."`. Check:

- `findings` is a list of objects, each with non-empty `citation`, `category: "modernize"`, `severity: "info"`, and `file`/`line`/`snippet`/`why`/`fix` populated.
- `len(findings) <= 15`.
- `research_summary` is a non-empty string.

On malformed return: re-dispatch once with the prefix `"Your prior return was malformed: <reason>. Please return per the contract."` If it fails twice, drop the modernize phase, log a single line in the report's "Skipped passes" section: `modernize: subagent return malformed twice`, and continue.

Aggregate the validated findings for Phase 6.

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

If found, propose to the user. If confirmed, encode as the entrypoint dict.

If none found, offer to scaffold `scripts/audit_introspection.py`. Generate the stub from the user's model construction code (look for the `nn.Module` subclass definition and its `__init__`). The stub:

```python
"""Audit introspection entrypoint. Fill in tensor shapes and dtypes."""
import torch
from <user's module> import <user's Model>


def build_for_introspection():
    # TODO: replace with the constructor args matching your config
    model = <user's Model>(...).cuda().eval()
    # TODO: replace with realistic example shapes/dtypes for your model
    example_inputs = (
        torch.randn(2, 3, 224, 224, device="cuda"),
    )
    return model, example_inputs
```

Write the stub, tell the user it has TODOs to fill in, and stop Phase 5 here. The user can re-run `/ml-research:audit --dynamic` after editing.

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

**Validate the return.** The subagent returns JSON with `passes_run`, `passes_skipped`, `findings`, `summary_metrics`. Check:

- `findings` is a list of objects with non-empty `citation` and one of the five static-audit categories.
- Each finding has an `evidence_path` pointing into `/tmp/audit-dynamic-<pid>/`.
- `summary_metrics` is an object (may be empty if all passes were skipped).

On malformed return: same retry policy as Phase 4 (re-dispatch once with a reason; on second failure, log to skipped passes and continue).

Aggregate the validated findings for Phase 6. Surface `passes_skipped` and `summary_metrics` in the report.

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
````

- [ ] **Step 2: Validate frontmatter and structure**

Run the `python3` block from the Verify section above. Expected: `OK`.

- [ ] **Step 3: Confirm the manifest still validates and the skill is discoverable**

```bash
claude plugin validate plugins/ml-research
ls -la plugins/ml-research/skills/audit/SKILL.md
```

Only the documented `version` warning is acceptable.

- [ ] **Step 4: Commit**

```bash
git add plugins/ml-research/skills/audit/SKILL.md
git commit -m "$(cat <<'EOF'
Add audit SKILL.md (six-phase orchestrator)

Phase 1 resolves targets (arg or auto-detect+confirm). Phase 2 probes
hardware, cluster context, framework, and ecosystem packages. Phase 3
runs the static audit inline against reference/pytorch.md. Phase 4
dispatches audit-modernize. Phase 5 (--dynamic only) verifies GPU,
resolves an introspection entrypoint, and dispatches audit-dynamic.
Phase 6 emits a categorized in-conversation report. Composes with
slurm for cluster identification; complements model-training.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Final integration check

**Goal:** Run the official plugin validator across the whole repo and the plugin dir; do a smoke check that the skill, both agent definitions, and the reference are all parseable and cross-reference correctly.

**Files:**

(no file changes)

**Acceptance Criteria:**

- [ ] `claude plugin validate .` reports no errors (warnings on `version` are expected).
- [ ] `claude plugin validate plugins/ml-research` reports no errors (same `version` warning).
- [ ] All four new files exist with the expected sections and frontmatter.
- [ ] The SKILL.md description string is short enough to be loaded into context efficiently (≤2 KB) and contains the trigger keywords from the design.

**Verify:**

```bash
claude plugin validate .
claude plugin validate plugins/ml-research
# Cross-file integrity: SKILL references reference/pytorch.md and the two agents
F=plugins/ml-research/skills/audit/SKILL.md
grep -q 'reference/pytorch\.md' "$F" \
  && grep -q 'ml-research:audit-modernize' "$F" \
  && grep -q 'ml-research:audit-dynamic' "$F" \
  && wc -c plugins/ml-research/skills/audit/SKILL.md \
  && python3 -c "
import yaml
fm = yaml.safe_load(open('$F').read().split('---', 2)[1])
desc_bytes = len(fm['description'].encode())
assert desc_bytes < 2048, f'description too large: {desc_bytes} bytes'
print(f'description size: {desc_bytes} bytes (under 2KB cap)')
" \
  && echo OK
```

Expected: `OK`.

**Steps:**

- [ ] **Step 1: Run the official validators**

```bash
claude plugin validate .
claude plugin validate plugins/ml-research
```

If either reports an error (not a warning), fix the underlying issue in the relevant file and re-validate. The only acceptable warning is the documented `version` warning from `plugin.json` — anything else needs investigation.

- [ ] **Step 2: Cross-file integrity check**

```bash
F=plugins/ml-research/skills/audit/SKILL.md
grep -q 'reference/pytorch\.md' "$F" && echo "SKILL → reference: OK"
grep -q 'ml-research:audit-modernize' "$F" && echo "SKILL → modernize: OK"
grep -q 'ml-research:audit-dynamic' "$F" && echo "SKILL → dynamic: OK"
```

Expected: three `... OK` lines.

- [ ] **Step 3: Description size check**

```bash
python3 - <<'PY'
import yaml
fm = yaml.safe_load(open("plugins/ml-research/skills/audit/SKILL.md").read().split("---", 2)[1])
desc_bytes = len(fm["description"].encode())
assert desc_bytes < 2048, f"description too large: {desc_bytes} bytes"
print(f"description size: {desc_bytes} bytes (under 2KB cap)")
PY
```

Skill descriptions are loaded into every conversation's context. Keep under 2 KB.

- [ ] **Step 4: Smoke-confirm `audit` is discoverable**

```bash
ls plugins/ml-research/skills/audit/SKILL.md
ls plugins/ml-research/skills/audit/reference/pytorch.md
ls plugins/ml-research/agents/audit-modernize.md
ls plugins/ml-research/agents/audit-dynamic.md
```

All four paths must resolve.

- [ ] **Step 5: No commit needed**

This task is verification-only. No files were modified.

- [ ] **Step 6: (optional) Live trial in a fresh worktree**

For a real end-to-end check, the user can run:

```bash
claude --plugin-dir /u/jschmidt3/ml_research/plugins/ml-research
```

Inside that session: `/ml-research:audit src/some_pytorch_file.py`. Expected: skill resolves the target, probes the environment, runs the static phase, dispatches the modernize subagent, and prints the categorized report. This step is informational; it isn't part of the plan's pass criteria.

---

## Self-review

After completing all tasks, do a final pass:

1. **Spec coverage.** Each phase from the spec (1–6) is implemented in `SKILL.md`. The two subagents from §"Phase 4" and §"Phase 5" exist as agent files. The five static categories from §"Phase 3" all appear in `reference/pytorch.md`. The seven dynamic passes from §"Phase 5" all appear in both `reference/pytorch.md` and `audit-dynamic.md`. The citation policy is referenced in all three places.

2. **Cross-file consistency.** The introspection-pass commands listed in `reference/pytorch.md` "Introspection runbooks" match the commands in `audit-dynamic.md`'s "Pass list". The categories mentioned in `SKILL.md` Phase 3 match the categories in `reference/pytorch.md`'s top-level headings.

3. **Citation rule applied everywhere.** Every entry in `reference/pytorch.md` has at least one URL. The two agent definitions enforce the same rule on their findings. `SKILL.md` `## Citation policy` codifies the rule.

4. **Trigger keywords in `SKILL.md` description.** "audit", "lint", "review my model", "torch._dynamo.explain", "TORCH_TRACE", "tlparse", "--dynamic" are all present per Task 4 acceptance criteria.

5. **No placeholders.** No `TBD`, `TODO`, `FIXME`, `XXX` in any new file.
