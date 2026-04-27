# `getitem-profiler` skill — design

Date: 2026-04-26
Issue: #4
Status: spec drafted, awaiting user review

## Motivation

`Dataset.__getitem__` is a common dataloader bottleneck. Optimizing it is mechanical work — profile, find the slowest line, rewrite it, verify the rewrite preserves outputs and actually saves time, repeat — but doing it by hand is tedious and easy to get wrong (e.g., introducing caching that breaks correctness, accepting an "improvement" that's just measurement noise, missing that the win disappears under multi-worker DataLoader IPC).

This skill automates that loop on a side branch, with two safety nets baked in: every edit must produce byte-identical outputs against a cached baseline (under seeded RNGs), and every edit must deliver a meaningful per-call speedup. Failed edits revert automatically; the user reviews the resulting branch as a single object at the end.

## Constraints

- **Runs inside Claude Code** as a skill in the `ml-research` plugin. Same shape as the other skills: thin SKILL.md prompt + a Python helper script for the deterministic, measurable work.
- **Single-process, in-process measurement.** Profiling uses `line_profiler` programmatically against a live dataset instance — not via `kernprof` against a launched script. A short `DataLoader(num_workers>0)` micro-benchmark serves as a reality check after each accepted edit.
- **Multi-rank distributed profiling is out of scope**, mention-only. Wins should generally hold across ranks since each rank's workers are independent.
- **Autonomous on a side branch.** No per-edit user confirmation. Equality + speedup checks gate every commit; rejected edits auto-revert.
- **Determinism via seeded RNGs**, not `torch.use_deterministic_algorithms(True)` or env-var gymnastics. `torch.manual_seed`, `np.random.seed`, `random.seed` are reset before every `dataset[i]` call. If outputs still aren't reproducible under that, the skill bails out rather than silently relaxing equality.

## Architecture

```
plugins/ml-research/skills/getitem-profiler/
├── SKILL.md                  # orchestration prompt (~150-200 lines)
└── scripts/
    └── profile_getitem.py    # measurement harness, JSON in/out
```

**Two actors:**

| Actor | Owns |
|---|---|
| **Skill (Claude)** | Greedy edit loop on a side branch. Picks slowest line, reads surrounding code, proposes one edit, applies it, invokes the harness, accepts or reverts based on the JSON. Stops on diminishing returns / consecutive failures / user interrupt. Writes a one-line entry to `session.md` per accepted edit. |
| **Harness (`profile_getitem.py`)** | The only thing that touches the user's dataset. Instantiates from a factory function, seeds RNGs around each call, runs `line_profiler` on `__getitem__` + auto-discovered subfunctions, runs the DataLoader micro-benchmark, dumps/compares cached baseline outputs, prints a JSON report. Pure measurement; no edits, no judgment. |

The harness is a single CLI with two subcommands:

```
profile_getitem.py baseline --factory pkg.mod:make_dataset \
    [--num-indices N] [--indices "0,1,2,..."] \
    [--profile-scope {local,package}] \
    [--num-workers W] [--bench-batches B] \
    [--equality-fn pkg.mod:fn] \
    [--out-dir DIR]

profile_getitem.py measure  --factory pkg.mod:make_dataset \
    --baseline-dir DIR
```

`baseline` runs once at session start (caches outputs, records starting timings). `measure` runs after each Claude edit (re-runs the same indices, checks equality against the cached outputs, returns per-line timings + DataLoader bench).

The cache lives in `.getitem-profile/` by default and is gitignored. The skill ensures `.getitem-profile/` is in `.gitignore` at session start.

## Data model

### `baseline.json`

Written by `profile_getitem.py baseline`. Read by the skill once at session start.

```json
{
  "factory": "pkg.mod:make_dataset",
  "indices": [0, 1, 2, 3, 4, 5, 6, 7],
  "seed_base": 0,
  "equality_mode": "strict",
  "reliable_line_stats": true,
  "per_call_wall_time_s": {"mean": 0.0123, "indices": [0.0119, 0.0124, ...]},
  "line_stats": [
    {
      "file": "mypkg/dataset.py",
      "function": "MyDataset.__getitem__",
      "line": 42,
      "code": "img = Image.open(path).convert(\"RGB\")",
      "hits": 8,
      "time_s": 0.080,
      "pct": 65.1
    }
  ],
  "dataloader_bench": {
    "num_workers": 4,
    "batch_size": 16,
    "batches_measured": 50,
    "batches_per_sec": 12.3,
    "mean_batch_latency_s": 0.081
  }
}
```

`equality_mode` is `strict` in the normal case. The harness sets it to `non_deterministic` (and refuses to proceed past baseline) if calling `dataset[i]` twice with the same seed already produces different outputs — see "Edge cases" below.

`reliable_line_stats` is `false` if mean per-call time is below ~1 ms, signaling that line_profiler overhead dominates rankings.

### `measure-N.json`

Written by `profile_getitem.py measure`. `N` auto-increments per session. Read by the skill after each edit.

Success path:
```json
{
  "equality": {"passed": true},
  "per_call_wall_time_s": {"mean": 0.0089, "indices": [...]},
  "delta_vs_baseline": {
    "per_call_speedup_x": 1.38,
    "dataloader_speedup_x": 1.12
  },
  "line_stats": [...],
  "dataloader_bench": {...}
}
```

Equality-failed path:
```json
{
  "equality": {
    "passed": false,
    "first_diff_path": "outputs[0]['image']",
    "summary": "tensor shape (3,224,224) vs (3,225,225)"
  }
}
```

Exceptions during `dataset[i]` are reported through the same equality-failed shape (`"summary": "raised RuntimeError: ..."`). DataLoader benchmark failures (worker death, introduced pickling error) likewise surface as a failed measurement; no special status — failure is failure.

### `.getitem-profile/session.md`

Skill-maintained narrative artifact. One entry per accepted edit:

```markdown
## Edit 1 — Replace PIL.Image.open with torchvision.io.read_image
- target: mypkg/dataset.py:42 (was 65.1% of __getitem__)
- per-call: 12.3 ms → 8.9 ms (1.38x)
- dataloader: 12.3 batches/s → 13.8 batches/s (1.12x)
- commit: a1b2c3d
```

Plus a header listing the rejected attempts (target line + brief reason). The user reads this at the end to understand what the branch contains.

## Phase 0: Setup (once per session)

1. The skill confirms with the user:
   - factory path (`pkg.mod:make_dataset`)
   - `--num-indices` (default 8)
   - `--profile-scope` (default `local` — only the dataset class + its defining module; `package` walks sibling modules in the same top-level package, for projects whose transforms / IO helpers live there)
   - `--num-workers` for the DataLoader bench (default 4)
2. Add `.getitem-profile/` to `.gitignore` if not already present.
3. Create the side branch `getitem-profile/<dataset-slug>-<YYYYMMDD-HHMM>` off the user's current `HEAD`.
4. Run `profile_getitem.py baseline ...`.
5. Read `baseline.json`. If `equality_mode == "non_deterministic"` or `reliable_line_stats == false`, stop and surface the issue (see "Edge cases"). Otherwise, show the user a brief table of the top-5 slowest lines + baseline DataLoader throughput so they know what we're starting with.

## Phase 1: Greedy loop

Per iteration:

1. **Pick the next-slowest line** in `__getitem__` or a discovered subfunction that hasn't already been the target of a failed attempt this session.
2. **Termination checks:**
   - If the targeted line's `pct` is < 5% of `__getitem__` total → stop (diminishing returns).
   - If we've had 3 consecutive failed attempts → stop.
   - If the user has interrupted → stop.
3. **Read just enough** surrounding code: the function it's in, ~20 lines of context, and any helper it calls. Don't read the whole module.
4. **Propose one concrete edit.** SKILL.md enumerates common-win categories as a vocabulary (not a checklist):
   - vectorize a Python loop into numpy/torch ops
   - replace PIL with `cv2` or `torchvision.io` for decode
   - cache an expensive constant in `__init__`
   - replace per-call file open with mmap or a pre-indexed handle
   - construct tensors on the right dtype/device once
   - remove redundant copy / `.contiguous()`
   - pre-tokenize / pre-resize at dataset init time
5. **Apply the edit** (single Edit tool call). Commit on the branch with a message naming the targeted file:line.
6. **Run `profile_getitem.py measure ...`.** Read the JSON.
7. **Decision:**
   - **Equality failed** → `git revert HEAD --no-edit`. Increment consecutive-failure counter. Add the line to the session's failed-attempts set.
   - **Equality passed but per-call speedup < 1.05×** → same revert path. Threshold is "5% wall-time reduction at the dataset level"; smaller wins are noise.
   - **Equality passed and speedup ≥ 1.05×** → keep the commit. Reset the consecutive-failure counter. Append an entry to `session.md`. Loop.

After termination: print a final summary (starting per-call time, ending per-call time, total speedup, DataLoader throughput before/after, list of accepted commits, list of rejected lines). The branch is left for the user to merge or discard.

## Helper script (`profile_getitem.py`)

### `baseline` subcommand

1. Import factory (`importlib.import_module` + `getattr`), call it, get `dataset`.
2. **Determinism self-check:** for each index, seed RNGs (`torch.manual_seed`, `np.random.seed`, `random.seed` with `seed_base + i`), call `dataset[i]`, pickle the output. Then re-seed and re-call. If the second output doesn't equal the first, set `equality_mode: non_deterministic`, write `baseline.json` with `first_diff_path`, exit 0 (the skill handles the non-deterministic case).
3. **Cache outputs:** pickle each output to `<out-dir>/baseline/<i>.pkl`.
4. **Per-call wall time:** time each `dataset[i]` call (also under seed reset), record mean + per-index list. If mean < ~1 ms, set `reliable_line_stats: false`.
5. **Line profiling** — programmatic API (NOT `autoprofile.run` / `kernprof`):
   ```python
   from line_profiler import LineProfiler
   from line_profiler.scoping_policy import ScopingPolicy

   prof = LineProfiler()
   prof.add_class(type(dataset), scoping_policy=ScopingPolicy.LOCAL, wrap=True)
   prof.add_module(sys.modules[type(dataset).__module__],
                   scoping_policy=ScopingPolicy.LOCAL, wrap=True)
   if profile_scope == "package":
       for sibling in walk_sibling_modules(type(dataset).__module__):
           prof.add_module(sibling, scoping_policy=ScopingPolicy.LOCAL, wrap=True)

   prof.enable_by_count()
   for i in indices:
       seed_all(seed_base + i)
       _ = dataset[i]
   prof.disable_by_count()
   stats = prof.get_stats()
   ```
   `add_class` walks methods defined on the class. `add_module` picks up module-level helpers. `ScopingPolicy.LOCAL` keeps the profiler from recursing into third-party imports. `wrap=True` replaces methods so calls through the C-level `__getitem__` slot still hit the profiler.
6. **DataLoader benchmark:** wrap the dataset in `DataLoader(batch_size=B, num_workers=W)`, iterate `bench-batches` batches, drop the first batch (worker-warmup), record batches/sec + mean batch latency.
7. Write `baseline.json`.

### `measure` subcommand

1. Re-import factory (after Claude's edit), instantiate.
2. **Equality check first** (fail-fast): for each cached index, seed, call `dataset[i]`, compare to the pickled baseline output via the equality function. On mismatch, write `measure-N.json` with the failed shape and exit 0. (Default equality: recursive walker over dicts/lists/tuples; `torch.equal` for tensors; `np.array_equal` for arrays; `tobytes()` byte-equal for PIL Images. Override via `--equality-fn pkg.mod:fn`.)
3. If equality passes, repeat the line-profiler + DataLoader bench from `baseline`.
4. Compute `delta_vs_baseline` against the cached `baseline.json`.
5. Write `measure-N.json`.

### Failure modes the harness handles itself

- Factory raises → exit non-zero with a structured error JSON (skill surfaces to user; can't proceed).
- Dataset's `__getitem__` raises during measurement → equality-failed shape with `summary: "raised <ExcType>: <msg>"`.
- Output unpicklable → equality-failed shape with `summary: "output not picklable: ..."`.
- DataLoader bench fails (worker dies, introduced pickling error) → equality-failed shape, since "the change broke things" is the same outcome from the loop's perspective.

## Edge cases

**Dataset is non-deterministic under seeded RNGs.** `baseline` detects this via its own re-call equality check. The skill refuses to start the greedy loop, names the leaf that differs, and offers two paths: (1) supply `--equality-fn` that tolerates the non-determinism, (2) bail out. No silent fall-back to tolerance.

**`__getitem__` is too fast to profile reliably.** If baseline mean per-call wall time < ~1 ms, line_profiler overhead dominates rankings. `reliable_line_stats: false` in `baseline.json`; skill refuses to start the loop and tells the user the dataset is already fast.

**Edit makes `__getitem__` raise.** Treated as a failed equality check (exception captured in `summary`). Revert + counter increment.

**Edit is a no-op or correct refactor with no measurable speedup.** Falls under the < 1.05× rule → reverted. Prevents commits that don't pull their weight.

**Multiple lines tie for slowest.** Take the highest-line-number one. Arbitrary but deterministic.

**Auto-discovered subfunction is in a path the user didn't intend to be editable.** Can happen with `--profile-scope=package`. The skill checks each prospective edit's path against the dataset module's directory + sibling modules in the same top-level package; if the slowest line is outside that scope, the skill notes it and moves to the next-slowest line. The user can opt in to broader edit scope by re-invoking with explicit broadening.

**Caching across calls is a tempting trap.** An optimization that mutates dataset state across calls (e.g., memoizing `__getitem__` results) can pass the per-index equality check while corrupting batch-level behavior under DataLoader (workers fork the dataset; cross-worker cache state diverges silently). SKILL.md names this trap explicitly and forbids edits that introduce mutable cross-call state.

**Resumption after interruption.** If a session is interrupted (token limit, `/compact`, machine reboot) and the user re-invokes the skill: it detects an existing `.getitem-profile/` dir + `getitem-profile/...` branch, reads `session.md` to recover the failed-attempts set and accepted edits, and resumes the loop without re-baselining. Cached outputs and `baseline.json` remain authoritative.

**Cleanup.** `.getitem-profile/` is gitignored. The branch is left for the user — the skill never deletes it.

## Hard rules (encoded in SKILL.md)

- Edits only inside the dataset class / its module / its sibling modules in the same top-level package, scoped by `--profile-scope`. Never broaden silently.
- Never introduce mutable cross-call state (see "Caching trap" above).
- Never modify validation code or any code path outside `__getitem__`'s call graph.
- One edit per commit. No bundling — defeats per-line attribution.
- All edits on the side branch only. Never touch `main` or the user's prior branch.

## Caveat layer (surfaced to the user at start AND end of session)

> Per-call timings come from in-process measurement; under a real DataLoader, fixed costs (worker startup, IPC, fork-time imports) won't show up here. The DataLoader micro-benchmark gives a sanity check, but wins below ~50 µs per call may not translate. Wins should generally hold across distributed ranks since each rank's workers are independent.

## Files

### Plugin-shipped

```
plugins/ml-research/skills/getitem-profiler/
├── SKILL.md                  # ~150-200 lines; orchestration prompt
└── scripts/
    └── profile_getitem.py    # measurement harness
```

### User-provided

- A factory function `pkg.mod:make_dataset` returning a ready dataset instance. Documented one-liner template in SKILL.md.
- Optional `--equality-fn pkg.mod:fn` for exotic outputs (bounding boxes where order doesn't matter, etc.).

### Session-scoped (gitignored)

```
.getitem-profile/
├── baseline.json
├── baseline/
│   ├── 0.pkl
│   ├── 1.pkl
│   └── ...
├── measure-1.json
├── measure-2.json
├── ...
└── session.md
```

## Out of scope

- **Multi-rank / multi-node distributed profiling.** Mentioned in the caveat layer; not measured.
- **Memory profiling.** Wall time only.
- **Optimizing DataLoader-level parameters** (num_workers, pin_memory, prefetch_factor, persistent_workers). The skill measures one DataLoader configuration at user request; it doesn't sweep.
- **Optimizing collate functions or transforms not invoked from `__getitem__`.** Out-of-scope by construction — `__getitem__` is the entry point.
- **Per-edit user confirmation.** Autonomous on the side branch is the design choice; user reviews at the end.
