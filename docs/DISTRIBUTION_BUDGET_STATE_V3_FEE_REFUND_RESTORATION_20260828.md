# DistributionBudgetState v3 — fee-refund restoration

V3 extends fee-aware BudgetState v2 after the canonical settlement-reversal lifecycle.

For the affected period and only after the base StatementReplay closing sequence it derives:

- `E`: canonical `OWNER_DISTRIBUTION_SETTLEMENT_FEE` external expenses;
- `R`: canonical `OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND` expense reversals;
- `F`: canonical `OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE` new external expenses.

Each non-zero refund must reference an exact post-close settlement-fee ReportingEntry from the same affected period. Cumulative refunds referencing one original fee entry cannot exceed that fee. Pre-close fee entries are deliberately not eligible for this restoration path because V3 is defined relative to the pre-distribution base close.

`net_post_close_distribution_fee_cost = E - R + F`

`fee_adjusted_period_profit_budget = min(gross_period_profit_budget, max(0, gross_period_profit_budget - net_post_close_distribution_fee_cost))`

Principal owner-distribution outflows and canonical principal reversals remain the existing capital-entitlement path:

`net_consumed_distribution_budget = canonical_distribution_outflows - canonical_distribution_reversals`

`remaining_period_profit_budget = max(0, fee_adjusted_period_profit_budget - net_consumed_distribution_budget)`.

The upper cap at the original gross period profit budget prevents a provider fee refund from becoming new distributable profit. A refund restores a previously deducted post-close cost; it does not create revenue.

Canonical regression: gross budget 25; post-close settlement fee 1.5; original fee refund 0.5; reversal-processing fee 0.1; net fee cost 1.1; fee-adjusted budget 23.9. A 10 owner distribution later fully returned has net consumed principal budget 0, so remaining entitlement is 23.9.

No authorization, payment, execution or AI authority is introduced.
