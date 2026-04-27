# `getitem-profiler` skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new skill `ml-research:getitem-profiler` that greedily optimizes `Dataset.__getitem__` line-by-line on a side branch, gating each edit on byte-identical outputs (under seeded RNGs) and a meaningful per-call speedup, per the design at `docs/superpowers/specs/2026-04-26-getitem-profiler-design.md`.

**Architecture:** The skill is a markdown orchestration prompt (`SKILL.md`) that drives a greedy edit loop, plus a single-file Python harness (`scripts/profile_getitem.py`) that owns all measurement work. The harness exposes two subcommands — `baseline` (cache outputs + record starting timings) and `measure` (re-run cached indices, equality-check, re-profile, compute deltas) — each printing JSON. The skill never touches the user's dataset directly; it only invokes the harness and reads JSON.

**Tech Stack:** Python 3.10+, `line_profiler` (programmatic API: `LineProfiler.add_class` + `add_module` with `ScopingPolicy.LOCAL`, NOT `kernprof`/`autoprofile.run`), `torch`, `numpy`, `PIL`, `pickle`. The user's environment is assumed to have these — the harness imports them directly. Markdown with YAML frontmatter for `SKILL.md`.

**Spec:** `docs/superpowers/specs/2026-04-26-getitem-profiler-design.md` is the source of truth for any detail not spelled out in this plan.

---

## File structure

After this plan completes:

```
plugins/ml-research/skills/getitem-profiler/
├── SKILL.md                              # NEW — orchestration prompt
├── scripts/
│   └── profile_getitem.py                # NEW — measurement harness
└── tests/
    └── fixtures/
        ├── tiny_image_dataset.py         # NEW — deterministic synthetic dataset
        ├── nondeterministic_dataset.py   # NEW — fails seed-based determinism
        └── README.md                     # NEW — describes the fixtures
```

Tests are exercised manually via the harness CLI during development — there is no pytest suite (the project has no Python test infra). The fixtures ship with the skill so a future maintainer can re-run the smoke tests.

---

## Tasks

### Task 0: Scaffold skill directory and synthetic test fixtures

**Goal:** Lay down the skill's directory structure with placeholder files that the next tasks will fill in, plus two synthetic datasets the harness can be exercised against during development.

**Files:**

- Create: `plugins/ml-research/skills/getitem-profiler/SKILL.md` (frontmatter-only stub for now)
- Create: `plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py` (empty `main()`)
- Create: `plugins/ml-research/skills/getitem-profiler/tests/fixtures/tiny_image_dataset.py`
- Create: `plugins/ml-research/skills/getitem-profiler/tests/fixtures/nondeterministic_dataset.py`
- Create: `plugins/ml-research/skills/getitem-profiler/tests/fixtures/README.md`

**Acceptance Criteria:**

- [ ] The skill is discoverable by Claude Code (frontmatter parses, `name: getitem-profiler`, has a non-empty `description`)
- [ ] `scripts/profile_getitem.py` is executable and prints usage when run with no args
- [ ] `tiny_image_dataset.py:make_dataset()` returns an instance whose `__getitem__(0)` returns a dict with a `"image"` torch tensor and `"label"` int, takes > 1 ms per call, and produces byte-identical outputs across two seeded calls
- [ ] `nondeterministic_dataset.py:make_dataset()` returns an instance whose `__getitem__(0)` differs across two seeded calls (uses `os.urandom`, deliberately bypassing standard RNGs)

**Verify:**

```bash
python3 -c "
import sys
sys.path.insert(0, 'plugins/ml-research/skills/getitem-profiler/tests/fixtures')
import torch, numpy as np, random

# Tiny dataset: deterministic under seeded RNGs
import tiny_image_dataset
ds = tiny_image_dataset.make_dataset()
def seed_all(s):
    torch.manual_seed(s); np.random.seed(s); random.seed(s)
seed_all(0); a = ds[0]
seed_all(0); b = ds[0]
assert torch.equal(a['image'], b['image']), 'tiny_image_dataset is not deterministic under seed'
assert a['label'] == b['label']
assert isinstance(a['image'], torch.Tensor)
import time
seed_all(0); t0 = time.perf_counter(); _ = ds[0]; dt = time.perf_counter() - t0
assert dt > 1e-3, f'tiny_image_dataset is too fast to profile: {dt*1000:.2f} ms'

# Nondet dataset: differs across seeded calls
import nondeterministic_dataset
nd = nondeterministic_dataset.make_dataset()
seed_all(0); a = nd[0]; seed_all(0); b = nd[0]
assert not torch.equal(a['value'], b['value']), 'nondeterministic_dataset is unexpectedly deterministic'

print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Create the skill directory tree**

```bash
mkdir -p plugins/ml-research/skills/getitem-profiler/scripts
mkdir -p plugins/ml-research/skills/getitem-profiler/tests/fixtures
```

- [ ] **Step 2: Write the SKILL.md frontmatter stub**

The full body comes in Task 4. For now, just enough that the skill loader picks it up.

```markdown
---
name: getitem-profiler
description: Profile Dataset.__getitem__ with line_profiler and greedily optimize the slowest line on a side branch, gated by output equality and a per-call speedup threshold. Use when the user says "__getitem__ is slow", "profile my dataset", "speed up my dataloader", or supplies a factory function and asks for optimization.
---

(Body filled in by Task 4.)
```

Save to `plugins/ml-research/skills/getitem-profiler/SKILL.md`.

- [ ] **Step 3: Write the harness shell**

```python
#!/usr/bin/env python3
"""getitem-profiler measurement harness.

See plugins/ml-research/skills/getitem-profiler/SKILL.md for the orchestration
prompt that drives this script.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="profile_getitem.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline")
    sub.add_parser("measure")
    args = parser.parse_args(argv)
    print(f"stub: cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Save to `plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py`. Then `chmod +x` it:

```bash
chmod +x plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py
```

- [ ] **Step 4: Write `tiny_image_dataset.py`**

Deterministic-under-seed synthetic dataset with a clear line-profiler hotspot (the per-pixel Python loop is intentionally slow so the harness has something to optimize during smoke tests).

```python
"""Synthetic dataset with a clear line_profiler hotspot.

Used to exercise the getitem-profiler harness during development. The per-pixel
Python loop in __getitem__ is the intentional bottleneck.
"""
from __future__ import annotations

import numpy as np
import torch


class TinyImageDataset:
    def __init__(self, n: int = 32, side: int = 48) -> None:
        self.n = n
        self.side = side
        # Per-index seeds so output depends only on idx (and the global RNG state
        # at call time, which the harness controls via seed_all).
        self._seeds = np.arange(n, dtype=np.int64)

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx: int) -> dict:
        rng = np.random.default_rng(int(self._seeds[idx]))
        arr = rng.uniform(0, 1, (self.side, self.side, 3)).astype(np.float32)
        # Intentional hotspot: per-pixel Python loop — line_profiler will rank
        # this line as the slowest. Vectorizing it (`out = arr * 2.0 - 1.0`)
        # is the obvious optimization the harness would propose.
        out = np.empty_like(arr)
        for i in range(self.side):
            for j in range(self.side):
                out[i, j] = arr[i, j] * 2.0 - 1.0
        img = torch.from_numpy(out).permute(2, 0, 1).contiguous()
        return {"image": img, "label": int(idx % 10)}


def make_dataset() -> TinyImageDataset:
    return TinyImageDataset()
```

Save to `plugins/ml-research/skills/getitem-profiler/tests/fixtures/tiny_image_dataset.py`.

- [ ] **Step 5: Write `nondeterministic_dataset.py`**

```python
"""Synthetic dataset that bypasses seed-based determinism.

