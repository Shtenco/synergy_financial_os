# Distribution Budget State + Current Available Capacity v2

## Why v2 exists

Owner/participant distributions are capital movements, not operating expense. Therefore a correct distribution posting reduces cash/equity/HardNAV but deliberately does not reduce realized external P&L.

That accounting treatment exposes a second-order control problem: the period's gross `period_profit_budget` remains an earnings measure after a payout. A later new Plan must not interpret that gross number as an unused entitlement and distribute the same realized profit twice.

Single-use Authorization prevents replay of one exact batch. It does not by itself prevent a new Authorization from consuming the same period profit again.

V22 therefore separates:

- **gross period profit budget** — what the period earned after retention/loss policy;
- **remaining distribution budget** — the portion not yet canonically paid out net of canonically posted settlement reversals;
- **current available capacity** — the amount that can be distributed now under the current closed ledger, HardNAV and liquidity state.

## 1. `distribution.budget-state/v1`

The budget state is derived from the canonical `ReportingLedger`, not from Plan, Authorization or MetaPay intent state.

For affected period P:

```text
gross_period_profit_budget
  = base historical DistributionCapacityReplay.realized_profit_budget

canonical_distribution_outflows
  = sum canonical OWNER_DISTRIBUTION postings tagged affected_period_id=P

canonical_distribution_reversals
  = sum canonical OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL postings
    whose original_distribution_reporting_entry_digest traces to an
    OWNER_DISTRIBUTION posting for P

net_consumed_distribution_budget
  = canonical_distribution_outflows
    - canonical_distribution_reversals

remaining_period_profit_budget
  = max(0, gross_period_profit_budget
         - net_consumed_distribution_budget)
```

A reversal restores budget only after Financial OS has canonically posted the reversal. MetaPay reversal evidence by itself does not restore entitlement.

The derivation validates canonical two-line accounting shape for payouts and reversals. Cumulative reversals cannot exceed the original distribution posting.

The state stores exact `ledger_sequence` and `ledger_digest`. Any later canonical payout/reversal makes the old budget state stale.

## 2. `liquidity.current-resources/v1`

Historical `liquidity.resources/v1` is bound to StatementReplay. Repeated payout planning requires current resources instead.

The current resource artifact binds:

- exact `financial.snapshot/v2` digest;
- exact `accounting.close/v2` digest;
- snapshot sequence and ledger digest;
- reporting currency and as-of;
- exact LiquidityPolicy digest;
- independent 1w/4w/8w resource evidence.

`FinancialSnapshot v2` stores LiquidNAV rather than raw liquid haircut assets. The resource ceiling is reconstructed deterministically:

```text
liquid_haircut_asset_ceiling
  = current LiquidNAV + current external liabilities
```

Each horizon resource must be non-negative, non-decreasing across longer horizons and no greater than this ceiling.

## 3. `distribution.available-capacity/v2`

The current capacity gate combines remaining entitlement with current solvency and current liquidity.

Current state is accepted only if:

- current ReportingLedger is exactly the ledger sealed by current FinancialSnapshot;
- current AccountingClose verifies the exact snapshot and full sealed event prefix;
- DistributionBudgetState has exactly that same ledger sequence/digest;
- current resource evidence binds that exact Snapshot/Close;
- current maturity snapshot digest set exactly equals `FinancialSnapshot.maturity_snapshot_refs`;
- each maturity snapshot has exactly one translation artifact;
- v2 maturity snapshot/translation `as_of` equals the current snapshot `as_of`;
- independently evidenced resources equal resources already sealed in the current snapshot liquidity horizons;
- reconstructed maturity outflows equal expected outflows already sealed in those snapshot horizons.

Thus current liquidity must agree three ways:

```text
closed FinancialSnapshot
        ==
current resource evidence
        +
reconstructed maturity outflows
```

### Current solvency

```text
current_solvency_headroom
  = max(0, current HardNAV - current required HardNAV buffer)
```

### Current post-distribution liquidity capacity

For each horizon h and proposed distribution D:

```text
D <= R_h - minimum_LCR_h * O_h
D <= R_h - O_h - minimum_surplus_h
D <= R_h
```

The horizon capacity is the non-negative minimum of those bounds. Overall current liquidity capacity is the minimum across 1w/4w/8w.

### Final v2 capacity

```text
final_available_capacity
  = min(
      remaining_period_profit_budget,
      current_solvency_headroom,
      current_liquidity_distribution_capacity
    )
```

Any current snapshot invariant failure forces `NO_ACTION`.

## Canonical example

Historical period economics:

```text
realized P&L        = 30
retention           = 5
gross profit budget = 25
historical liquidity one-shot capacity = 18
```

A canonical distribution later settles/posts 10:

```text
remaining period budget = 25 - 10 = 15
current HardNAV          = 90
HardNAV buffer           = 20
current solvency headroom= 70
```

Current resources/outflows after payout:

```text
1w: R=40, O=10 -> capacity 25
4w: R=65, O=30 -> capacity 29
8w: R=80, O=60 -> capacity 8
```

Therefore:

```text
final_available_capacity = min(15, 70, 8) = 8
```

The system must not return 25 (gross period budget), 15 (remaining entitlement only) or 18 (stale historical liquidity capacity).

## Race protection

Suppose BudgetState is built at ledger sequence N. Another payout is posted, producing sequence N+1, and a new FinancialSnapshot/AccountingClose is captured.

The old BudgetState fails because its `ledger_sequence/ledger_digest` no longer equals the current closed snapshot. Two independently prepared payout plans therefore cannot safely consume the same stale budget state after one of them changes canonical accounting.

## Canonical guard

`build_distribution_available_capacity_canonical_v2()` is the only intended upstream for a later DistributionPlan v2.

The raw builder is a pure derivation helper. The canonical guard additionally:

- verifies the historical base capacity formula object;
- binds base capacity to the exact StatementReplay and original FinancialSnapshot;
- recomputes gross period budget from StatementReplay realized P&L + original retention/loss policy;
- re-derives BudgetState from the current ReportingLedger;
- requires current ReportingLedger == current closed FinancialSnapshot ledger;
- enforces final temporal ordering across close/resources/policy/budget/translation artifacts.

## Authority boundary

All V22 objects are measurement/derivation only:

```text
authorization_authority = NONE
payment_authority       = NONE
execution_authority     = NONE
AI authority            = NONE where applicable
```

A positive current capacity is not permission to pay.

## Versioning rule

No v1 artifact is rewritten or deleted.

`distribution.capacity-replay/v1` remains the immutable historical/restated one-shot calculation. Once canonical owner-distribution/reversal accounting changes the ledger, any later payout planning must use current `distribution.available-capacity/v2`.

The next protocol generation must introduce DistributionPlan/Authorization/Ticket v2 bound to this exact v2 capacity and current closed-state digests. V1 Plan must not be reused for repeated payout cycles.
