# DistributionAvailableCapacity v4

V4 is required because AvailableCapacity v3 is explicitly bound to BudgetState v2. After canonical settlement reversal/refund accounting, BudgetState v3 has new semantics that must not be consumed through an older capacity schema.

V4 accepts only `distribution.budget-state/v3` and carries its exact fee lifecycle decomposition:

- settlement fee expenses;
- canonical original-fee refunds;
- new reversal-processing fees;
- net post-close distribution fee cost;
- restored fee-adjusted period profit budget;
- distribution principal outflows and principal reversals;
- remaining period entitlement.

The mature current HardNAV, maturity and 1w/4w/8w liquidity arithmetic is reused through the existing v2 math kernel, but the returned V4 object explicitly pins the BudgetState v3 digest/schema.

`final_available_capacity = 0 if blockers else min(remaining_period_profit_budget, current_solvency_headroom, current_liquidity_distribution_capacity)`.

Canonical regression payload: gross budget 25; settlement fees 1.5; fee refunds 0.5; reversal-processing fees 0.1; net fee cost 1.1; principal outflow/reversal 10/10; remaining entitlement 23.9; HardNAV headroom 70; liquidity capacity 8; final capacity 8.

V4 is a deterministic non-authorizing upper bound for a *future* distribution cycle. It does not reactivate the authorization used by the reversed payout and it does not implicitly create a Plan v4.