Used to verify the harness's `equality_mode: non_deterministic` detection.
"""
from __future__ import annotations

import os

import torch


class NondeterministicDataset:
    def __len__(self) -> int:
        return 32

    def __getitem__(self, idx: int) -> dict:
        # os.urandom isn't affected by torch.manual_seed / np.random.seed /
        # random.seed — the harness should detect this and refuse to start
        # the greedy loop.
        n = int.from_bytes(os.urandom(4), "little")
        return {"value": torch.tensor(float(n))}


def make_dataset() -> NondeterministicDataset:
    return NondeterministicDataset()
```

Save to `plugins/ml-research/skills/getitem-profiler/tests/fixtures/nondeterministic_dataset.py`.

- [ ] **Step 6: Write a brief README for the fixtures**

```markdown
# Test fixtures

Synthetic datasets used to exercise `scripts/profile_getitem.py` during development. There is no pytest suite — fixtures are imported via the harness's `--factory` flag.

- `tiny_image_dataset.py:make_dataset` — deterministic under seeded RNGs, intentionally slow per-pixel loop in `__getitem__` so line_profiler has a clear hotspot to surface.
- `nondeterministic_dataset.py:make_dataset` — uses `os.urandom`, deliberately bypassing standard RNGs. The harness should detect this and emit `equality_mode: non_deterministic` in `baseline.json`.
```

Save to `plugins/ml-research/skills/getitem-profiler/tests/fixtures/README.md`.

- [ ] **Step 7: Run the verify command**

Run the multi-line python verify command from the **Verify** section above.

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add plugins/ml-research/skills/getitem-profiler/
git commit -m "Scaffold getitem-profiler skill and synthetic test fixtures"
```

---

### Task 1: Implement equality walker

**Goal:** Implement `deep_equal(a, b)` in `profile_getitem.py` — recursively compares dicts, lists, tuples, tensors, numpy arrays, PIL Images, and primitive types, returning `(passed, first_diff_path, summary)`. This is the core safety net behind every accepted edit.

**Files:**

- Modify: `plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py` (add equality + helper imports)

**Acceptance Criteria:**

- [ ] `deep_equal(x, x)` returns `(True, None, None)` for tensors, numpy arrays, dicts, lists, tuples, ints, floats, strings, None, PIL Images
- [ ] `deep_equal({"a": tensor1}, {"a": tensor2})` with `tensor1 != tensor2` returns `(False, "outputs.a", <summary mentioning shape or value>)`
- [ ] `deep_equal({"a": 1}, {"a": 1, "b": 2})` returns `(False, "outputs", "key sets differ: ...")`
- [ ] `deep_equal([1, 2], [1, 3])` returns `(False, "outputs[1]", ...)`
- [ ] Different dtypes count as unequal (e.g. `tensor(1.0, float32)` vs `tensor(1.0, float64)`)
- [ ] PIL Image equality compares `.tobytes()` and `.size` and `.mode`
- [ ] Unknown leaf types fall back to `==` and capture exceptions

**Verify:**

```bash
python3 -c "
import sys
sys.path.insert(0, 'plugins/ml-research/skills/getitem-profiler/scripts')
import torch, numpy as np
from PIL import Image
from profile_getitem import deep_equal

# Equal cases
assert deep_equal(torch.zeros(3), torch.zeros(3)) == (True, None, None)
assert deep_equal(np.zeros(3), np.zeros(3)) == (True, None, None)
assert deep_equal({'a': 1, 'b': [2, 3]}, {'a': 1, 'b': [2, 3]}) == (True, None, None)
img = Image.new('RGB', (4, 4), (255, 0, 0))
img2 = Image.new('RGB', (4, 4), (255, 0, 0))
assert deep_equal(img, img2) == (True, None, None)

# Unequal cases
ok, path, _ = deep_equal({'a': torch.zeros(3)}, {'a': torch.ones(3)})
assert not ok and path == 'outputs.a'
ok, path, _ = deep_equal({'a': 1}, {'a': 1, 'b': 2})
assert not ok and path == 'outputs'
ok, path, _ = deep_equal([1, 2], [1, 3])
assert not ok and path == 'outputs[1]'
ok, _, _ = deep_equal(torch.zeros(3, dtype=torch.float32), torch.zeros(3, dtype=torch.float64))
assert not ok, 'dtype mismatch should fail'

print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Replace `profile_getitem.py` with the equality walker added**

The walker handles the leaf types named in the spec § "Data model → measure-N.json". Keep the `main()` stub — it'll be filled in over the next tasks.

```python
#!/usr/bin/env python3
"""getitem-profiler measurement harness.

See plugins/ml-research/skills/getitem-profiler/SKILL.md for the orchestration
prompt that drives this script.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any


