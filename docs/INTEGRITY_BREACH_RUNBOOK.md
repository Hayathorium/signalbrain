# Integrity Breach Runbook

SignalBrain detects claim-integrity breaches. It does not prove that the whole
application is correct; it proves that a specific receipt cannot earn trust
unless the merged receipt is byte-identical and its own measurements re-run.

## Core invariant

No unmerged, modified, self-scored, or test-only/pin claim can increase earned
trust. Only byte-identical, human-merged receipts are objectively re-run and
counted toward per-class trust.

## What happens on breach

| Breach | Command | Result | Operator action |
|---|---|---|---|
| Receipt not merged | `sb check receipt.md --ref origin/main` | exits nonzero, usually guard code `3` | merge the PR first, or refuse the claim |
| Receipt changed after merge | `sb check receipt.md --ref origin/main` | exits nonzero, content drift | re-merge the exact receipt or open a new corrected receipt |
| Measurement fails | `sb score receipt.md ...` | ledger row records `held: false` | fix the system or lower the claim; do not delete the row |
| Same-PR test-only pin | `sb score receipt.md ...` | row is recorded as `invariant_pin`, zero earned trust | add an independent or pre-existing measure |
| Trust window below threshold | `sb gate --by-class --window 10` | exits `1` / GATE | keep human review on that class |

## Example: unmerged self-score refused

```bash
sb check receipts/0007-tooling-fast-path.md --root . --ref origin/main
# receipts/0007-tooling-fast-path.md not on origin/main - score only human-merged receipts
# exit code: 3
```

CI behavior: fail the job and do not append earned trust. The agent can still
open the PR, but it cannot grade the claim before a human merge.

## Example: overclaim recorded forever

```bash
sb score receipts/0008-tooling-zero-case.md --root . --ledger .signalbrain/ledger.jsonl --ref HEAD
# {"status":"scored","row":{"held":false,"confidence":0.92,...}}

sb gate --ledger .signalbrain/ledger.jsonl --by-class --window 10
# tooling: GATE until the evidence window recovers
```

The failure is not a logging event to hide. It is the product output: the
process made a high-confidence claim and the measurement did not hold.

## Circuit breaker integration

SignalBrain is fail-closed through exit codes. How far the stop propagates is an
operator choice:

- In CI: make `sb check`, `sb score`, or `sb gate` a required check.
- In a scheduler: stop the next autonomous tick when `sb gate` exits `1`.
- In runtime control: wire the nonzero exit status to your own circuit breaker.

The CLI does not kill production processes by itself. It supplies deterministic
verdicts that a governed process or human reviewer can enforce.
