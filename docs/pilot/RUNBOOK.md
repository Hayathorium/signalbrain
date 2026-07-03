# Design-partner pilot — runbook

The offer: we score your coding agents' claims against what actually merged, in
your CI, on your infrastructure. **First caught overclaim is free. If we catch
nothing, you don't pay — and you've audited your agents either way.**

Everything below happens inside the partner's walls. No code, receipts, or
ledger data leaves their infrastructure at any point.

## Day 0 — the 15-minute call

Agenda: which repos, which agents, what "caught" means to them. Exit criteria:
one target repo chosen (prefer the busiest agent-PR repo), one contact who can
merge CI changes, and a start date.

## Day 1 — wiring (one PR from us, reviewed by them)

1. Receipt-emission block ([receipt-emission.md](receipt-emission.md)) added to
   the repo's agent instructions (`CLAUDE.md` / `.cursorrules` / system prompt).
2. The receipt-gate workflow added (see the
   [reference workflow](https://github.com/whitestone1121-web/receipt-gate-demo/blob/main/.github/workflows/receipt-gate.yml));
   ledger at `.signalbrain/ledger.jsonl`, scoring on merge to their default branch.
3. Baseline run on any receipts that already exist (usually none — that's fine).

**Known first-repo friction, stated up front:** the measure grammar supports
pytest/python/bash; other stacks (jest, go test, cargo) work via `bash` wrappers
until native leaders land. Monorepos: one ledger per repo root in v0.1.

## Days 2–10 — accumulation (no touch)

Agents work normally; every merged agent PR with a receipt gets scored
automatically. We check in only if the workflow itself breaks.

## Day 10 — the ledger report

Delivered as a document in their repo (reproducible, like everything else):

- claims scored, held-rate overall and by confidence band
- **the calibration gap**: stated confidence vs measured hold-rate
- any caught overclaim, written up receipt-style (what was claimed, what
  re-running showed, the commands to reproduce)
- pins detected (agents self-scoring with their own tests) — an adoption
  finding, not a fault
- per-class trust standings and what the agents would need to earn autonomy

## The decision point

- **Overclaim caught** → the write-up is theirs free; the paid engagement is
  continuing the gate + monthly ledger reports + earned-autonomy policy design.
- **Nothing caught** (real possibility) → they get the audit and the calibration
  report free, we get the case study data point, no invoice.

## Operator notes (our side)

- Their agents will produce receipts that stress the grammar — capture every
  parse failure as a package issue; the first three pilots ARE the hardening.
- Never accept `CALIBRATION_ALLOW_UNMERGED`-style shortcuts to make numbers
  appear faster. The pilot sells the discipline; the discipline is the product.
- Every claim in the day-10 report must re-derive from their git history with a
  command included in the report. If they can't reproduce it, we don't ship it.
