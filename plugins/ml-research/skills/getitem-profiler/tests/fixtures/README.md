# Test fixtures

Synthetic datasets used to exercise `scripts/profile_getitem.py` during development. There is no pytest suite — fixtures are imported via the harness's `--factory` flag.

- `tiny_image_dataset.py:make_dataset` — deterministic under seeded RNGs, intentionally slow per-pixel loop in `__getitem__` so line_profiler has a clear hotspot to surface.
- `nondeterministic_dataset.py:make_dataset` — uses `os.urandom`, deliberately bypassing standard RNGs. The harness should detect this and emit `equality_mode: non_deterministic` in `baseline.json`.
