#!/usr/bin/env python3
"""getitem-profiler measurement harness.

See plugins/ml-research/skills/getitem-profiler/SKILL.md for the orchestration
prompt that drives this script.
"""
from __future__ import annotations

import argparse
import importlib
import json
import pickle
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from torch.utils.data import DataLoader


RELIABLE_LINE_STATS_THRESHOLD_S = 1e-3  # below this, line_profiler overhead dominates


def deep_equal(a: Any, b: Any, _path: str = "outputs") -> tuple[bool, str | None, str | None]:
    """Recursively compare two outputs.

    Returns (True, None, None) on equal; (False, first_diff_path, summary) on mismatch.
    Handles dicts, lists, tuples, torch tensors, numpy arrays, PIL Images, and
    primitive types. Unknown leaf types fall back to ==.
    """
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
        if type(a) is not type(b):
            return False, _path, f"type mismatch: {type(a).__name__} vs {type(b).__name__}"
        return False, _path, f"values differ: {a!r} vs {b!r}"
    except Exception as e:  # noqa: BLE001
        return False, _path, f"comparison failed for {type(a).__name__}: {e}"


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
    prof.add_class(cls, scoping_policy=ScopingPolicy.CHILDREN, wrap=True)
    prof.add_module(mod, scoping_policy=ScopingPolicy.CHILDREN, wrap=True)
    if profile_scope == "package":
        top = cls.__module__.split(".")[0]
        for name, m in list(sys.modules.items()):
            if name == cls.__module__:
                continue
            if (name == top or name.startswith(top + ".")) and m is not None:
                prof.add_module(m, scoping_policy=ScopingPolicy.CHILDREN, wrap=True)

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


if __name__ == "__main__":
    sys.exit(main())
