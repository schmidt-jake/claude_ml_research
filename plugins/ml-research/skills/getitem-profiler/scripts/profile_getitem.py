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
