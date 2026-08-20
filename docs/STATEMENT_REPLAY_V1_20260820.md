# Accounting Statement Replay v1

`accounting.statement-replay/v1` is a non-mutating Financial OS derivation for reproducible historical restatement.

## Order of trust

The replay never starts from a restated story. It first verifies the original immutable evidence:

1. exact `ledger.event/v2` genesis-based prefix;
2. exact original `financial.snapshot/v2`;
3. exact original `accounting.close/v2`;
4. exact `accounting.period/v1` / `accounting.period-close/v1` relation.

Only then may presentation treatment be applied.

## Reconstructible semantics

Replay requires:

- `account.registry/v1`, whose inner `account_registry_digest` equals the existing ReportingLedger/Snapshot digest;
- `valuation.policy-artifact/v1`, whose inner `valuation_policy_digest` equals the existing ValuationPolicy/Snapshot digest;
- `accounting.restated-period-view/v1` and the exact overlay objects whose digests and excluded ReportingEntry digests match the view.

The derived ledger is a new replay chain. It does not claim its entry digests are the historical entry digests after an exclusion.

## Period boundary

For the first period, opening sequence is 0.

For later periods, the opening `PeriodClose` must equal `AccountingPeriod.opening_period_close_digest`, and its `AccountingClose.event_count` becomes the opening sequence. The current close event count is the closing sequence.

Period P&L and revenue are calculated only from surviving events with original sequence in `(opening_sequence, closing_sequence]`. Their `effective_at` must lie inside the accounting period.

## V1 output

Recalculated:

- hard external assets;
- liquid haircut assets;
- economic haircut assets;
- external liabilities;
- HardNAV;
- LiquidNAV;
- EconomicNAV;
- realized external revenue for the affected period;
- realized external P&L for the affected period.

Explicitly not calculated:

- LCR / liquidity horizons;
- maturity state;
- distribution capacity;
- retained-profit authorization;
- jurisdiction-specific tax restatement.

Those values require additional independently replayable inputs and cannot be inferred from accounting hashes alone.

## Authority

`authority = FINANCIAL_OS_REPLAY_DERIVATION`

`ledger_mutation_authority = NONE`

`execution_authority = NONE`

A replay object is an audit/reporting derivation, not a new canonical ledger, payment authorization, or distribution authorization.