def deep_equal(a: Any, b: Any, _path: str = "outputs") -> tuple[bool, str | None, str | None]:
    """Recursively compare two outputs.

    Returns (True, None, None) on equal; (False, first_diff_path, summary) on mismatch.
    Handles dicts, lists, tuples, torch tensors, numpy arrays, PIL Images, and
    primitive types. Unknown leaf types fall back to ==.
    """
    # Handle types in order: containers first, then leaf types.
    if isinstance(a, dict) or isinstance(b, dict):
        if not (isinstance(a, dict) and isinstance(b, dict)):
            return False, _path, f"type mismatch: {type(a).__name__} vs {type(b).__name__}"
        if set(a.keys()) != set(b.keys()):
            return False, _path, f"key sets differ: {sorted(a.keys())} vs {sorted(b.keys())}"
        for k in a:
            ok, p, s = deep_equal(a[k], b[k], f"{_path}.{k}")
            if not ok:
                return False, p, s
        return True, None, None

    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        if type(a) is not type(b):
            return False, _path, f"type mismatch: {type(a).__name__} vs {type(b).__name__}"
        if len(a) != len(b):
            return False, _path, f"length mismatch: {len(a)} vs {len(b)}"
        for i, (ai, bi) in enumerate(zip(a, b)):
            ok, p, s = deep_equal(ai, bi, f"{_path}[{i}]")
            if not ok:
                return False, p, s
        return True, None, None

    # Lazy imports so the equality module doesn't hard-require torch/numpy/PIL
    # to be importable at module load (the harness imports them at top level
    # anyway, but keeping deep_equal robust in isolation makes it easier to
    # smoke-test).
    try:
        import torch  # type: ignore
    except ImportError:
        torch = None  # type: ignore
    try:
        import numpy as np  # type: ignore
    except ImportError:
        np = None  # type: ignore
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        Image = None  # type: ignore

    if torch is not None and (isinstance(a, torch.Tensor) or isinstance(b, torch.Tensor)):
        if not (isinstance(a, torch.Tensor) and isinstance(b, torch.Tensor)):
            return False, _path, f"type mismatch: {type(a).__name__} vs {type(b).__name__}"
        if a.shape != b.shape:
            return False, _path, f"tensor shape {tuple(a.shape)} vs {tuple(b.shape)}"
        if a.dtype != b.dtype:
            return False, _path, f"tensor dtype {a.dtype} vs {b.dtype}"
        if not torch.equal(a, b):
            return False, _path, "tensor values differ"
        return True, None, None

    if np is not None and (isinstance(a, np.ndarray) or isinstance(b, np.ndarray)):
        if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)):
            return False, _path, f"type mismatch: {type(a).__name__} vs {type(b).__name__}"
        if a.shape != b.shape:
            return False, _path, f"array shape {a.shape} vs {b.shape}"
        if a.dtype != b.dtype:
            return False, _path, f"array dtype {a.dtype} vs {b.dtype}"
        if not np.array_equal(a, b):
            return False, _path, "array values differ"
        return True, None, None

    if Image is not None and (isinstance(a, Image.Image) or isinstance(b, Image.Image)):
        if not (isinstance(a, Image.Image) and isinstance(b, Image.Image)):
            return False, _path, f"type mismatch: {type(a).__name__} vs {type(b).__name__}"
        if a.size != b.size:
            return False, _path, f"PIL size {a.size} vs {b.size}"
        if a.mode != b.mode:
            return False, _path, f"PIL mode {a.mode} vs {b.mode}"
        if a.tobytes() != b.tobytes():
            return False, _path, "PIL pixel bytes differ"
        return True, None, None

    # Fallback: ==, capturing exceptions.
    try:
        if a == b:
            return True, None, None
        return False, _path, f"{type(a).__name__} != {type(b).__name__}: {a!r} vs {b!r}"
    except Exception as e:  # noqa: BLE001
        return False, _path, f"comparison failed for {type(a).__name__}: {e}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="profile_getitem.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline")
    sub.add_parser("measure")
    args = parser.parse_args(argv)
    print(f"stub: cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Save the file (overwriting Task 0's stub).

- [ ] **Step 2: Run the verify command**

Run the python verify block from the **Verify** section.

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py
git commit -m "Add deep_equal walker for getitem-profiler harness"
```

---

### Task 2: Implement `baseline` subcommand end-to-end

**Goal:** Implement `profile_getitem.py baseline` — load the user's factory, seed RNGs, call `__getitem__` for the requested indices, run the determinism self-check, run line_profiler, run the DataLoader micro-benchmark, write `baseline.json` and pickled outputs to the out-dir.

**Files:**

- Modify: `plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py`

**Acceptance Criteria:**

- [ ] `profile_getitem.py baseline --factory tiny_image_dataset:make_dataset` writes `<out-dir>/baseline.json` and `<out-dir>/baseline/{0..7}.pkl`
- [ ] `baseline.json` has the keys: `factory, indices, seed_base, equality_mode, reliable_line_stats, per_call_wall_time_s, line_stats, dataloader_bench`
- [ ] On `tiny_image_dataset`, `equality_mode == "strict"` and `reliable_line_stats == true`
- [ ] On `tiny_image_dataset`, the top entry of `line_stats` (sorted by `pct` descending) is the per-pixel loop line, with `pct > 50`
- [ ] On `nondeterministic_dataset`, `equality_mode == "non_deterministic"`, `first_diff_path` is set, and the script exits 0 (skill handles the case)
- [ ] `--profile-scope local` is the default; `--profile-scope package` walks sibling modules in the dataset's top-level package
- [ ] `--num-indices 8`, `--num-workers 4`, `--bench-batches 50` are the defaults; all overridable
- [ ] `--out-dir` defaults to `.getitem-profile`

**Verify:**

```bash
cd plugins/ml-research/skills/getitem-profiler && \
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py baseline \
    --factory tiny_image_dataset:make_dataset \
    --num-indices 4 \
    --num-workers 2 \
    --bench-batches 10 \
    --out-dir /tmp/getitem-profile-test && \
python3 -c "
import json, pathlib
b = json.loads(pathlib.Path('/tmp/getitem-profile-test/baseline.json').read_text())
assert b['equality_mode'] == 'strict', b['equality_mode']
assert b['reliable_line_stats'] is True
assert len(b['indices']) == 4
top = sorted(b['line_stats'], key=lambda x: x['pct'], reverse=True)[0]
assert top['pct'] > 50, f'expected hotspot >50%, got {top}'
assert 'for j in range' in top['code'] or 'for i in range' in top['code'], top
assert all(pathlib.Path(f'/tmp/getitem-profile-test/baseline/{i}.pkl').exists() for i in range(4))
print('OK strict')
" && \
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py baseline \
    --factory nondeterministic_dataset:make_dataset \
    --num-indices 4 --num-workers 2 --bench-batches 10 \
    --out-dir /tmp/getitem-profile-nondet && \
python3 -c "
import json, pathlib
b = json.loads(pathlib.Path('/tmp/getitem-profile-nondet/baseline.json').read_text())
assert b['equality_mode'] == 'non_deterministic', b
assert b.get('first_diff_path'), b
print('OK non_deterministic')
"
```

Expected output (last lines): `OK strict` then `OK non_deterministic`.

**Steps:**

- [ ] **Step 1: Add the imports and core helpers (factory loading, RNG seeding, line_profiler integration, dataloader bench)**

Add these to `profile_getitem.py` near the top, after the `deep_equal` definition. The `RELIABLE_LINE_STATS_THRESHOLD_S` constant matches the spec's "below ~1 ms" wording.

```python
import importlib
import json
import pickle
import random
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from torch.utils.data import DataLoader


RELIABLE_LINE_STATS_THRESHOLD_S = 1e-3  # below this, line_profiler overhead dominates


def load_factory(spec: str) -> Callable:
    """Resolve 'pkg.mod:attr' to a callable factory."""
    if ":" not in spec:
        raise ValueError(f"--factory must be 'pkg.mod:attr', got {spec!r}")
    mod_path, attr = spec.split(":", 1)
    mod = importlib.import_module(mod_path)
    fn = getattr(mod, attr)
    if not callable(fn):
        raise TypeError(f"{spec} is not callable")
    return fn


def seed_all(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)


def call_one(dataset, idx: int, seed_base: int):
    """Seed RNGs and call dataset[idx]. Returns (output, wall_time_s) or raises."""
    seed_all(seed_base + idx)
    t0 = time.perf_counter()
    out = dataset[idx]
    dt = time.perf_counter() - t0
    return out, dt


def run_line_profiler(dataset, indices: list[int], seed_base: int, profile_scope: str):
    """Returns the list of line_stats dicts (file, function, line, code, hits, time_s, pct)."""
    from line_profiler import LineProfiler  # type: ignore
    from line_profiler.scoping_policy import ScopingPolicy  # type: ignore

    prof = LineProfiler()
    cls = type(dataset)
    mod = sys.modules[cls.__module__]
    prof.add_class(cls, scoping_policy=ScopingPolicy.LOCAL, wrap=True)
    prof.add_module(mod, scoping_policy=ScopingPolicy.LOCAL, wrap=True)
    if profile_scope == "package":
        top = cls.__module__.split(".")[0]
        for name, m in list(sys.modules.items()):
            if name == cls.__module__:
                continue
            if (name == top or name.startswith(top + ".")) and m is not None:
                prof.add_module(m, scoping_policy=ScopingPolicy.LOCAL, wrap=True)

    prof.enable_by_count()
    try:
        for i in indices:
            seed_all(seed_base + i)
            _ = dataset[i]
    finally:
        prof.disable_by_count()

    stats = prof.get_stats()
    # Build per-line dicts. stats.timings: {(filename, lineno_start, name): [(lineno, hits, time_us)]}
    # Convert microseconds to seconds; compute pct vs sum of all timed lines.
    rows = []
    for (filename, _start_lineno, fn_name), entries in stats.timings.items():
        # Pull source lines for the `code` field.
        try:
            source = Path(filename).read_text().splitlines()
        except OSError:
            source = []
        for lineno, hits, time_us in entries:
            time_s = time_us * stats.unit  # stats.unit is the conversion to seconds
            code = source[lineno - 1].strip() if 0 < lineno <= len(source) else ""
            rows.append({
                "file": filename,
                "function": fn_name,
                "line": lineno,
                "code": code,
                "hits": hits,
                "time_s": time_s,
            })
    total = sum(r["time_s"] for r in rows) or 1.0
    for r in rows:
        r["pct"] = round(100.0 * r["time_s"] / total, 2)
    rows.sort(key=lambda r: r["time_s"], reverse=True)
    return rows


def run_dataloader_bench(dataset, num_workers: int, batch_size: int, batches: int) -> dict:
    """Run a short DataLoader iteration. Drops the first batch (worker warmup)."""
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        num_workers=num_workers,
        shuffle=False,
        drop_last=True,
    )
    timings: list[float] = []
    it = iter(loader)
    # Warmup batch
    try:
        next(it)
    except StopIteration:
        pass
    for _ in range(batches):
        t0 = time.perf_counter()
        try:
            next(it)
        except StopIteration:
            break
        timings.append(time.perf_counter() - t0)
    if not timings:
        return {
            "num_workers": num_workers,
            "batch_size": batch_size,
            "batches_measured": 0,
            "batches_per_sec": 0.0,
            "mean_batch_latency_s": 0.0,
        }
    mean_latency = sum(timings) / len(timings)
    return {
        "num_workers": num_workers,
        "batch_size": batch_size,
        "batches_measured": len(timings),
        "batches_per_sec": 1.0 / mean_latency if mean_latency > 0 else 0.0,
        "mean_batch_latency_s": mean_latency,
    }
