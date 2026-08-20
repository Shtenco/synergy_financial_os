# Distribution Capacity Replay v1

This layer answers one narrow question after historical restatement:

> What is the maximum distribution amount mathematically supportable by the restated realized-profit budget, HardNAV buffer and evidenced post-distribution liquidity constraints?

It does **not** authorize a payment.

## Accounting side

The original FinancialSnapshot remains immutable and supplies only its already-sealed policy inputs:

- required retention;
- realized loss carryforward;
- required HardNAV buffer;
- original invariant-failure list.

The measurements replaced by restatement come from StatementReplay:

- restated realized external P&L;
- restated HardNAV.

Therefore:

`profit budget = max(0, restated realized P&L - retention - loss carryforward)`

`solvency headroom = max(0, restated HardNAV - required HardNAV buffer)`

`accounting distribution capacity = min(profit budget, solvency headroom)`

## Liquidity side

`liquidity.policy/v1` contains explicit 1w/4w/8w:

- minimum LCR;
- minimum liquidity surplus.

V1 models a cash distribution D as an immediate reduction of evidenced liquid resources at every horizon.

For horizon h:

`D <= R_h - minimum_LCR_h * O_h`

and

`D <= R_h - O_h - minimum_surplus_h`

with D also bounded by available resources.

Therefore:

`horizon capacity = max(0, min(R_h, LCR headroom, surplus headroom))`

`liquidity distribution capacity = min(all horizon capacities)`

## Final capacity

If there are no blockers:

`final distribution capacity = min(accounting distribution capacity, liquidity distribution capacity)`

If the original immutable FinancialSnapshot carried any invariant failures, v1 fails conservatively to `NO_ACTION`. It does not claim that a historical restatement automatically resolved a previously recorded policy/invariant failure. That requires a future independent policy reevaluation.

## Canonical example

Restated accounting:
- realized P&L = 30;
- retention = 5;
- loss carryforward = 0;
- HardNAV = 100;
- HardNAV buffer = 20.

Accounting capacity = 25.

Liquidity:
- resources = 50 / 75 / 90;
- outflows = 10 / 30 / 60;
- minimum LCR = 1.2 at each horizon;
- minimum surplus = 5.

Horizon capacities = 35 / 39 / 18.

Liquidity capacity = 18.

Final mathematical capacity = 18.

## Authority

`authorization_authority = NONE`

`payment_authority = NONE`

`execution_authority = NONE`

A later distribution-authorization object must be separately human/multisig authorized, state-bound, time-bounded and payment-bound. This replay is only a deterministic upper bound.