# Phase 0 — trust-layer extraction plan (literal file list)

Scope for carving the receipt/ledger/trust machinery into a standalone,
Titan-free repository. Trigger per the adopted decision rule: **start the
6-week clock only once three design-partner conversations exist.** Until then
this document is the scope, not a work order.

Verified 2026-07-02 against `b6cb84f3e1` (import audits run, not assumed).

## Extract — the product

| Component | Files | Seam notes |
|---|---|---|
| Ledger core | `src/agi_os_backend/governance/calibration_ledger_core.py` | stdlib-only. Clean. |
| Autonomy gate | `src/agi_os_backend/governance/calibration_autonomy_gate.py` | stdlib + ledger_core only (audited). Clean. |
| Same-PR pin classifier | `src/agi_os_backend/governance/calibration_same_pr_pin.py` | stdlib + git subprocess. Clean. |
| Scorer | `scripts/calibration_score_measured.py` | **The one real refactor**: imports `calibration_ingest_receipts`, assumes repo-root layout, hardcoded ledger/receipts paths. |
| Ingest (self-reported lane) | `scripts/calibration_ingest_receipts.py` | stdlib-only (audited); scorer dep — extract together. |
| Guards | `scripts/calibration_receipt_merged_check.sh`, `calibration_score_receipt.sh` | Path assumptions only. |
| Gate CLI | `scripts/calibration_ledger.py` | Thin wrapper. Clean. |
| F2P verifier | `scripts/calibration_f2p_verify.py` | Measurement-layer anti-gaming; pairs with pin exclusion. |
| Receipt spec | `docs/RECEIPT_SPEC.md`, `docs/improvements/0000-template.md` | The open standard. |
| Measurement (SPC) | `scripts/eval_matrix.py`, `spc_control_chart.py`, `defect_pareto.py`, `spc_record_run.py` | Self-contained; second product surface. |
| Doctrine | `docs/AB_TEST_AND_AUDIT_DOCTRINE.md`, `docs/runbook/16_full_autonomy_operator_lane.md`, `docs/incidents/` | The credential corpus. |

## Contracts — the product's spec (8, minimum set)

1. `test_calibration_rescore_order_contract.py` — rescore is position-preserving
2. `test_calibration_class_window_contract.py` — per-class windowing
3. `test_calibration_merged_score_guard_contract.py` — merged-only scoring
4. `test_automerge_class_window_env_contract.py` — report == decision window
5. `test_calibration_antigoodhart_contract.py` — pin exclusion integrity
6. `test_calibration_pin_exclusion_contract.py` — pins can't pad any window
7. `test_calibration_same_pr_test_pin_contract.py` — same-PR measures are pins
8. `test_calibration_f2p_verify_contract.py` — fail-to-pass verification

Port with their fixtures; they define the product's behavior better than any
design doc.

## Explicitly NOT extracted

Brain readiness, GitNexus wrappers, `autonomous_merge.py` PR plumbing, the
council/soul/dreaming stack, chat, retrieval, Forge. The product ships gate
math and scoring; customers bring their own CI and merge policy. Titan remains
the running reference deployment (R&D dummy) consuming the extracted package
like any other customer would.

## Known work items (the honest six weeks)

1. Break `calibration_score_measured` ↔ repo-root coupling: ledger path,
   receipts glob, and repo root become explicit parameters / config.
2. Package layout: one Python package (`receipts/` or similar), CLI entry
   points replacing the `scripts/` invocation style.
3. Multi-repo semantics: `origin/main` as "merged ref" becomes configurable per
   deployment (the guard already env-overrides via `CALIBRATION_MERGED_REF`).
4. CI adapter: a GitHub Action wrapping score + gate output as a check run —
   the free tier and the distribution vehicle.
5. Resolve the over-pinning discriminator (spec §6.2 open question) before the
   classifier ships to anyone else's ledger.
6. Port the 8 contracts + a fresh e2e: receipt → merge → score → gate flip, in
   a scratch git repo, as the package's own acceptance test.