```

- [ ] **Step 2: Add the `cmd_baseline` function**

```python
def cmd_baseline(args) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "baseline").mkdir(exist_ok=True)

    factory = load_factory(args.factory)
    dataset = factory()

    if args.indices:
        indices = [int(x) for x in args.indices.split(",")]
    else:
        indices = list(range(args.num_indices))
    seed_base = args.seed_base

    # Determinism self-check: call each index twice, compare.
    per_call_times: list[float] = []
    cached_outputs: list = []
    for i in indices:
        out_a, dt = call_one(dataset, i, seed_base)
        out_b, _ = call_one(dataset, i, seed_base)
        ok, diff_path, summary = deep_equal(out_a, out_b)
        if not ok:
            payload = {
                "factory": args.factory,
                "indices": indices,
                "seed_base": seed_base,
                "equality_mode": "non_deterministic",
                "first_diff_path": diff_path,
                "summary": summary,
            }
            (out_dir / "baseline.json").write_text(json.dumps(payload, indent=2))
            return 0
        per_call_times.append(dt)
        cached_outputs.append(out_a)

    # Cache outputs.
    for i, out in zip(indices, cached_outputs):
        with open(out_dir / "baseline" / f"{i}.pkl", "wb") as f:
            pickle.dump(out, f)

    mean_per_call = sum(per_call_times) / len(per_call_times)
    reliable = mean_per_call >= RELIABLE_LINE_STATS_THRESHOLD_S

    # Line profiler.
    line_stats = run_line_profiler(dataset, indices, seed_base, args.profile_scope)

    # DataLoader bench. (Re-instantiate so workers don't share state from above.)
    bench_dataset = factory()
    bench = run_dataloader_bench(
        bench_dataset, args.num_workers, args.batch_size, args.bench_batches
    )

    payload = {
        "factory": args.factory,
        "indices": indices,
        "seed_base": seed_base,
        "equality_mode": "strict",
        "reliable_line_stats": reliable,
        "per_call_wall_time_s": {
            "mean": mean_per_call,
            "indices": per_call_times,
        },
        "line_stats": line_stats,
        "dataloader_bench": bench,
    }
    (out_dir / "baseline.json").write_text(json.dumps(payload, indent=2))
    return 0
```

- [ ] **Step 3: Wire up the argparse subcommand**

Replace the stub `main()` with:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="profile_getitem.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_b = sub.add_parser("baseline")
    p_b.add_argument("--factory", required=True, help="pkg.mod:attr factory function")
    p_b.add_argument("--num-indices", type=int, default=8)
    p_b.add_argument("--indices", type=str, default="", help="comma-separated, overrides --num-indices")
    p_b.add_argument("--profile-scope", choices=["local", "package"], default="local")
    p_b.add_argument("--num-workers", type=int, default=4)
    p_b.add_argument("--batch-size", type=int, default=16)
    p_b.add_argument("--bench-batches", type=int, default=50)
    p_b.add_argument("--seed-base", type=int, default=0)
    p_b.add_argument("--out-dir", type=str, default=".getitem-profile")
    p_b.set_defaults(func=cmd_baseline)

    p_m = sub.add_parser("measure")
    # Filled in by Task 3.
    p_m.set_defaults(func=lambda a: (print("not yet implemented", file=sys.stderr), 1)[1])

    args = parser.parse_args(argv)
    return args.func(args)
```

- [ ] **Step 4: Run the verify command from the Verify section**

(Same multi-step bash + python block.) Expected: `OK strict` then `OK non_deterministic`.

If the verify fails on `pct > 50` for the hotspot line, double-check that `wrap=True` was passed to `add_class` — without it the bound `__getitem__` invoked through `dataset[idx]` may bypass the profiler.

