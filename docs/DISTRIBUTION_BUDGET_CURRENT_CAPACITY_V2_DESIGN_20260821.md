# Distribution Budget + Current Capacity v2 design

## Problem

`distribution.capacity-replay/v1` correctly derives a one-shot mathematical payout limit from restated period P&L, HardNAV and liquidity. `distribution.authorization/v1` is single-use, and MetaPay consumes it at the first batch attempt.

That is not sufficient for a later new Plan/Authorization.

After a canonical owner distribution, realized external P&L intentionally remains unchanged. Therefore a new snapshot or a new v1 capacity derived from the same period can expose the same gross realized-profit budget again unless prior canonical distributions are deducted.

Example:
- gross realized-profit budget = 25;
- initial liquidity distribution capacity = 18;
- first actual settlement = 10.

The period-profit remainder is 15, but the original liquidity headroom remainder is only 8. Reusing either the gross period budget or the historical liquidity state can therefore over-authorize.

## Required v2 split

### 1. `distribution.budget-state/v1`

Derived only from canonical ReportingLedger entries:

`gross_period_budget = base DistributionCapacityReplay.realized_profit_budget`

`distribution_outflows = canonical OWNER_DISTRIBUTION postings for affected_period_id`

`distribution_reversals = canonical OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL postings traced back to those original distribution entries`

`net_consumed_budget = distribution_outflows - distribution_reversals`

`remaining_period_budget = max(0, gross_period_budget - net_consumed_budget)`

A reversal restores budget only after the reversal itself is canonically posted. Settlement evidence alone never restores budget.

### 2. `liquidity.current-resources/v1`

A current, evidence-bound 1w/4w/8w resource artifact bound to one exact closed `financial.snapshot/v2` / `accounting.close/v2`, rather than to a historical StatementReplay.

### 3. `distribution.available-capacity/v2`

Combines:
- remaining period budget;
- current closed FinancialSnapshot HardNAV and current required HardNAV buffer;
- current liquidity resources;
- exact current maturity snapshots / translations;
- current LiquidityPolicy floors.

For each horizon the post-distribution liquidity headroom remains:

`D <= R_h - minimum_LCR_h * O_h`

`D <= R_h - O_h - minimum_surplus_h`

Then:

`final_available_capacity = min(remaining_period_budget, current_solvency_headroom, current_liquidity_capacity)`

Any current snapshot invariant failure => `NO_ACTION`.

## Authority

All three artifacts are measurement/derivation only. They do not authorize or execute a payout.

A later `distribution.plan/v2` must bind this v2 available-capacity object; v1 Plan must not be reused after canonical distribution state changes.
