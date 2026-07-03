# Receipt emission — making your agents write verifiable claims

Your coding agents don't write receipts today. This template fixes that in one
paste. It goes into the agent's standing instructions (`CLAUDE.md`, `.cursorrules`,
system prompt — wherever your agent reads its rules).

## The drop-in block

```markdown
## Improvement receipts (required)

Every change you ship MUST include a receipt file: `receipts/NNNN-<class>-<slug>.md`
(NNNN = next unused number; class = bugfix | tooling | config | research).
The receipt is a claim you will be held to — it is objectively re-scored after
merge, and your autonomy depends on your claims holding. Rules:

1. `### How measured` must contain commands that PROVE the claimed effect and
   could realistically FAIL if the claim is false. Prefer commands that exercise
   pre-existing tests or observable behavior. A measure that only runs a test
   you wrote in this same change earns zero trust.
2. `## Confidence` is your honest probability (0.0–1.0) that the measure passes
   on re-run. Overclaiming at ≥0.85 damages your track record permanently.
   When unsure, state lower confidence — calibration is rewarded, bravado is not.
3. If you could not measure, say so: use verdict `not_applicable` — never invent
   a measurement.
4. Use this exact structure:

# NNNN — <one-line title>

## Compared
- branch:    `<branch>@<sha>`
- baseline:  `<default-branch>@<sha>`
- date:      `YYYY-MM-DD`

## Change summary
<what changed and why>

## Metric delta
| Metric | Baseline | Branch | Delta |
|---|---|---|---|
| <measured values, not aspirations> |

### How measured
```bash
<the commands>
```

## Verdict
`improvement` | `parity` | `regression` | `not_applicable`

## Confidence
<0.0–1.0>

## change_class

<bugfix | tooling | config | research>
```

## Grammar constraints your agents must know

- Allowed measure commands: `pytest …`, `python`/`python3 …`, `bash …`,
  `export VAR=value`, and inline `VAR=value cmd` prefixes.
- Shell pipelines/redirects are supported (`cmd 2>&1 | grep x`) for allowed
  leaders, but single-purpose commands are more robust.
- Measures must NOT invoke the scoring pipeline itself (self-reference
  deadlocks the scorer — learned from receipt 0582 in the reference deployment).
- Measures run from the repo root with the repo's environment; anything they
  need must be derivable from a fresh checkout.

## Calibration note for operators

Expect the first week's receipts to be badly calibrated — agents default to
0.9-confidence on everything. That's not a failure; **that gap is the finding.**
The ledger makes it visible, and most agents' calibration improves once their
instructions include their own current hit-rate.