If `equality_mode != "non_deterministic"` for the second fixture, verify that `nondeterministic_dataset.__getitem__` is using `os.urandom` (not anything seeded).

- [ ] **Step 5: Commit**

```bash
git add plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py
git commit -m "Implement baseline subcommand for getitem-profiler harness"
```

---

### Task 3: Implement `measure` subcommand end-to-end

**Goal:** Implement `profile_getitem.py measure` — load the (potentially edited) factory, equality-check against the cached baseline outputs, re-profile, compute `delta_vs_baseline` and `delta_vs_prev_accepted`, write `measure-N.json`. Failures (equality mismatch, raised exception in `__getitem__`, dataloader-bench failure) all surface through the `equality.passed: false` shape — no special status codes.

**Files:**

- Modify: `plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py`

**Acceptance Criteria:**

- [ ] `profile_getitem.py measure --factory ... --baseline-dir ...` writes the next available `measure-N.json`
- [ ] On the unmodified `tiny_image_dataset`, `equality.passed == true` and `delta_vs_prev_accepted.per_call_speedup_x ≈ 1.0` (within ±10%)
- [ ] If the user edits `tiny_image_dataset` to vectorize the per-pixel loop (`out = arr * 2.0 - 1.0`), `equality.passed == true` and `delta_vs_prev_accepted.per_call_speedup_x > 1.5` (the loop is the dominant cost)
- [ ] If the user edits `tiny_image_dataset` to change shapes (e.g. drop a channel), `equality.passed == false` and `first_diff_path` names the differing leaf
- [ ] If `__getitem__` raises during measurement, output JSON has `equality.passed == false` and `summary` starts with `"raised "`
- [ ] `delta_vs_prev_accepted` is computed against the most recent `measure-K.json` with `equality.passed == true`, falling back to `baseline.json` if none
- [ ] Exit code is `0` on equality failure (not an error — this is normal flow); non-zero only on harness-level failures (e.g., baseline-dir missing)

**Verify:**

```bash
# Reuse the baseline directory from Task 2's verify.
BASELINE_DIR=/tmp/getitem-profile-test
cd plugins/ml-research/skills/getitem-profiler

# Case 1: unmodified factory → equality passes, speedup near 1.0
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py measure \
    --factory tiny_image_dataset:make_dataset \
    --baseline-dir $BASELINE_DIR && \
python3 -c "
import json, pathlib, glob
files = sorted(glob.glob('$BASELINE_DIR/measure-*.json'))
m = json.loads(pathlib.Path(files[-1]).read_text())
assert m['equality']['passed'] is True, m
sp = m['delta_vs_prev_accepted']['per_call_speedup_x']
assert 0.85 < sp < 1.15, f'speedup unexpectedly far from 1.0: {sp}'
print('OK unchanged')
"

# Case 2: vectorize the hotspot → equality passes, speedup > 1.5
cp tests/fixtures/tiny_image_dataset.py /tmp/tiny_image_dataset.py.bak
python3 -c "
import pathlib
p = pathlib.Path('tests/fixtures/tiny_image_dataset.py')
src = p.read_text()
new = src.replace(
    '        out = np.empty_like(arr)\n        for i in range(self.side):\n            for j in range(self.side):\n                out[i, j] = arr[i, j] * 2.0 - 1.0\n',
    '        out = arr * 2.0 - 1.0\n'
)
assert new != src, 'pattern not found — fixture text drift'
p.write_text(new)
"
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py measure \
    --factory tiny_image_dataset:make_dataset \
    --baseline-dir $BASELINE_DIR && \
python3 -c "
import json, pathlib, glob
files = sorted(glob.glob('$BASELINE_DIR/measure-*.json'))
m = json.loads(pathlib.Path(files[-1]).read_text())
assert m['equality']['passed'] is True, m
sp = m['delta_vs_prev_accepted']['per_call_speedup_x']
assert sp > 1.5, f'expected speedup > 1.5, got {sp}'
print('OK vectorized')
"
# Restore the fixture
cp /tmp/tiny_image_dataset.py.bak tests/fixtures/tiny_image_dataset.py

# Case 3: shape-changing edit → equality fails
python3 -c "
import pathlib
p = pathlib.Path('tests/fixtures/tiny_image_dataset.py')
src = p.read_text()
# Drop a channel: 'permute(2, 0, 1).contiguous()' → '[:2].permute(2, 0, 1).contiguous()'  ←  wrong shape after permute, so simulate by slicing first dim of the np array
new = src.replace(
    '        img = torch.from_numpy(out).permute(2, 0, 1).contiguous()\n',
    '        img = torch.from_numpy(out[:, :, :2]).permute(2, 0, 1).contiguous()\n'
)
assert new != src
p.write_text(new)
"
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py measure \
    --factory tiny_image_dataset:make_dataset \
    --baseline-dir $BASELINE_DIR && \
python3 -c "
import json, pathlib, glob
files = sorted(glob.glob('$BASELINE_DIR/measure-*.json'))
m = json.loads(pathlib.Path(files[-1]).read_text())
assert m['equality']['passed'] is False, m
assert m['equality'].get('first_diff_path'), m
print('OK shape-change')
"
# Restore
cp /tmp/tiny_image_dataset.py.bak tests/fixtures/tiny_image_dataset.py

# Case 4: raise → equality fails with 'raised'
python3 -c "
import pathlib
p = pathlib.Path('tests/fixtures/tiny_image_dataset.py')
src = p.read_text()
new = src.replace(
    '    def __getitem__(self, idx: int) -> dict:\n',
    '    def __getitem__(self, idx: int) -> dict:\n        raise RuntimeError(\"injected for testing\")\n'
)
assert new != src
p.write_text(new)
"
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py measure \
    --factory tiny_image_dataset:make_dataset \
    --baseline-dir $BASELINE_DIR && \
python3 -c "
import json, pathlib, glob
files = sorted(glob.glob('$BASELINE_DIR/measure-*.json'))
m = json.loads(pathlib.Path(files[-1]).read_text())
assert m['equality']['passed'] is False, m
assert m['equality']['summary'].startswith('raised '), m
print('OK raised')
"
# Restore
cp /tmp/tiny_image_dataset.py.bak tests/fixtures/tiny_image_dataset.py
```

Expected: `OK unchanged`, `OK vectorized`, `OK shape-change`, `OK raised`.

**Steps:**

- [ ] **Step 1: Add `cmd_measure` and helpers**

Add to `profile_getitem.py`:

