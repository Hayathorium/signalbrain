# A/B test and audit doctrine

Status: **doctrine, gate dormant**
First landed: 2026-06-04

## The rule

Every PR that changes runtime-observable code MUST include an A/B audit entry under `docs/improvements/NNNN-<short-name>.md` capturing:

1. **The branch HEAD SHA** being proposed.
2. **The `origin/main` HEAD SHA** it was measured against.
3. **The metric delta** — at minimum one quantitative comparison (contract count, latency, error rate, throughput, memory, line count, whichever the change actually affects).
4. **The verdict** — one of: `improvement`, `parity`, `regression`, `not_applicable`. Regression requires explicit justification (why we're shipping it anyway — usually because it's a tradeoff against a different metric).

The audit entry is the answer to "what changed and what's the evidence." Reviewers use it to sanity-check that the PR did what its title claims and didn't quietly regress something orthogonal.

## What counts as "runtime-observable"

Triggers the audit requirement:

- **`.py` outside `tests/`** — anything in `src/`, scripts that ship as part of the runtime, root-level entrypoints. Test-only files are exempt because the test suite IS the measurement.
- **`.mjs` server / worker code** — `titan-dashboard/server/*.mjs`, runner code, anything that executes in the Forge marketplace path.
- **`.github/workflows/*.yml`** — workflow changes alter CI/CD behavior; treat as runtime.
- **`docker-compose*.yml`** — runtime topology.
- **`Dockerfile*`** — runtime images.
- **Contract additions or deletions** — moves the gate surface.

Exempt (no audit needed):

