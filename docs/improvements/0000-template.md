# 0000-template

> Copy this file to `docs/improvements/NNNN-<short-name>.md` where NNNN is the next sequential 4-digit number. Fill in every section. Keep it tight — the audit is a receipt, not a design doc.

## Compared
- branch:    `feat/example@<branch-sha>`
- baseline:  `origin/main@<main-sha>`
- date:      `YYYY-MM-DD`

## Change summary

<One paragraph in plain language. What the PR does, who it's for, why now. Avoid jargon — the audit should be readable by a reviewer who hasn't seen the PR yet.>

## Metric delta

<At least one row. Use the metrics the change actually affects. Honest "not measured: <reason>" is better than fabricated numbers.>

| Metric | Baseline (main) | Branch | Delta |
|---|---|---|---|
| Contract test count | NNN | NNN | +N / -N / 0 |
| Contract pass rate | NNN/NNN | NNN/NNN | +N / -N / 0 |
| `verify_fast.sh` runtime | X s | Y s | ±Z s |
| Latency p50 / p95 / p99 | a / b / c ms | a' / b' / c' ms | ... |
| Error rate (under load) | M / N | M' / N' | ... |
| LOC added / removed | — | +X / -Y | — |
| Memory (peak RSS) | A MB | B MB | ±C MB |
| <other metric specific to this change> | ... | ... | ... |

### How measured

<One paragraph: command(s) run, input set, environment. If you couldn't measure, say "not measured: <reason>" — e.g., "not measured: requires GPU lane, change is doc-only.">

## Verdict

`improvement` | `parity` | `regression` | `not_applicable`

## Reasoning

<Why this verdict. If `regression`, this section is mandatory and must say why we're shipping it (tradeoff against another metric, blocker on something larger, etc.). If `not_applicable`, name which exempt category from the doctrine applies.>

## Risks / follow-ups

<Anything the operator should watch for after merge. Empty if none.>
