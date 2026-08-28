# Distribution handoff v3 — fee-aware capacity lineage

This generation is additive and preserves all v1/v2 handoff artifacts.

## Why v3 exists

`DistributionAvailableCapacity v3` is the first current-capacity generation that explicitly consumes `DistributionBudgetState v2`, where real post-close settlement fees reduce remaining period profit entitlement. Reusing Plan/Auth/Ticket v2 would hide that generation change behind structurally similar fields.

V3 therefore creates an explicit type boundary:

```text
DistributionBudgetState v2
  -> DistributionAvailableCapacity v3
  -> DistributionPlan v3
  -> DistributionAuthorization v3
  -> DistributionExecutionTicket v3
  -> MetaPay v3 handoff
```

## Invariants

1. `Plan v3` accepts only `DistributionAvailableCapacity v3`.
2. `principal_total + external_fee_budget <= final_available_capacity`.
3. Beneficiary principal is immutable and separate from the fee budget.
4. Only `HUMAN_COMMITTEE` or `MULTISIG_GOVERNANCE` may approve.
5. AI authority is always `NONE`.
6. Authorization has one exact batch and cannot execute payment.
7. Ticket is short-lived, cannot outlive authorization, and carries only `payment_authority=METAPAY_ONLY` handoff semantics; `execution_authority=NONE`.
8. Legacy v1/v2 Plan/Auth/Ticket objects are not accepted on the v3 path.

## Canonical regression

Fee-aware capacity = 8.

Two beneficiaries receive principal 4 + 2 = 6 and the payer-borne external fee budget is 2. Total authorized cash ceiling is therefore 8 and the batch is valid.

If principal is raised to 7 while fee budget stays 2, total 9 exceeds fee-aware capacity 8 and plan creation fails.

## Next owner

MetaPay must implement a new generation that consumes exactly the v3 Plan/Auth/Ticket family, marks authorization consumed once before release of payment intents, preserves beneficiary principal, records actual payer-borne fee separately, and never interprets unused fee budget as profit.
