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
