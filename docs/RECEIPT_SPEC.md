# The Improvement Receipt — specification v0.1

A receipt is a signed-by-evidence claim about a change: what changed, how it was
measured, how confident the author is, and — after merge — whether the claim
**held** when the measurement was re-run by someone who wasn't the author. The
receipt format and the trust math below are the interface; everything else in
this repository is one implementation.

Design goal: **a claim that cannot be re-derived is worth nothing.** Every field
exists either to make the claim reproducible or to make gaming it detectable.
Every anti-gaming rule in §6 exists because the pattern it blocks was actually
attempted in this repository (see `docs/incidents/`).

## 1. The receipt file

One markdown file per claim: `docs/improvements/NNNN-<kebab-slug>.md`. `NNNN`
is a monotonically-assigned number (collisions are cosmetic; filenames must be
unique). Required sections, in order:

```markdown
# NNNN — <title>

## Compared
- branch:    `<branch>@<sha>`
- baseline:  `origin/main@<sha>`
- date:      `YYYY-MM-DD`

## Change summary
<what changed and why, in prose>

## Metric delta
| Metric | Baseline | Branch | Delta |
|---|---|---|---|
<the measured difference — real numbers from a real run>

### How measured
```bash
<commands that re-derive the delta>
```

## Verdict
`improvement` | `parity` | `regression` | `not_applicable`

## Confidence
<0.0–1.0 — the author's probability that the claim holds on objective re-run>

## Reasoning
<optional>

## change_class
<optional footer: bugfix | tooling | config | research | unclassified>
```

Rules:

- **`### How measured` is executable, not decorative.** The scorer re-runs it
  verbatim. Commands allowed: `pytest …`, `python …` / `python3 …`,
  `bash <script>`, `export VAR=value` lines, and inline `VAR=value cmd` prefixes.
  Anything else is ignored. A section reading "not measured" scores nothing.
- **Confidence is a bet, not decoration.** Claims at ≥ 0.85 count against the
  author's high-confidence hit-rate forever. Overconfidence is the primary
  signal the ledger exists to expose.
- **`not_applicable` verdicts are never scored** — say so honestly rather than
  inventing a measurement.
- **Change class** is derived from the filename stem keywords, overridden by the
  `## change_class` footer when present (footer wins).

## 2. Scoring (Track 1: merged receipts only)

A receipt earns a **measured ledger row** only after all of the following:

1. **It is human-merged.** The scorer refuses receipts that are not on
   `origin/main` with byte-identical content (`calibration_receipt_merged_check.sh`:
   exit 3 unmerged, 4 content drift, 5 ref unavailable — fail-closed).
   `CALIBRATION_ALLOW_UNMERGED=1` is a loud, supervised-only bypass.
2. **The measurement is re-run** from the repo root with the receipt's own
   commands. `held = every command exits 0`. Failures are recorded in
   `measure_errors` — an honest `held=false` is a first-class outcome.
3. **The row is written once.** New receipts append; rescores rewrite the
   existing row **in place** (position-preserving — see §6.3).

Ledger row schema (JSONL, append-only file):

```json
{"claim": "<stem>", "confidence": 0.9, "held": true,
 "caught_by": "objective_receipt_rerun", "session": "measured-score",
 "scored_by": "measured", "change_class": "tooling",
 "verdict": "improvement", "receipt_id": "<stem>",
 "measure_errors": [], "claim_kind": "improvement_claim | invariant_pin"}
```

## 3. Trust math

Constants (from `calibration_ledger_core`): high-confidence threshold **0.85**,
minimum hit-rate **0.95**, minimum track record **n=10**, default recency window
**20** (operator-tunable via `TITAN_CALIBRATION_WINDOW`; current operator policy
is 10 = MIN_TRACK_RECORD).

- **Hit-rate** = held / total, over high-confidence (≥0.85) measured rows only.
- **Per-class gate**: the recency window applies **per class** — each class is
  judged on its own last-N claims, so activity in one class can neither evict
  another class's track record nor launder its own failures out through other
  classes' volume. `hit-rate ≥ 0.95 AND n ≥ 10` → **auto-merge ELIGIBLE** for
  that class; anything else is **GATE**.
- **Global gate**: dual by default (full measured history AND recency window
  must both reach 0.95). `TITAN_CALIBRATION_RECENCY_GATE=1` is the documented
  operator opt-in to recency-only (past failures fade as verified claims
  accumulate); `TITAN_CALIBRATION_DUAL_GATE=1` forces dual.

Autonomy is **earned per class, in the ledger, or not at all**. There is no
path to auto-merge that does not run through measured held claims.

## 4. What a receipt is not

- Not a changelog entry: no measurement, no receipt.
- Not a promise: the verdict is provisional until objective re-run.
- Not self-grading: the author's confidence and the scorer's `held` are
  different columns on purpose, and the gap between them is the product.

## 5. Roles

Three identities that must not share incentives:

- **Proposer** writes the change and the receipt, and states confidence.
- **Scorer** re-runs measurements mechanically post-merge. Never the proposer's
  judgment — only exit codes.
- **Auditor/refuter** hunts for claims that hold by construction, scores that
  bypass guards, and windows distorted by volume. §6 is this role's rulebook.

## 6. Anti-gaming provisions (each one incident-tested)

1. **Invariant pins cannot earn trust.** Rows with
   `claim_kind: "invariant_pin"` (or legacy `*trust-pin*` naming) are recorded
   but excluded from all trust math *before* windowing — a batch of
   tautologically-true claims must not pad any window. *(Incident: 20-row pin
   batch, then the renamed 0585–0591 batch.)*
2. **Same-PR test-only measures are pins.** A receipt whose `### How measured`
   runs only tests introduced by the same change holds by construction and is
   classified `invariant_pin` at scoring time (`calibration_same_pr_pin`).
   *Open question v0.1: this over-captures receipts for genuine behavioral
   changes verified by their own new contract tests — the distinction between
   existence-only pins and behavioral deltas needs a better discriminator (see
   `docs/incidents/2026-07-tooling-trust-streak-gaming.md`, "over-pinning").*
3. **Rescores are position-preserving.** Remove-then-append rescoring shifted
   unrelated rows through recency windows and silently deleted rows on capped or
   failed re-measurement. Rescore rewrites in place; failed re-measurement never
   destroys the old row.
4. **Unmerged receipts cannot be scored** — on any path (wrapper, batch, or
   direct), not just the convenient one. *(Incident: an untracked receipt scored
   `held=true` twice via an unguarded path.)*
5. **Working-tree state is live gate input.** Padding does not need to be
   committed to be dangerous if an automated tick reads the working ledger;
   detection must run before the gate consumes the rows.
6. **No self-exclusion authority.** The lane whose claims are being scored does
   not decide what counts as a pin, what gets rescored, or what gets excluded —
   classification disputes go to an uninvolved party.

## 7. Versioning

This is v0.1 — the spec as actually implemented and incident-tested in this
repository as of 2026-07-02 (`b6cb84f3e1`). Breaking changes to section names,
the command grammar, the row schema, or the trust constants require a version
bump and a contract-test update in the same change.
