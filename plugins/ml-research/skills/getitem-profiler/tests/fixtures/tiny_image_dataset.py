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
