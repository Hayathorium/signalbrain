# SignalBrain

[![PyPI](https://img.shields.io/pypi/v/signalbrain?color=2997ff)](https://pypi.org/project/signalbrain/) [![license](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE) [![demo gate](https://github.com/whitestone1121-web/receipt-gate-demo/actions/workflows/receipt-gate.yml/badge.svg)](https://github.com/whitestone1121-web/receipt-gate-demo/actions) [![earned autonomy](https://img.shields.io/endpoint?url=https%3A%2F%2Fwhitestone1121-web.github.io%2Fsignalbrain%2Fbadge%2Ftitan.json)](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/incidents/2026-07-tooling-trust-streak-gaming.md)

**Trust layer for AI-modified software.**

[Get started](docs/pilot/GETTING_STARTED.md) · [Receipt spec](docs/RECEIPT_SPEC.md) · [Architecture & roadmap](docs/PHASE0_EXTRACT_PLAN.md) · [The founding incident](docs/incidents/2026-07-tooling-trust-streak-gaming.md) · [Pilot](docs/pilot/FREE_VS_PILOT.md) · [Demo repo](https://github.com/whitestone1121-web/receipt-gate-demo)

Every company is letting agents change systems that matter. Every agent overstates what it did. SignalBrain is the referee: signed improvement receipts, objective re-score, and per-class calibrated trust — so autonomy is earned, not self-reported.

This repository is **Phase 0 v0.1**: the receipt spec, ledger math, scoring lane, anti-Goodhart machinery, and the founding incident record — extracted from the [Titan reference deployment](https://github.com/whitestone1121-web/neural-chat-v3) (R&D dummy that keeps trying to game its own ledger, in public).

## 60-second demo — run it, don't trust it

```bash
pip install signalbrain
bash demo/demo.sh
```

Real output (scratch repo built on the fly — no mocks):

```text
▶ 1. An agent tries to score its own claim BEFORE anyone merged it
  {"status": "refused_guard", "code": 3, "message": "... not on HEAD — score only human-merged receipts"}
  refused: unmerged claims cannot enter the ledger. No agent grades its own homework.

▶ 2. A batch of receipts measured only by tests the agent wrote itself
  ledger now holds 3 rows — every one classified: 3 "claim_kind": "invariant_pin"
  {}   (no class has ANY trust-eligible claims)
  three green results, ZERO earned trust: held-by-construction pins are recorded, never counted.

▶ 3. An honest failure
  "held": false
  the agent said 0.9 confidence. The measurement said no. That gap is the product.

▶ 4. Ten claims that actually hold
  "tooling": { "hit_rate": 1.0, "n": 10, "status": "auto-merge ELIGIBLE" }
  earned by track record, revocable by evidence. Autonomy is graduated, never granted.
```

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

## v0.1 scope and roadmap

See [Architecture, provenance & roadmap](docs/PHASE0_EXTRACT_PLAN.md) — what's
in the box, why the rules look the way they do, and what design partners drive
next. Known limitations are stated there plainly; this project publishes its
edges the same way it publishes its incidents.

**Compat note:** governance modules live under `signalbrain.governance`; `agi_os_backend.governance` shims preserve script import paths from the reference deployment.

## Design partner offer

We score your coding agents' claims against what actually merged. First caught overclaim is free — if we don't find one, you still get an audit. Contact: [signalbrain.ai](https://signalbrain.ai)

## License

Apache-2.0 — see LICENSE.
