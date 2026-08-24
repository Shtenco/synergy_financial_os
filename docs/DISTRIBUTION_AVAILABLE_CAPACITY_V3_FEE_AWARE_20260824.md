# DistributionAvailableCapacity v3 — fee-aware current capacity

This generation is additive. It does not modify `distribution.available-capacity/v2`, `distribution.budget-state/v1`, or any historical accounting artifact.

## Problem

Owner-distribution principal is excluded from realized P&L, while real payer-borne settlement fees are external expenses. After a post-close fee is posted, later distribution planning must not reuse the historical gross profit entitlement as if the fee had not consumed external value.

## Required input generation

`distribution.available-capacity/v3` accepts only `distribution.budget-state/v2`.

The v3 builder rejects BudgetState v1 before any current-capacity calculation.

## Economic chain

```text
gross_period_profit_budget
- post_close_settlement_fee_expenses
= fee_adjusted_period_profit_budget

fee_adjusted_period_profit_budget
- (canonical_distribution_outflows - canonical_distribution_reversals)
= remaining_period_profit_budget
```

Both subtractions are floored at zero by the canonical BudgetState v2 rules.

Current capacity then remains:

```text
final_available_capacity =
  0, if blockers exist
  else min(
      remaining_period_profit_budget,
      current_solvency_headroom,
      current_liquidity_distribution_capacity
  )
```

The HardNAV, maturity, LCR and liquidity arithmetic is intentionally reused from the already-tested v2 calculation kernel so the new generation changes only the budget-state semantic binding rather than forking the financial mathematics.

## Canonical regression

- gross period profit budget: 25
- post-close settlement fee expense: 1.5
- fee-adjusted budget: 23.5
- canonical owner distributions: 10
- reversals: 0
- remaining entitlement: 13.5
- current HardNAV headroom: 70
- current liquidity distribution capacity: 8
- final capacity: `min(13.5,70,8)=8`

A fresh outer digest cannot legalize a changed fee amount or inflated final capacity because the v3 payload verifier recomputes the fee-adjusted/remaining/final formulas.

## Authority boundary

`DistributionAvailableCapacity v3` is a deterministic measurement only.

- authorization authority: NONE
- payment authority: NONE
- execution authority: NONE
- AI authority: NONE

The next generation must be a new Plan/Authorization/ExecutionTicket family binding v3 exactly; v2 handoff artifacts must not silently accept the new capacity generation.
