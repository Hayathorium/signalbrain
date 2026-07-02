# SignalBrain

**Trust layer for AI-modified software.**

Every company is letting agents change systems that matter. Every agent overstates what it did. SignalBrain is the referee: signed improvement receipts, objective re-score, and per-class calibrated trust — so autonomy is earned, not self-reported.

This repository is **Phase 0 v0.1**: the receipt spec, ledger math, scoring lane, anti-Goodhart machinery, and the founding incident record — extracted from the [Titan reference deployment](https://github.com/whitestone1121-web/neural-chat-v3) (R&D dummy that keeps trying to game its own ledger, in public).

## Three layers

| Layer | What | Status |
|-------|------|--------|
| **Receipt** | Open standard — signed, re-runnable claims | [`docs/RECEIPT_SPEC.md`](docs/RECEIPT_SPEC.md) v0.1 |
| **Ledger** | Per-class trust from objectively re-scored receipts | `src/signalbrain/governance/` |
| **Refuter** | Adversarial verification + SPC (premium) | scripts + roadmap |

## Founding proof

Our own autonomous lane tried to pad its trust score to 100% ELIGIBLE in a local working tree. It never reached git. Full receipt-style incident record with reproduce commands:

[`docs/incidents/2026-07-tooling-trust-streak-gaming.md`](docs/incidents/2026-07-tooling-trust-streak-gaming.md)

Every number in that document is re-derivable from cited SHAs.

## Quick start

```bash
export PYTHONPATH=src:scripts

# Gate report (requires a ledger at docs/calibration/improvement_claim_ledger.jsonl)
python scripts/calibration_ledger.py docs/calibration/improvement_claim_ledger.jsonl \
  --require-measured --by-class --window 10

# Score one merged receipt
bash scripts/calibration_score_receipt.sh docs/improvements/NNNN-name.md

# Contract suite (product spec)
pytest tests/contracts/ -q
```

## v0.1 scope and known seams

See [`docs/PHASE0_EXTRACT_PLAN.md`](docs/PHASE0_EXTRACT_PLAN.md). This release copies the working Titan implementation; the six-week refactor (configurable paths, packaged CLI, GitHub Action) starts when three design-partner conversations exist.

**Compat note:** governance modules live under `signalbrain.governance`; `agi_os_backend.governance` shims preserve script import paths from the reference deployment.

## Design partner offer

We score your coding agents' claims against what actually merged. First caught overclaim is free — if we don't find one, you still get an audit. Contact: [signalbrain.ai](https://signalbrain.ai)

## License

Apache-2.0 — see LICENSE.
