# Distribution fee accounting v2 — principal and external fee stay separate

This layer is additive above the Financial OS fee-budget handoff and MetaPay fee-budget settlement v2. Distribution accounting v1 and settlement-reversal accounting v1 remain immutable.

## Posting law

For a MetaPay utilization with:

- settled beneficiary principal `P`;
- actually incurred payer-borne external fee `F`;

Financial OS posts two economically different flows.

### Principal

`OWNER_DISTRIBUTION`

- flow type: `EXTERNAL_CAPITAL`;
- debit distribution equity;
- credit external cash;
- P&L treatment: `EXCLUDED_FROM_REALIZED_PNL`.

### Fee

`OWNER_DISTRIBUTION_SETTLEMENT_FEE`

- flow type: `EXTERNAL_EXPENSE`;
- debit external settlement-fee expense;
- credit external cash;
- P&L treatment: `REALIZED_EXTERNAL_EXPENSE`.

Therefore:

`realized_external_pnl_effect = -F`, not `-(P+F)`.

The total external cash effect is `-(P+F)`.

## Failed settlement with fee

If no beneficiary principal settles but an externally evidenced provider/network fee is incurred, the accounting decision may still be POSTABLE. It posts only the external expense. Distribution equity is unchanged.

## Unused fee budget

Authorized but unused fee budget is not a ledger flow. It creates no revenue, expense, capital flow or profit. Only actually evidenced external fee is posted.

## Evidence boundary

Financial OS independently re-verifies MetaPay BatchAttempt v2, every SettlementReceipt v2 and Utilization v2 against the exact Financial OS Plan/Authorization/ExecutionTicket v2. MetaPay cannot post the ledger itself and cannot recognize profit.

The next budget-generation layer must incorporate fee-expense entries into remaining distributable profit when those fees economically belong to the affected accounting period. Current HardNAV/liquidity already reflect cash loss after posting, but remaining-period profit budget must not remain artificially high merely because the fee is not OWNER_DISTRIBUTION principal.