```python
def _next_measure_path(out_dir: Path) -> Path:
    n = 1
    while (out_dir / f"measure-{n}.json").exists():
        n += 1
    return out_dir / f"measure-{n}.json"


def _latest_accepted_measure(out_dir: Path) -> dict | None:
    """Return the most recent measure-N.json with equality.passed == true, or None."""
    files = sorted(out_dir.glob("measure-*.json"),
                   key=lambda p: int(p.stem.split("-")[1]),
                   reverse=True)
    for f in files:
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("equality", {}).get("passed") is True:
            return data
    return None


def _compute_delta(curr_mean: float, curr_bench_bps: float,
                   ref_mean: float, ref_bench_bps: float) -> dict:
    return {
        "per_call_speedup_x": (ref_mean / curr_mean) if curr_mean > 0 else 0.0,
        "dataloader_speedup_x": (curr_bench_bps / ref_bench_bps) if ref_bench_bps > 0 else 0.0,
    }


def cmd_measure(args) -> int:
    baseline_dir = Path(args.baseline_dir)
    baseline_path = baseline_dir / "baseline.json"
    if not baseline_path.exists():
        print(f"baseline.json not found at {baseline_path}", file=sys.stderr)
        return 2
    baseline = json.loads(baseline_path.read_text())
    if baseline.get("equality_mode") == "non_deterministic":
        print("baseline is non-deterministic; cannot measure", file=sys.stderr)
        return 2

    factory = load_factory(args.factory)
    dataset = factory()

    indices = baseline["indices"]
    seed_base = baseline["seed_base"]

    measure_path = _next_measure_path(baseline_dir)

    # Equality check (fail-fast: bail at first mismatch or exception).
    per_call_times: list[float] = []
    for i in indices:
        try:
            seed_all(seed_base + i)
            t0 = time.perf_counter()
            out = dataset[i]
            dt = time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001
            payload = {
                "equality": {
                    "passed": False,
                    "first_diff_path": f"outputs[{i}]",
                    "summary": f"raised {type(e).__name__}: {e}",
                },
            }
            measure_path.write_text(json.dumps(payload, indent=2))
            return 0
        with open(baseline_dir / "baseline" / f"{i}.pkl", "rb") as f:
            cached = pickle.load(f)
        ok, diff_path, summary = deep_equal(out, cached, _path=f"outputs[{i}]")
        if not ok:
            payload = {
                "equality": {"passed": False, "first_diff_path": diff_path, "summary": summary},
            }
            measure_path.write_text(json.dumps(payload, indent=2))
            return 0
        per_call_times.append(dt)

    # Equality passed → re-profile + bench.
    line_stats = run_line_profiler(dataset, indices, seed_base, args.profile_scope)

    bench_dataset = factory()
    try:
        bench = run_dataloader_bench(
            bench_dataset, args.num_workers, args.batch_size, args.bench_batches
        )
    except Exception as e:  # noqa: BLE001
        payload = {
            "equality": {
                "passed": False,
                "first_diff_path": "<dataloader>",
                "summary": f"dataloader bench raised {type(e).__name__}: {e}",
            },
        }
        measure_path.write_text(json.dumps(payload, indent=2))
        return 0

    mean_per_call = sum(per_call_times) / len(per_call_times)
    baseline_mean = baseline["per_call_wall_time_s"]["mean"]
    baseline_bps = baseline["dataloader_bench"]["batches_per_sec"]

    prev = _latest_accepted_measure(baseline_dir)
    if prev:
        prev_mean = prev["per_call_wall_time_s"]["mean"]
        prev_bps = prev["dataloader_bench"]["batches_per_sec"]
    else:
        prev_mean = baseline_mean
        prev_bps = baseline_bps

    payload = {
        "equality": {"passed": True},
        "per_call_wall_time_s": {"mean": mean_per_call, "indices": per_call_times},
        "delta_vs_baseline": _compute_delta(mean_per_call, bench["batches_per_sec"],
                                            baseline_mean, baseline_bps),
        "delta_vs_prev_accepted": _compute_delta(mean_per_call, bench["batches_per_sec"],
                                                 prev_mean, prev_bps),
        "line_stats": line_stats,
        "dataloader_bench": bench,
    }
    measure_path.write_text(json.dumps(payload, indent=2))
    return 0
```

- [ ] **Step 2: Wire up the `measure` argparse subcommand**

Replace the stub `p_m` block in `main()` with:

```python
    p_m = sub.add_parser("measure")
    p_m.add_argument("--factory", required=True)
    p_m.add_argument("--baseline-dir", required=True)
    p_m.add_argument("--profile-scope", choices=["local", "package"], default="local")
    p_m.add_argument("--num-workers", type=int, default=4)
    p_m.add_argument("--batch-size", type=int, default=16)
    p_m.add_argument("--bench-batches", type=int, default=50)
    p_m.set_defaults(func=cmd_measure)
```

- [ ] **Step 3: Run the verify cases from the Verify section**

This is four cases — run each in order and check for the four `OK ...` outputs.

If a step fails: the most likely culprit is module re-importation. `cmd_measure` calls `load_factory` which calls `importlib.import_module`. After the test edits the fixture file, the new `measure` invocation is a fresh process, so the import is fresh. (No `importlib.reload` needed.)

- [ ] **Step 4: Commit**

```bash
git add plugins/ml-research/skills/getitem-profiler/scripts/profile_getitem.py
git commit -m "Implement measure subcommand for getitem-profiler harness"
```

---

### Task 4: Write the SKILL.md orchestration prompt

**Goal:** Replace the Task 0 frontmatter stub with the full orchestration prompt that drives the greedy edit loop. This is the agent-facing artifact.

**Files:**

- Modify: `plugins/ml-research/skills/getitem-profiler/SKILL.md`

**Acceptance Criteria:**

- [ ] Frontmatter has `name: getitem-profiler` and a `description:` matching spec § "SKILL.md → frontmatter" triggering language
- [ ] Body has these sections in order: **Identity**, **Setup (once per session)**, **The greedy loop**, **Hard rules**, **Caveat layer**, **Termination summary**
- [ ] The greedy loop section names the three termination conditions (line < 5%, 3 consecutive failures, user interrupt)
- [ ] The hard rules section names: edit-scope limit, no mutable cross-call state, no validation-set edits, one edit per commit, branch-only edits
- [ ] The caveat layer matches the wording in spec § "Caveat layer"
- [ ] The greedy-loop step "Decision" uses `delta_vs_prev_accepted.per_call_speedup_x` (not `delta_vs_baseline`) and the 1.05× threshold
- [ ] Total length ~150–200 lines (target from spec § "Files → Plugin-shipped")

**Verify:**

```bash
python3 -c "
import pathlib, re
p = pathlib.Path('plugins/ml-research/skills/getitem-profiler/SKILL.md')
text = p.read_text()
# Frontmatter
assert text.startswith('---\n'), 'missing frontmatter'
fm_end = text.index('\n---\n', 4)
fm = text[4:fm_end]
assert 'name: getitem-profiler' in fm, fm
assert 'description:' in fm, fm
body = text[fm_end + 5:]
# Required sections
for hdr in ['## Identity', '## Setup', '## The greedy loop', '## Hard rules', '## Caveat layer', '## Termination summary']:
    assert hdr in body, f'missing section: {hdr}'
# Decision rule references the right delta
assert 'delta_vs_prev_accepted' in body, 'decision rule must reference delta_vs_prev_accepted'
assert '1.05' in body, 'threshold missing'
# Termination conditions
assert '5%' in body and 'consecutive' in body and 'interrupt' in body, 'termination conditions incomplete'
# Hard rules
for rule in ['cross-call state', 'validation', 'one edit', 'side branch']:
    assert rule in body, f'hard rule missing: {rule}'
# Length
n_lines = text.count('\n')
assert 100 < n_lines < 280, f'SKILL.md length {n_lines} outside target range'
print('OK')
"
```

