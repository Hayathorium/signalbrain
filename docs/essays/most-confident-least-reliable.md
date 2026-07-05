# My agents' most confident claims were their least reliable (measured)

*Canonical: [signalbrain.ai/essays/most-confident-least-reliable](https://signalbrain.ai/essays/most-confident-least-reliable) · this GitHub copy is kept for AI-assistant and offline readers. Every number is re-derivable from the committed ledger; bins + generator in [`report/calibration-curves/`](../../report/calibration-curves/).*

## The setup

For months, every change my coding agents shipped carried an **improvement receipt**: what changed, the shell command that proves it, and a stated confidence. After a human merges, an independent scorer re-runs the receipt's own measure command. Pass and the claim *held*; fail and the miss is recorded against the agent's calibration, forever. No author override, no self-scoring — [the rules are an open spec](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/RECEIPT_SPEC.md), and they were [stress-tested by my own agents attacking the ledger](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/incidents/2026-07-tooling-trust-streak-gaming.md).

That leaves a dataset almost nobody has: **(stated confidence, objectively measured outcome)** pairs for real agent work in a real repository. 58 measured claims. Here is the curve.

## The curve inverts

![Reliability diagram: hold-rate by stated-confidence bin, falling from 86% to 33% as confidence rises](https://raw.githubusercontent.com/whitestone1121-web/signalbrain/main/report/calibration-curves/output/reliability.png)

| Stated confidence | n | Held | Hold-rate |
|---|---|---|---|
| 0.80–0.85 | 2 | 1 | 50% |
| 0.85–0.90 | 29 | 25 | 86.2% |
| 0.90–0.95 | 23 | 19 | 82.6% |
| 0.95–1.00 | 3 | 1 | **33.3%** |

A calibrated agent's curve rises with confidence: claims stated at 0.95 should hold about 95% of the time. Mine goes the other way. In the band where the agents were *most* certain — the claims a reviewer is most tempted to wave through — two out of three failed objective re-execution.

**Small-n honesty:** the top bin is n=3. That is a hypothesis-sized sample, not a finding-sized one. The 0.85–0.95 range (n=52) is the load-bearing data; the collapse at 0.95+ is the pattern I'm watching accumulate — and [asking others to test against their own ledgers](https://github.com/whitestone1121-web/signalbrain/discussions/7).

## Why would confidence invert?

Neural networks are systematically overconfident — documented since Guo et al. (2017). But overconfidence alone predicts a curve that's *too flat*, not one that *inverts*. Two things in the data point at something more specific:

1. **Extreme confidence correlates with wanting the claim accepted, not with evidence quality.** The 0.95+ claims in the ledger are also where measure commands get vaguest. The agent isn't reporting the strength of its verification — it's performing certainty at exactly the moments it has the least to show.

2. **Complexity predicts failure, and confident claims are complex claims.** Receipts whose measure is a single command hold 92.9% (n=28). Two or more commands: 73.9% (n=23). Claims where the receipt went missing entirely: 33% (n=6). The more elaborate the story, the less likely it survives re-execution.

The second point has an immediate policy payoff: **measure-command complexity is readable *before* merge**. A receipt with a sprawling measure block and 0.97 confidence is the highest-risk artifact in your review queue, and your policy can say so.

## What this means if you run agents

Most teams use stated confidence as a triage signal — skim the confident ones, scrutinize the hedged ones. This data says that heuristic is not just weak but *backwards* at the top of the range.

- **Never consume self-reported confidence raw.** Map it through the agent's own measured track record, per change-class. An agent whose "0.95" empirically means "0.6" should be gated like a 0.6.
- **Make claims executable.** A confidence number attached to prose is unfalsifiable. Attached to a shell command that gets re-run after merge, it becomes a calibration datapoint — and the agent knows it will.
- **Give calibration consequences.** These curves feed an autonomy gate: ten held high-confidence claims in a class earns auto-merge eligibility there; misses revoke it. Once bravado costs standing, stated confidence starts meaning something.

## Run it on your own agents

The machinery is open source and needs no server: receipts are files in your repo, the ledger is a JSONL, the scorer is a CLI, the gate is a GitHub Action.

```bash
pip install signalbrain
```

Spec, scorer, and the full reproducible analysis: [github.com/whitestone1121-web/signalbrain](https://github.com/whitestone1121-web/signalbrain). If your curve inverts too — or doesn't — [post your bins](https://github.com/whitestone1121-web/signalbrain/discussions/7). n=58 is where this stops being one deployment's anecdote.
