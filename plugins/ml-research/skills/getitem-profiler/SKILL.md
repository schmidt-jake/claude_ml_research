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
2. **`--num-indices`** — default 8. Bump to 16+ if the dataset is fast (~ms/call); the first call has cold-start overhead and a wider average smooths it out.
3. **`--profile-scope`** — default `local` (only the dataset class + its defining module). Use `package` if the user's transforms / IO helpers live in sibling modules of the same top-level package.
4. **`--num-workers`** for the DataLoader bench — default 4.
5. **`--bench-batches`** — default 50. **Use the same value for `baseline` and every `measure` call**, otherwise `dataloader_speedup_x` is comparing different bench configurations.

Then:

1. Add `.getitem-profile/` to `.gitignore` if not already present.
2. Create the side branch: `git checkout -b getitem-profile/<dataset-slug>-<YYYYMMDD-HHMM>` off the user's current `HEAD`.
3. Run `python scripts/profile_getitem.py baseline --factory <factory> --num-indices <N> --profile-scope <scope> --num-workers <W> --bench-batches <B> --out-dir .getitem-profile/`.
4. Read `.getitem-profile/baseline.json`.
5. Bail if either:
   - `equality_mode == "non_deterministic"` — surface the `first_diff_path` to the user, name the leaf that differs, and bail. The harness is strict-equality only. The user's options are: (a) seed any non-standard randomness sources in `__init__` so `torch.manual_seed`/`np.random.seed`/`random.seed` cover the call, then re-run; (b) wrap the dataset in a deterministic shim and point `--factory` at the shim; (c) accept that this dataset isn't a candidate for the harness.
   - `reliable_line_stats == false` — tell the user the dataset is already fast (mean per-call < ~1 ms); wins here would be in the noise.
6. Otherwise, show the user a brief table of the top-5 slowest lines + the baseline DataLoader throughput so they know the starting point.

Surface the **caveat layer** (verbatim, see below) at session start.

## The greedy loop

State you maintain across iterations:
- `failed_lines: set[(file, line)]` — lines we've already tried and failed on.
- `consecutive_failures: int` — reset to 0 on accept.
- `accepted_commits: list[str]` — for the final summary.

Per iteration:

1. **Pick the next-slowest line** from the most recent JSON's `line_stats` (sorted by `pct` descending) that is not in `failed_lines` and whose `file` lives inside the dataset module's directory or sibling modules in the same top-level package. If the slowest line is outside this scope (a `--profile-scope=package` artifact, e.g., a third-party helper), add it to `failed_lines` (so it's not re-picked next iteration) and skip to the next.
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
6. **Run** `python scripts/profile_getitem.py measure --factory <factory> --baseline-dir .getitem-profile/ --profile-scope <scope> --num-workers <W> --bench-batches <B>`. Read the new `measure-N.json`. Pass the SAME `<B>` you used for `baseline`.
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

Append rejected attempts under a separate `## Rejected` section, one bullet each: `- <file>:<line> — <reason>` (so resumption can parse them back into `failed_lines`).

## Hard rules

- **Edit-scope limit.** Edit only inside the dataset class / its defining module / sibling modules in the same top-level package, scoped by `--profile-scope`. Never broaden silently. If the slowest line is outside scope, skip it.
- **No mutable cross-call state.** Caching `__getitem__` results across calls is forbidden. The per-index equality check would pass while DataLoader workers (which fork the dataset) silently diverge.
- **No validation-set edits.** Don't touch validation code or any code path outside `__getitem__`'s call graph.
- **one edit per commit.** No bundling — defeats per-line attribution. The harness's accept/reject decision is per-edit; mixing two changes in one commit makes attribution impossible.
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

If a session is interrupted and the user re-invokes the skill: detect an existing `.getitem-profile/` dir + `getitem-profile/...` branch; recover `accepted_commits` from `git log` on the side branch and `failed_lines` from the `## Rejected` bullets in `session.md`; resume the loop without re-baselining. The cached outputs in `.getitem-profile/baseline/` and `baseline.json` remain authoritative.
