# Distribution Reversal Accounting v1

This layer handles a later provider reversal/compensation of a distribution that was already SETTLED and already posted in Financial OS.

Nothing historical is rewritten:
- original DistributionPlan/Authorization/Ticket remain immutable;
- original MetaPay receipt/utilization remain immutable;
- original owner-distribution ReportingEntry remains immutable;
- authorization remains consumed.

## Preconditions

Financial OS independently re-verifies original batch attempt, utilization and terminal receipt set against the original Plan/Auth/Ticket.

The supplied original `distribution.accounting-decision/v1` must match those exact evidence digests.

Financial OS then requires one exact prior ReportingLedger entry with:
- `reference == original distribution.utilization digest`;
- `FlowType.EXTERNAL_CAPITAL`;
- `evidence_digest == original DistributionAccountingDecision digest`;
- `economic_class == OWNER_DISTRIBUTION`;
- canonical two-line posting matching the original settled total.

A reversal cannot restore cash/equity for a payout that was never actually posted.

## MetaPay reversal

`distribution.settlement-reversal/v1` must:
- be issued by MetaPay settlement authority;
- bind exactly one originally SETTLED reconciled receipt;
- preserve payer/payee/asset/amount/idempotency lineage;
- have zero payer-borne reversal fee in V1;
- remain `authorization_consumption=REMAINS_CONSUMED`.

## Canonical recovery posting

For reversed beneficiary amount D:

`Dr External Cash D`

`Cr Distribution Equity D`

with:
- FlowType.EXTERNAL_CAPITAL;
- economic_class=OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL;
- capital_direction=INFLOW_REVERSAL_OF_PRIOR_OUTFLOW;
- pnl_treatment=EXCLUDED_FROM_REALIZED_PNL.

Thus a payout and its later exact provider reversal net to zero signed capital effect and zero realized P&L.

## Independent replay protection

Financial OS scans existing ReportingEntries for `original_distribution_receipt_digest`. If that receipt has already been recovered by an OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL entry, a second recovery is NO_ACTION even if a caller presents another separately hashed reversal artifact.

## Deliberate V1 limits

Fee-bearing reversals, FX reversals, partial provider returns and beneficiary disputes that do not map to one exact prior receipt are not guessed. They require separate later generations with explicit economic evidence.