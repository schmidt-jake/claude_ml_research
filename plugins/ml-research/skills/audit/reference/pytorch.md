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
- https://github.com/pytorch/tlparse

---

## 2. Numerical stability under reduced precision

**Symptoms:** `NaN`/`Inf` in loss, mid-training divergence, gradient norms that explode under bf16/fp16 but are stable in fp32.

**Anti-patterns to grep for:**

- `F.softmax(x, ...)`, `torch.exp(x)`, `torch.log(x)`, `(-x).exp()` where `x` is a logit tensor in fp16/bf16 without an explicit `x.float()` upcast.
- `tensor.sum()` / `tensor.mean()` / `tensor.var()` over very large tensors (e.g., loss reduction over a long sequence) where the tensor is fp16. bf16 sums are usually fine; fp16 accumulation overflows.
- `eps=1e-8` (or smaller) in normalization layers (`LayerNorm`, `BatchNorm`, `RMSNorm`) when running in fp16 — `1e-8` is below fp16's smallest normal (`6e-5`).
- `(1 - x)` for very small `x` in fp16 — catastrophic cancellation; use log-space or upcast.
- Training in bf16 without setting `torch.backends.cuda.matmul.allow_tf32 = True` and `torch.backends.cudnn.allow_tf32 = True` (or using `torch.set_float32_matmul_precision('high'|'highest')` on PyTorch ≥ 2.0).
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
- Two `loss.backward()` calls without an intervening `optimizer.zero_grad()` and without `retain_graph=True` (will error or silently accumulate).
- `torch.nn.utils.clip_grad_norm_(params, ...)` called *after* `optimizer.step()` (clips on the next iter's pre-step grads, not this step's).
- `torch.autograd.grad(...)` with `create_graph=True` in a training loop without realizing the higher-order graph is retained.

**Citations:**

- https://pytorch.org/docs/stable/notes/autograd.html#in-place-operations-on-tensors
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
- `torch.distributed.init_process_group(...)` without an explicit `timeout=timedelta(...)` argument — defaults can be too short or too long depending on PyTorch version.
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
- `optimizer.zero_grad()` instead of `optimizer.zero_grad(set_to_none=True)` — `set_to_none=True` is faster and uses less memory.

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
| `trace_tlparse` | `TORCH_TRACE=/tmp/t python harness.py && tlparse /tmp/t` | full compile timeline, kernel fusions missed | https://github.com/pytorch/tlparse |
| `anomaly` | `with torch.autograd.detect_anomaly(): loss.backward()` | NaN/inf in grad, in-place leaf modification | https://pytorch.org/docs/stable/autograd.html#anomaly-detection |
| `profiler` | `with torch.profiler.profile(...) as p: ... ; p.key_averages().table(...)` | top ops by self-CUDA time, host↔device syncs | https://pytorch.org/docs/stable/profiler.html |
| `memory` | `torch.cuda.memory._record_memory_history()` then `_dump_snapshot(path)` | allocator fragmentation, peak allocations, leaks | https://pytorch.org/docs/stable/torch_cuda_memory.html |
| `flop_counter` | `with FlopCounterMode() as f: model(*ex)` | per-op FLOPs vs. peak; under-utilized GEMMs | https://github.com/pytorch/pytorch/blob/main/torch/utils/flop_counter.py |
