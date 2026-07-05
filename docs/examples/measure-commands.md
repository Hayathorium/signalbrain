# Measure command examples

SignalBrain receipts are language-neutral: the scorer re-runs argv-style commands and trusts exit codes, not a specific test framework. Keep shell pipelines and redirects out of receipts; put complex logic in a committed script and invoke that script.

## JavaScript / TypeScript

~~~markdown
# 0001-bugfix-cache-ttl — Preserve cache TTL after refresh

## Compared
- branch:    `feature/cache-ttl@abc123`
- baseline:  `origin/main@def456`
- date:      `2026-07-05`

## Change summary

Fixes cache refresh so the original TTL is preserved instead of resetting to the default.

## Metric delta

| Metric | Baseline | Branch | Delta |
|---|---|---|---|
| TTL preservation test | failing | passing | improvement |

### How measured

```bash
npx jest packages/cache/cache_ttl.test.ts --ci
```

## Verdict

`improvement`

## Confidence

0.91

## change_class

bugfix
~~~

Jest note: do not use `--passWithNoTests` in a receipt measure. A command that can pass without executing the target test is not a valid measure.

## Go

~~~markdown
# 0002-bugfix-retry-budget — Stop retry budget leakage

## Compared
- branch:    `feature/retry-budget@abc123`
- baseline:  `origin/main@def456`
- date:      `2026-07-05`

## Change summary

Fixes retry accounting so canceled attempts return unused budget to the caller.

## Metric delta

| Metric | Baseline | Branch | Delta |
|---|---|---|---|
| retry budget regression | failing | passing | improvement |

### How measured

```bash
go test ./pkg/retry -run TestBudgetReturnedOnCancel
```

## Verdict

`improvement`

## Confidence

0.88

## change_class

bugfix
~~~

Go note: prefer a package path plus a specific `-run` target when the claim is narrow. If a receipt claims broader behavior, use the broader package set that could actually fail.

## Rust

~~~markdown
# 0003-bugfix-idempotent-writer — Preserve idempotent writes

## Compared
- branch:    `feature/idempotent-writer@abc123`
- baseline:  `origin/main@def456`
- date:      `2026-07-05`

## Change summary

Fixes duplicate write handling so replaying the same operation does not append a second record.

## Metric delta

| Metric | Baseline | Branch | Delta |
|---|---|---|---|
| idempotent writer regression | failing | passing | improvement |

### How measured

```bash
cargo test writer::tests::idempotent_replay_does_not_append
```

## Verdict

`improvement`

## Confidence

0.9

## change_class

bugfix
~~~

Rust note: if the workspace has feature-gated behavior, include the same feature flags users need in production, for example `cargo test --features durable-writes writer::tests::idempotent_replay_does_not_append`.
