# Adoption tracking & the fleet layer — doctrine

The free tier is architecturally client-side: your CI, your repo, your ledger,
no SignalBrain server. That is the pitch **and** the constraint — we cannot see
adoption the way a SaaS sees a user table, and we will not fake it with hidden
telemetry. We track footprints users leave in public git, and opt-in
registration whose benefit flows to the registrant.

## Signals we can observe (no customer data required)

| Signal | What it tells us | Honest limit |
|---|---|---|
| Workflow references to `whitestone1121-web/signalbrain@…` | repos running the gate | public repos only; GitHub code search lags |
| Public `.signalbrain/ledger.jsonl` files | committed audit trails in the wild | public repos only |
| `receipt-gate-demo` stars/forks/Actions runs | top-of-funnel interest | interest ≠ adoption |
| Package download counts | pulls | aggregate, anonymous — requires PyPI publish |
| Badge fetches | repos displaying calibrated trust | shields caches aggressively; Pages insights are 14-day — weak signal |
| Inbound (pilot mailto, HN/LinkedIn UTM) | named, high-intent leads | the only *named* signal at v0.1 |

Baseline recorded 2026-07-03: action references in public code search = **1**
(our own demo repo). External adoption is zero; every future claim about
adoption must cite the reproducible search that measured it.

## Counting prerequisites (cheap, do before adoption exists)

1. **PyPI publish** — `signalbrain` is unclaimed as of 2026-07-03 (verified
   404). Grab it: cleaner installs than `git+https`, and download counts come
   free. Name-squatting risk is real for a public product.
2. **GitHub Marketplace listing** for the Action — install counts don't exist
   for bare `uses:` references; the Marketplace provides them.

## Opt-in registration (the on-brand version of telemetry)

- **Action input `telemetry:`** — default **off**; when enabled, posts an
  anonymized gate summary (hold-rate bands, class counts, pin count) and the
  org/repo slug only with explicit opt-in. The fleet tier may contractually
  require it; the free tier never does.
- **`sb gate --register`** — one command after a green gate: share this repo's
  aggregate calibration numbers with the public benchmark. Ledger-derived
  numbers only — never receipt text, never source.
- **Public ledger index** — we may index public repos with committed ledgers,
  but the published map shows **aggregates only; named entries are opt-in**.
  A trust company does not out its users, even with public data.

## Why free spread pays (the documented asymmetry)

Free riders are distribution for the receipt standard — Codecov / HashiCorp /
CA economics. Mass adoption creates: the design-partner pipeline (public repos
with poor hold-rates are qualified outbound), the benchmark ("industry bugfix
hold-rate is X"), standard gravity (auditors start asking for receipt-shaped
claims), and conversion pressure at exactly the seams FREE_VS_PILOT.md prices:
independence, threat-intel, interpretation, fleet policy, accountability.

## Sequence

1. **v0.1 (now):** observe public footprints + inbound. Ship nothing.
2. **~10–50 public adopters:** PyPI + Marketplace publish, opt-in Action
   telemetry, `sb gate --register`.
3. **Design-partner conversations:** fleet dashboard MVP (GitHub App/SSO,
   cross-repo ledgers, org policy) — the point where "who uses it" becomes a
   customer record because they asked for it, not surveillance.

## Never

- Hidden telemetry, phone-home defaults, or "anonymous" data that isn't.
- Calling self-hosted gates "independent" — that word is the paid tier's.
- Naming adopters in any public index without their opt-in.
- Building the fleet layer before the first paying catch (decision rule).
- Adoption claims without the reproducible query that measured them.
