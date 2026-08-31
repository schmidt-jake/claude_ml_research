# ACCESS-governed clusters

Cross-cluster reference for clusters that draw allocations from the [NSF ACCESS](https://access-ci.org) program. Read alongside the generic SLURM guidance in this skill's `SKILL.md` and the cluster-specific reference for the cluster you're actually on.

ACCESS-governed clusters covered by this skill:

| Cluster | Reference file |
|---|---|
| NCSA Delta | `clusters/delta.md` |

Other ACCESS resources (Anvil, Bridges-2, Expanse, Stampede3, FASTER, Jetstream2, etc.) follow the same allocation model but their per-resource conversion factors aren't documented here — derive them from the cluster's `TRESBillingWeights` using the framework below.

## How ACCESS allocations map to SLURM billing

ACCESS issues allocations in **ACCESS Credits**, a unified currency. The ACCESS portal displays per-resource balances in resource-native units (e.g. "GPU Hours" on a GPU resource, "Core Hours" on a CPU resource). Internally each cluster enforces the allocation via SLURM's `GrpTRESMins=billing=...` quota, denominated in the cluster's *local billing-units* — not ACCESS-portal units. Two conversions matter:

1. **Portal unit → cluster billing-units.** Set by the cluster operator at allocation time. Inferable from `sacctmgr show qos <qos>`'s `GrpTRESMins=billing=N` divided by your portal-reported allocation in resource-native units.
2. **Cluster billing-units → wallclock cost for a specific job.** Set by `TRESBillingWeights` and `PriorityFlags` on the partition (see SKILL.md "TRES billing rates"). This is what determines whether you're billed by GPU, CPU, or memory for your particular request.

Both are needed to convert "I have N GPU Hours left in the portal" into "how long can I run this specific shape on this partition." Neither alone is sufficient.

```bash
# Local billing-units cap (cluster-side enforcement).
sacctmgr show qos <qos> format=Name,GrpTRESMins
# Per-resource portal balance: check the ACCESS portal at https://allocations.access-ci.org/
# Project's cluster-side usage:
sshare -A <account>
```

## When `Reason=QOSGrpBillingMinutes` fires

The scheduler computes `billing_rate × TimeLimit` for the pending job and refuses to start it if `(used + projected) > GrpTRESMins`. This can fire well before the project hits zero on the ACCESS portal — a long `--time` on a large request projects a large cost.

Levers, in order of leverage:
1. Shorten `--time` on the pending job — projected cost is linear in walltime.
2. Reduce the dominant TRES on the request (see SKILL.md). Reducing non-dominant TRES doesn't help under MAX_TRES.
3. Wait for other project jobs to finish (frees up `used`).
4. Request an allocation supplement via the ACCESS portal — multi-day turnaround, not a fix for an immediate deadline.

## Caveats

- The ACCESS portal balance is not always real-time; cluster-side enforcement uses the SLURM cap, which may be ahead or behind the portal by hours.
- Some clusters charge differently across partitions (e.g. interactive partitions are 2× standard). The portal usually reports a single per-resource balance, leaving the per-partition multiplier implicit.
- "GPU Hours" in the portal is a normalized unit, typically calibrated to one specific GPU type on the cluster (e.g. A100 on Delta). Newer/older GPUs charge at a multiple/fraction of that rate. The cluster-specific reference file lists the conversions.

## ACCESS documentation

- [ACCESS allocations](https://allocations.access-ci.org/)
- [ACCESS user portal](https://access-ci.org/)