- **Docs-only**: `.md`, `.rst`, `.txt` changes anywhere.
- **Test-only**: anything under `tests/` (including new contract tests that don't ship with paired runtime changes — the contract IS the measurement).
- **One-line bug fixes** where the bug + the fix are both obvious — the commit message should call this out explicitly ("trivial fix, no audit").
- **Formatter / lint sweeps** — `black`, `ruff --fix`, `isort`, etc. The audit is "shape only, no behavior."
- **Config-only tweaks** that don't alter runtime behavior (e.g., updating a CI-only constant).

When in doubt, write the audit. The 5-minute cost of writing one is much smaller than the cost of merging a regression nobody measured.

## The audit format

See `docs/improvements/0000-template.md` for the canonical template. Minimal required structure:

```markdown
# NNNN-<short-name>

## Compared
- branch:    <branch>@<sha>
- baseline:  origin/main@<sha>
- date:      YYYY-MM-DD

## Change summary
<one paragraph — what the PR does, in plain language>

## Metric delta
<at least one row. Use what the change actually affects.>
- contract pass: NNN/NNN → NNN/NNN  (or "unchanged")
- latency p95:   X ms → Y ms        (or "not measured: no perf impact")
- error rate:    M/N → M'/N'         (or "not measured: not on hot path")
- LOC delta:     +X / -Y
- ...

## Verdict
<one of: improvement | parity | regression | not_applicable>

## Reasoning
<why this is the verdict. If regression, why we're shipping it anyway.>
```

Keep entries short. The audit is a receipt, not a design doc.

## Enforcement (phased)

### Phase 1 — dormant gate (now)

- Doctrine doc + template exist.
- `tests/contracts/test_ab_audit_doctrine_contract.py` asserts the doctrine + template are present and the rule is named in `CLAUDE.md` + `AGENTS.md`.
- Reviewer enforces presence of an audit entry per-PR. The PR template asks for the path to the audit entry.
- No hard CI fail on missing audit (yet). The point of Phase 1 is to bootstrap the practice without immediately blocking work.

### Phase 2 — hard gate (after ~10 real audit entries exist)

> **Status: ACTIVE since 2026-06-04** — flipped with 12 real entries in `docs/improvements/` (entry 0014). The flag is set in `.github/workflows/ci.yml` (contract job) and the doctrine contract is in `scripts/smoke_contract_manifest.txt`, so the strict assertion runs in the PR lane against the PR diff.

- Flip `AB_AUDIT_RECEIPT_REQUIRED=1` in CI.
- The strict assertion in the contract test fail-closes when a PR touches runtime-observable code without adding a `docs/improvements/*.md` entry in the same PR diff.
- Exemptions can be claimed by adding `## Verdict\nnot_applicable` with reasoning — the gate still requires an entry, but `not_applicable` is a valid verdict for the cases listed in the "Exempt" section above.
- PRs that touch runtime `.py` should prefer `parity` or `improvement` with a contract-table metric delta when behavior changed, even if default-off — reserve `not_applicable` for exempt categories (docs-only, CI-only, operator-gated surfaces with no measurable delta in the merge lane). If you use `not_applicable` on a runtime PR, state which exempt category applies and what follow-up receipt will carry the live proof.

This mirrors the pattern from `RETIRED_ROTATION_EVIDENCE_REQUIRED` (PR #237) — ship the doctrine + dormant gate first, flip to hard-enforce once there's enough real-world data to know the false-positive shape.

## Worked example — what an audit entry actually looks like

See `docs/improvements/0001-ab-audit-doctrine.md` — the audit entry for this PR itself, which is `not_applicable` because the PR is docs-only. The entry exists to show the format in practice and to seed the directory.

## Common pitfalls

- **Don't measure what doesn't matter.** A docs change doesn't need latency p95. The verdict + one honest metric beats five fabricated numbers.
- **Don't claim `improvement` without measuring.** If the PR's intuition is "this should be faster" but there's no number, say `not_measured` and justify it instead of guessing.
- **Regressions are allowed.** Sometimes you ship a known regression because it unlocks something more valuable. Honesty in the audit is the contract; the verdict + reasoning are the audit trail for "we knew."
- **The SHA you compare against matters.** Use the *current* `origin/main` HEAD at the time you open the PR, not a stale local main. If main moves while your PR is open and the delta could change meaningfully, update the audit.

## Confidence & calibration

**Additive and OPTIONAL — existing receipts need no changes.** A receipt MAY include a
single `## Confidence` line holding a number in `[0, 1]`: the author's probability that
the change is a *real* improvement (not just that the tests pass). This is deliberately
distinct from the four-way `## Verdict`: the verdict is a categorical claim, the
confidence is a calibrated probability that the verdict will hold up downstream.

Confirmed outcomes feed `docs/calibration/improvement_claim_ledger.jsonl` — a JSONL ledger
of `{claim, confidence, held, caught_by, session}` rows scored by
`scripts/calibration_ledger.py` (held-rate, Brier score, count of high-confidence claims
that nonetheless failed = overconfidence, and an autonomy verdict). The autonomy ladder is
gated on the **calibrated hit-rate** of high-confidence claims (TRUST only when
high-confidence claims hold `>=95%`), **not** on the raw `## Verdict`. The motivation:
over the 2026-06 session several high-confidence "this is fixed/proven" claims shipped
wrong and were caught only downstream (live runs, py-spy, Codex measurement); making
claimed-confidence-vs-outcome a number is what keeps that overconfidence visible.

This is the **seed** of "calibration as a tracked metric," not the finished system.
Planned follow-ups (not implemented yet): (a) auto-append a `## Confidence` field to the
ledger on merge, (b) auto-score `held` from the post-merge measured delta, (c) gate the
autonomy ladder per-domain on the hit-rate. It relates to the conformal calibration in
`governance_benchmark.py` (governor confidence) — this extends the same idea to the
improvement loop. **Flagged for Codex review:** the A/B doctrine is shared; this section
is additive only.

## Related

- `docs/improvements/0000-template.md` — canonical template.
- `scripts/calibration_ledger.py` + `docs/calibration/improvement_claim_ledger.jsonl` — calibration scoring for improvement claims (seed of move #2).
- `tests/contracts/test_ab_audit_doctrine_contract.py` — contract gate.
- `CLAUDE.md` Operating goal #7 — the rule statement.
- `AGENTS.md` Always Do — the rule statement.
- `RETIRED_ROTATION_EVIDENCE_REQUIRED` pattern (`tests/contracts/test_retired_credentials_rotation_evidence_contract.py`, PR #237) — the dormant-then-flip enforcement pattern this doctrine reuses.
