# Distribution fee budget v3 — principal protected from settlement fees

This layer is additive above `distribution.available-capacity/v2`. Plan/Authorization/ExecutionTicket v1 remain immutable and keep their original zero-fee semantics.

## Economic invariant

For one current Financial OS distribution capacity `C`:

`principal_total + payer_borne_external_fee_budget <= C`

Beneficiary principal is the exact sum of beneficiary amounts. External fee budget is a separate payer-borne ceiling. It is not a discount to principal and it is not additional unbudgeted cash outflow.

Example:

- current available capacity: 12 USDC;
- exact beneficiary principal: 10 USDC;
- external fee budget: 2 USDC;
- maximum authorized payer cash outflow: 12 USDC.

A 3 USDC fee budget is rejected. A provider cannot transform `10 principal + 2 fee` into `9 principal + 3 fee` while claiming the same total outflow. The exact beneficiary batch and principal are independently bound by digest and authorization.

## Objects

### `distribution.plan/v2`

Binds one exact current `distribution.available-capacity/v2`, one source account and one exact beneficiary batch. It carries:

- `principal_total`;
- `external_fee_budget`;
- `total_authorized_outflow_ceiling = principal_total + external_fee_budget`;
- `capacity_limit = current final_available_capacity`.

It has no authorization, payment, execution or AI authority.

### `distribution.authorization/v2`

Only `HUMAN_COMMITTEE` or `MULTISIG_GOVERNANCE` may approve it. APPROVED binds the exact Plan v2 principal, fee budget and total outflow ceiling. AI authority is structurally `NONE`.

Authorization still does not execute settlement. It delegates only to a separate MetaPay handoff after a valid ExecutionTicket v2.

### `distribution.execution-ticket/v2`

Short-lived Financial OS gate that re-verifies the current Plan v2, Authorization v2 and AvailableCapacity v2 immediately before handoff. It cannot outlive the authorization.

`payment_authority=METAPAY_ONLY`, while the ticket itself has `execution_authority=NONE`.

## Independent bundle verifier

`distribution_fee_budget_contract_v3.py` reconstructs objects from canonical payload bytes, recomputes digests/formulas and rechecks the entire chain:

`AvailableCapacity v2 -> Plan v2 -> Authorization v2 -> ExecutionTicket v2`.

A fresh outer digest cannot legalize a changed principal, changed fee budget, stale capacity or expanded outflow ceiling.

Legacy v1 Plan/Authorization/Ticket are explicitly rejected as sources of payer-borne external-fee authority.

## MetaPay contract for the next generation

MetaPay may later report an actual payer-borne fee `F_actual` only when:

`0 <= F_actual <= external_fee_budget`

and:

`settled_principal + F_actual <= total_authorized_outflow_ceiling`.

For each settled beneficiary, beneficiary principal must equal the exact Financial OS planned principal. A provider fee may not be netted from beneficiary principal.

Unused fee budget is simply unspent capacity; it is not MetaPay profit and it does not prove new Financial OS profit.

Settlement evidence remains a MetaPay responsibility. Accounting of actually settled principal and actually incurred external fee remains a later Financial OS consumer responsibility.