Expected: `OK`

**Steps:**

- [ ] **Step 1: Replace `SKILL.md` with the full prompt**

The body assembles content from spec sections in this order. Cross-reference the spec's wording where exact phrasing matters (the caveat layer is verbatim).

```markdown
---
name: getitem-profiler
description: Profile Dataset.__getitem__ with line_profiler and greedily optimize the slowest line on a side branch, gated by output equality and a per-call speedup threshold. Use when the user says "__getitem__ is slow", "profile my dataset", "speed up my dataloader", "find the bottleneck in my dataset class", or supplies a factory function and asks for optimization.
---

## Identity

Greedy line-level optimizer for `Dataset.__getitem__`. The harness at `scripts/profile_getitem.py` is the source of truth for measurement — never guess at timings, never decide acceptance from memory. After every edit, re-invoke the harness and read its JSON.

You do not read the user's full dataset module up front. You read just enough surrounding code per edit to understand the line being targeted. The harness handles all instrumentation, seeding, equality checks, and benchmarking.

## Setup (once per session)

Confirm with the user:

1. **Factory path** — `pkg.mod:make_dataset` returning a ready dataset instance. Document the one-liner template if the user doesn't have one yet:
   ```python
   def make_dataset():
       from mypkg.dataset import MyDataset
       return MyDataset(root="/path", split="train", transform=...)
   ```
2. **`--num-indices`** — default 8.
3. **`--profile-scope`** — default `local` (only the dataset class + its defining module). Use `package` if the user's transforms / IO helpers live in sibling modules of the same top-level package.
4. **`--num-workers`** for the DataLoader bench — default 4.

Then:

1. Add `.getitem-profile/` to `.gitignore` if not already present.
2. Create the side branch: `git checkout -b getitem-profile/<dataset-slug>-<YYYYMMDD-HHMM>` off the user's current `HEAD`.
3. Run `python scripts/profile_getitem.py baseline --factory <factory> --num-indices <N> --profile-scope <scope> --num-workers <W> --out-dir .getitem-profile/`.
4. Read `.getitem-profile/baseline.json`.
5. Bail if either:
   - `equality_mode == "non_deterministic"` — surface the `first_diff_path` to the user, name the leaf that differs, offer two paths: (a) supply `--equality-fn pkg.mod:fn` that tolerates the non-determinism, (b) bail. Never silently fall back to tolerance.
   - `reliable_line_stats == false` — tell the user the dataset is already fast (mean per-call < ~1 ms); wins here would be in the noise.
6. Otherwise, show the user a brief table of the top-5 slowest lines + the baseline DataLoader throughput so they know the starting point.

Surface the **caveat layer** (verbatim, see below) at session start.

## The greedy loop

State you maintain across iterations:
- `failed_lines: set[(file, line)]` — lines we've already tried and failed on.
- `consecutive_failures: int` — reset to 0 on accept.
- `accepted_commits: list[str]` — for the final summary.

Per iteration:

1. **Pick the next-slowest line** from the most recent JSON's `line_stats` (sorted by `pct` descending) that is not in `failed_lines` and whose `file` lives inside the dataset module's directory or sibling modules in the same top-level package. If the slowest line is outside this scope (a `--profile-scope=package` artifact, e.g., a third-party helper), note it and skip to the next.
2. **Termination checks:**
   - If the targeted line's `pct` < 5% → stop (diminishing returns).
   - If `consecutive_failures >= 3` → stop.
   - If the user has interrupted → stop.
3. **Read just enough**: the function the line is in, ~20 surrounding lines, and any helper it calls. Don't read the whole module.
4. **Propose one concrete edit.** Common-win categories (vocabulary, not a checklist):
   - vectorize a Python loop into numpy/torch ops
   - replace PIL with `cv2` or `torchvision.io` for decode
   - cache an expensive constant in `__init__`
   - replace per-call file open with mmap or a pre-indexed handle
   - construct tensors on the right dtype/device once
   - remove a redundant `.copy()` or `.contiguous()`
   - pre-tokenize / pre-resize at dataset init time
5. **Apply the edit** (single Edit tool call). Do NOT commit yet.
6. **Run** `python scripts/profile_getitem.py measure --factory <factory> --baseline-dir .getitem-profile/ --profile-scope <scope> --num-workers <W>`. Read the new `measure-N.json`.
7. **Decision** — use `delta_vs_prev_accepted.per_call_speedup_x`:
   - **Equality failed** → `git restore <changed_file>`. Add the line to `failed_lines`. `consecutive_failures += 1`.
   - **Equality passed but speedup < 1.05×** → same `git restore` path. Smaller wins are noise.
   - **Equality passed and speedup ≥ 1.05×** → `git add <file>` + `git commit -m "perf(<file>:<line>): <one-line summary>"`. Reset `consecutive_failures = 0`. Append an entry to `.getitem-profile/session.md`.
8. Loop.

After each accepted edit, append to `.getitem-profile/session.md`:

```markdown
## Edit <N> — <one-line summary>
- target: <file>:<line> (was <pct>% of __getitem__)
- per-call: <before> ms → <after> ms (<delta_vs_prev_accepted.per_call_speedup_x>x)
- dataloader: <before> batches/s → <after> batches/s (<delta_vs_prev_accepted.dataloader_speedup_x>x)
- commit: <short SHA>
```

Append rejected attempts under a separate `## Rejected` section: target line + brief reason.

## Hard rules

- **Edit-scope limit.** Edit only inside the dataset class / its defining module / sibling modules in the same top-level package, scoped by `--profile-scope`. Never broaden silently. If the slowest line is outside scope, skip it.
- **No mutable cross-call state.** Caching `__getitem__` results across calls is forbidden. The per-index equality check would pass while DataLoader workers (which fork the dataset) silently diverge.
- **No validation-set edits.** Don't touch validation code or any code path outside `__getitem__`'s call graph.
- **One edit per commit.** No bundling — defeats per-line attribution. The harness's accept/reject decision is per-edit; mixing two changes in one commit makes attribution impossible.
- **Side branch only.** Never touch `main` or the user's prior branch. The skill never deletes the side branch — the user merges or discards.

## Caveat layer

Surface this at session start AND in the final summary:

> Per-call timings come from in-process measurement; under a real DataLoader, fixed costs (worker startup, IPC, fork-time imports) won't show up here. The DataLoader micro-benchmark gives a sanity check, but wins below ~50 µs per call may not translate. Wins should generally hold across distributed ranks since each rank's workers are independent.

## Termination summary

When the loop terminates (any condition), print:

