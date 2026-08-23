# DistributionBudgetState v2 — fee-aware remaining profit entitlement

This generation is additive to DistributionBudgetState v1. V1 remains the historical principal/reversal budget derivation.

## Why v2 exists

Settlement fees are external expenses. Once Financial OS posts an actual MetaPay fee as `OWNER_DISTRIBUTION_SETTLEMENT_FEE` / `EXTERNAL_EXPENSE`, current HardNAV and liquidity fall immediately. But a historical gross period-profit entitlement must also fall if the fee economically belongs to that affected period and occurred after the base accounting close.

Naively subtracting all fee entries would double count fees already included in the base StatementReplay realized P&L. V2 therefore binds the exact base StatementReplay and its `closing_sequence`.

## Formula

`post_close_settlement_fee_expenses = sum(valid fee entries for affected period with sequence > base closing_sequence)`

`fee_adjusted_period_profit_budget = max(0, gross_period_profit_budget - post_close_settlement_fee_expenses)`

`remaining_period_profit_budget = max(0, fee_adjusted_period_profit_budget - net_consumed_distribution_budget)`

Owner-distribution principal is still deducted separately because `OWNER_DISTRIBUTION` is external capital and explicitly excluded from realized P&L.

## Regression vector

- historical gross distributable profit: 25;
- pre-close settlement fee: 0.5 — already represented by historical P&L, not deducted again;
- owner distribution principal: 10;
- post-close settlement fee: 1.5;
- fee-adjusted period budget: 23.5;
- remaining distributable profit: 13.5.

A fee attributed to another period is ignored by this period's budget state.

## Authority

BudgetState v2 derives capacity only. authorization/payment/execution/AI authority remain NONE.

The next generation is DistributionAvailableCapacity v3, which must consume BudgetState v2 so fee-adjusted remaining profit actually constrains the next Plan v2.
