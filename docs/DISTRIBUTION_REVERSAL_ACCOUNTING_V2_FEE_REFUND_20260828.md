# Distribution Reversal Accounting v2

This additive generation consumes MetaPay `distribution.settlement-reversal/v2` for an originally settled and canonically accounted Financial OS v3 owner distribution.

Financial OS re-verifies the original Plan/Auth/Ticket v3, BatchAttempt v3, complete SettlementReceipt v3 set, Utilization v3, original DistributionFeeAccountingDecision v3 and canonical original ledger postings before recognizing the later reversal.

Three economic flows are deliberately separate:

1. Returned principal `P`:
   - Dr External Cash `P`
   - Cr Distribution Equity `P`
   - `FlowType.EXTERNAL_CAPITAL`
   - `economic_class=OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL`
   - realized P&L effect = 0.

2. Refund of original settlement fee `R`:
   - Dr External Cash `R`
   - Cr Settlement Fee Expense `R`
   - `FlowType.EXTERNAL_EXPENSE`
   - `economic_class=OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND`
   - realized P&L effect = `+R` because it reverses a previously recognized external expense.

3. New reversal-processing fee `F`:
   - Dr Settlement Fee Expense `F`
   - Cr External Cash `F`
   - `FlowType.EXTERNAL_EXPENSE`
   - `economic_class=OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE`
   - realized P&L effect = `-F`.

Therefore:

`gross_cash_return = P + R`

`net_cash_effect = P + R - F`

`realized_pnl_effect = R - F`.

A refund cannot exceed the fee recorded by the original beneficiary settlement receipt and requires the canonical original fee posting to exist. A second accounting reversal for the same original receipt is fail-closed. MetaPay `authorization_consumption=REMAINS_CONSUMED` is mandatory; reversal never creates payment authority.

Historical reversal-accounting v1 is preserved unchanged. The next budget-state generation must restore fee-adjusted distributable entitlement only from canonical `OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND` postings while deducting new `OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE` postings, and must cap restored entitlement at the original gross period profit budget.
