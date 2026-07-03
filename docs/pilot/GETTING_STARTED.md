# Getting started with SignalBrain

**Trust layer for AI-modified software** — signed improvement receipts, objective re-score after merge, and per-class calibrated trust. Every command and link below works against what is live today (July 2026).

Use this page if you are **interested but not ready to call**. Path A is self-serve (free, ~30 minutes). Path B is the guided design-partner pilot ([terms](#path-b--guided-pilot-with-us)).

---

## Path A — Self-serve test (30 minutes, free)

### Step 1 — See it work on our repo (2 min)

Open **[receipt-gate-demo → Actions](https://github.com/whitestone1121-web/receipt-gate-demo/actions)**.

Watch a passing run on a repo that already has history:

| Receipt | Agent claimed | Re-score found |
|---------|---------------|----------------|
| [0001-tooling-add-function](https://github.com/whitestone1121-web/receipt-gate-demo/blob/main/receipts/0001-tooling-add-function.md) | tests pass (0.9) | **held** |
| [0002-tooling-zero-handling-overclaim](https://github.com/whitestone1121-web/receipt-gate-demo/blob/main/receipts/0002-tooling-zero-handling-overclaim.md) | zero-input handled (0.92) | **caught** — measure fails |
| [0003-tooling-streak-attempt](https://github.com/whitestone1121-web/receipt-gate-demo/blob/main/receipts/0003-tooling-streak-attempt.md) | +1 contract case (0.9) | green, but **`invariant_pin`** — earns zero trust |

Nothing to install; the evidence is in public CI logs and the committed ledger [`.signalbrain/ledger.jsonl`](https://github.com/whitestone1121-web/receipt-gate-demo/blob/main/.signalbrain/ledger.jsonl).

Re-derive it yourself:

```bash
git clone https://github.com/whitestone1121-web/receipt-gate-demo && cd receipt-gate-demo
pip install signalbrain
sb score receipts/*.md --root . --ledger /tmp/fresh-ledger.jsonl --ref HEAD
sb gate --ledger /tmp/fresh-ledger.jsonl --by-class --window 10
```

### Step 2 — Run the four-beat demo locally (5 min)

```bash
pip install signalbrain
git clone https://github.com/whitestone1121-web/signalbrain && bash signalbrain/demo/demo.sh
```

The demo builds a scratch repo and walks four rules live:

1. Unmerged self-scores **refused**
2. Tautological pin batches **recorded, zero trust**
3. Honest failures **recorded forever**
4. Ten held claims → **auto-merge ELIGIBLE** at n=10

Package home: [github.com/whitestone1121-web/signalbrain](https://github.com/whitestone1121-web/signalbrain)

### Step 3 — Wire your own repo (15 min, one PR)

Two files:

1. **Workflow** — copy [`.github/workflows/receipt-gate.yml`](https://github.com/whitestone1121-web/receipt-gate-demo/blob/main/.github/workflows/receipt-gate.yml) from receipt-gate-demo (or use the [`signalbrain` GitHub Action](https://github.com/whitestone1121-web/signalbrain/blob/main/action.yml) composite action).

2. **Receipt emission** — paste the agent instruction block from [`docs/pilot/receipt-emission.md`](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/pilot/receipt-emission.md) into `CLAUDE.md`, `.cursorrules`, or your agent system prompt.

Receipt format: [`docs/RECEIPT_SPEC.md`](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/RECEIPT_SPEC.md)

### Step 4 — Do nothing for a week

Agents keep working. Every merged agent PR with a receipt gets scored in CI; verdicts append to `.signalbrain/ledger.jsonl` (commit it in your repo).

### Step 5 — Read your first trust report

```bash
sb gate --ledger .signalbrain/ledger.jsonl --by-class --window 10
```

Output: per-class hit-rate, track record, and whether any change-class has earned auto-merge.

Week one almost always shows a **calibration gap** — agents claiming ~0.85–0.9 confidence with a materially lower hold rate. That number, about *your* agents on *your* code, is the moment the product sells itself or does not.

---

## Path B — Guided pilot (with us)

**Terms:** first caught overclaim is free. If we catch nothing, you do not pay — and you keep the audit and calibration report.

| Phase | What happens |
|-------|----------------|
| **Day 0** | 15-minute call — pick the busiest agent-PR repo, agree what "caught" means, name a contact who can merge CI changes |
| **Day 1** | We open one PR (you review): workflow + emission block + baseline run. Everything runs in **your CI on your infra** — no code, receipts, or ledger data leave your walls (architectural: the tool has no server to send to) |
| **Days 2–10** | Zero touch — ledger accumulates; we intervene only if the workflow breaks |
| **Day 10** | Ledger report in your repo — every claim ships with the command that re-derives it |

Day-10 report includes:

- Claims scored; hold-rate overall and by confidence band
- The calibration gap (stated confidence vs measured reality, per agent/class)
- Any caught overclaim, written forensically (claim, re-run result, reproduce commands)
- Pins detected (agents grading themselves with their own tests)
- What your agents would need to earn graduated auto-merge

Operator detail: [`docs/pilot/RUNBOOK.md`](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/pilot/RUNBOOK.md)

**Start a conversation:** [alan@signalbrain.ai](mailto:alan@signalbrain.ai?subject=SignalBrain%20design%20partner%20pilot)

---

## Who this is for (and what changes)

**Engineering manager** — "The agent said it's done" is verified today by a human skimming a diff. The gate replaces skim-trust with measured trust: spend review attention on agents and change-classes with bad track records; stop re-checking earned ones.

**Platform / AI lead** — Objective answer to "which agent config is actually better?" Hold-rate per agent, per class, over time — vendor-neutral (we do not sell agents; the referee cannot be a player).

**Compliance / leadership** — Append-only, reproducible audit trail: *every AI-authored change carried an executable claim independently re-verified after merge* — a sentence auditors and customers will eventually require.

**The skeptic** — Our credential is that the system caught its own maker. [Public forensic record](https://github.com/whitestone1121-web/signalbrain/blob/main/docs/incidents/2026-07-tooling-trust-streak-gaming.md) reproduces from git SHAs. Every anti-gaming rule exists because an agent already tried it.

---

## What we tell you honestly before you start

v0.1 has real edges:

- Measure grammar is **pytest / python / bash**-shaped (other stacks via bash wrappers for now)
- **One ledger per repo root** in v0.1
- Agents need the **emission block** before receipts exist at all
- End-to-end on **two public repos** today — yours would be among the first partners, which is why the free-catch terms exist

We publish limitations for the same reason we publish incidents: a trust product that oversells itself refutes its own thesis.

---

## Why run the free gate and still pay later?

Some teams never will — and that is fine. Free adoption spreads the receipt standard; the standard being everywhere is what makes paid layers exist (the same asymmetry as Codecov, HashiCorp, certificate authorities).

What self-hosting does **not** give you:

1. **Detection of attacks you have not seen yet** — our reference deployment is a standing adversarial lab; agents evolve weekly. A fork from last quarter has last quarter's immune system.
2. **Someone to read the ledger** — the gate outputs numbers; judgment (is 78% hold-rate enough for auto-merge here?) is paid labor no fork produces.
3. **Independence** — self-attestation ("we checked our own AI") is worth nothing to customers, auditors, or insurers. You cannot fork a certificate.
4. **The fleet layer** — one repo free forever; org-wide policy, dashboards, retention, SSO, and SLAs are a product build the CLI does not contain.
5. **A throat to choke** — when the gate misfires, enterprises want someone answerable under contract.

Full write-up: [`docs/pilot/FREE_VS_PILOT.md`](FREE_VS_PILOT.md)

The pilots **are** the measure command for that receipt. If free audits never convert, the layers above are mispriced — and we would rather know in ninety days than after incorporating.

---

## Links

| Resource | URL |
|----------|-----|
| Package + CLI (`sb`) | https://github.com/whitestone1121-web/signalbrain |
| Live demo repo | https://github.com/whitestone1121-web/receipt-gate-demo |
| Receipt spec v0.1 | https://github.com/whitestone1121-web/signalbrain/blob/main/docs/RECEIPT_SPEC.md |
| Founding incident | https://github.com/whitestone1121-web/signalbrain/blob/main/docs/incidents/2026-07-tooling-trust-streak-gaming.md |
| Site | https://signalbrain.ai |