- starting per-call wall time (from `baseline.json`)
- ending per-call wall time (from the most recent accepted measure)
- total speedup (`delta_vs_baseline.per_call_speedup_x`)
- DataLoader throughput before/after
- list of accepted commits with one-line summaries
- list of rejected target lines with brief reasons
- the caveat layer (repeated)
- the branch name; instruct the user to review and merge/discard

## Resumption

If a session is interrupted and the user re-invokes the skill: detect an existing `.getitem-profile/` dir + `getitem-profile/...` branch; read `session.md` to recover `failed_lines` and `accepted_commits`; resume the loop without re-baselining. The cached outputs in `.getitem-profile/baseline/` and `baseline.json` remain authoritative.
```

- [ ] **Step 2: Run the verify command**

Expected: `OK`

If the length check fails: trim or expand sections to bring `n_lines` into the target range. The body is meant to be ~150–200 lines (the verify allows up to 280 to give some slack for header overhead).

- [ ] **Step 3: Commit**

```bash
git add plugins/ml-research/skills/getitem-profiler/SKILL.md
git commit -m "Write getitem-profiler SKILL.md orchestration prompt"
```

---

### Task 5: End-to-end smoke test

**Goal:** Exercise the skill+harness combination on the synthetic fixture in a way that mimics what the skill would actually do — baseline, edit, measure, commit-or-revert. This is the final integration check before the skill is usable.

**Files:**

- No source changes. May create / clean up `/tmp/getitem-smoke/` during the test.

**Acceptance Criteria:**

- [ ] Running the full sequence (baseline → vectorize the loop → measure → confirm acceptance threshold met → restore fixture) completes with no errors
- [ ] `delta_vs_prev_accepted.per_call_speedup_x` for the vectorized edit is ≥ 1.5 (the loop is the dominant cost; vectorizing is a clear win)
- [ ] After restoring the fixture, the original baseline still applies (no leftover state)

**Verify:**

```bash
set -euo pipefail
cd plugins/ml-research/skills/getitem-profiler

OUT=/tmp/getitem-smoke
rm -rf "$OUT"

# 1. Baseline.
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py baseline \
    --factory tiny_image_dataset:make_dataset \
    --num-indices 4 --num-workers 2 --bench-batches 10 \
    --out-dir "$OUT"
python3 -c "
import json, pathlib
b = json.loads(pathlib.Path('$OUT/baseline.json').read_text())
assert b['equality_mode'] == 'strict'
assert b['reliable_line_stats'] is True
print('baseline OK, mean per-call =', b['per_call_wall_time_s']['mean'])
"

# 2. Apply the obvious optimization (vectorize the per-pixel loop).
cp tests/fixtures/tiny_image_dataset.py /tmp/tiny_image_dataset.py.bak
python3 -c "
import pathlib
p = pathlib.Path('tests/fixtures/tiny_image_dataset.py')
src = p.read_text()
new = src.replace(
    '        out = np.empty_like(arr)\n        for i in range(self.side):\n            for j in range(self.side):\n                out[i, j] = arr[i, j] * 2.0 - 1.0\n',
    '        out = arr * 2.0 - 1.0\n'
)
assert new != src
p.write_text(new)
"

# 3. Measure.
PYTHONPATH=tests/fixtures python3 scripts/profile_getitem.py measure \
    --factory tiny_image_dataset:make_dataset \
    --baseline-dir "$OUT" --num-workers 2 --bench-batches 10
python3 -c "
import json, pathlib, glob
files = sorted(glob.glob('$OUT/measure-*.json'))
m = json.loads(pathlib.Path(files[-1]).read_text())
assert m['equality']['passed'] is True
sp = m['delta_vs_prev_accepted']['per_call_speedup_x']
assert sp >= 1.5, f'expected speedup >= 1.5, got {sp}'
print('measure OK, speedup =', sp)
"

# 4. Restore + confirm clean state.
cp /tmp/tiny_image_dataset.py.bak tests/fixtures/tiny_image_dataset.py
rm /tmp/tiny_image_dataset.py.bak
rm -rf "$OUT"

echo "SMOKE OK"
```

Expected last line: `SMOKE OK`.

**Steps:**

- [ ] **Step 1: Run the verify block end-to-end**

If anything fails, fix the issue in the relevant earlier task (don't paper over it here). The smoke test is the gate — failures here mean an upstream task didn't actually work.

- [ ] **Step 2: Commit (if any fixes were needed)**

If the smoke test passed first try, no commit needed. If you had to fix a bug, commit the fix:

```bash
git add -A plugins/ml-research/skills/getitem-profiler/
git commit -m "Fix smoke-test failure in getitem-profiler"
```

- [ ] **Step 3: Final review**

Read `plugins/ml-research/skills/getitem-profiler/SKILL.md` end-to-end one more time. Check that nothing references files or arguments that don't exist (`scripts/profile_getitem.py` exists; `--factory`, `--num-indices`, `--profile-scope`, `--num-workers`, `--out-dir`, `--baseline-dir` all match what `argparse` accepts).

Mark this task complete only if the SKILL.md ↔ argparse surface matches.

---

## Self-review notes

Cross-checked against the spec:

- Spec § "Architecture" → Task 0 + the file-structure section above.
- Spec § "Data model → baseline.json / measure-N.json" → Tasks 2 + 3 produce the exact JSON shapes.
- Spec § "Phase 0: Setup" → SKILL.md `## Setup` section in Task 4.
- Spec § "Phase 1: Greedy loop" → SKILL.md `## The greedy loop` section in Task 4.
- Spec § "Helper script (`profile_getitem.py`)" → Tasks 2 + 3.
- Spec § "Edge cases" → covered:
  - Non-deterministic dataset → Task 2 acceptance + verify (uses `nondeterministic_dataset` fixture).
  - Too-fast dataset → Task 2 (`reliable_line_stats: false` heuristic, threshold 1 ms).
  - Edit raises → Task 3 case 4.
  - DataLoader bench fails → Task 3 has try/except around `run_dataloader_bench`.
  - No-op edit → Task 3 verify case 1 demonstrates speedup ≈ 1.0; SKILL.md's 1.05× threshold rejects it.
  - Tied slowest lines → `line_stats` is sorted descending, ties resolve by Python's stable sort (file order); SKILL.md's "next-slowest line" picker is deterministic given the JSON.
  - Out-of-scope subfunction → SKILL.md "Edit-scope limit" hard rule covers it; Task 4 acceptance includes the rule.
  - Resumption → SKILL.md `## Resumption` section.
- Spec § "Hard rules" → SKILL.md `## Hard rules` section, Task 4 acceptance enumerates each.
- Spec § "Caveat layer" → SKILL.md `## Caveat layer` section, verbatim.
- Spec § "Out of scope" → not implemented (correct).

No type/method-name drift across tasks: `deep_equal`, `load_factory`, `seed_all`, `call_one`, `run_line_profiler`, `run_dataloader_bench`, `cmd_baseline`, `cmd_measure` are defined once and referenced consistently.
