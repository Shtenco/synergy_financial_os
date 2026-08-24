# Distribution fee accounting v3 — MetaPay v3 consumer

This generation is additive. Accounting v1/v2, historical Plan/Auth/Ticket generations and prior MetaPay evidence remain unchanged.

## Exact input chain

```text
DistributionBudgetState v2
  -> DistributionAvailableCapacity v3
  -> DistributionPlan v3
  -> DistributionAuthorization v3
  -> DistributionExecutionTicket v3
  -> MetaPay DistributionBatchAttempt v3
  -> SettlementReceipt v3[]
  -> DistributionUtilization v3
  -> Financial OS DistributionFeeAccountingDecision v3
```

Accounting v3 rejects v2 attempts/receipts/utilizations even when an attacker recomputes valid outer digests after changing the schema identifier.

## Independent verification

Financial OS independently verifies:
- exact Plan/Auth/Ticket v3 object identities;
- `distribution.available-capacity/v3` lineage;
- exact beneficiary principal/destination/idempotency in the attempt;
- every terminal receipt and its settlement/fee evidence;
- one receipt per planned beneficiary;
- utilization receipt set;
- aggregate settled principal, actual fee, unused fee budget and payer cash outflow;
- MetaPay authority boundaries and permanent authorization consumption.

MetaPay never becomes accounting or profit-recognition authority.

## Posting law

For settled beneficiary principal `P`:

```text
Dr Distribution Equity P
Cr External Cash P
flow = EXTERNAL_CAPITAL
economic_class = OWNER_DISTRIBUTION
pnl_treatment = EXCLUDED_FROM_REALIZED_PNL
```

For actually incurred external settlement fee `F`:

```text
Dr External Settlement Fee Expense F
Cr External Cash F
flow = EXTERNAL_EXPENSE
economic_class = OWNER_DISTRIBUTION_SETTLEMENT_FEE
pnl_treatment = REALIZED_EXTERNAL_EXPENSE
```

Therefore:

```text
cash effect = -(P + F)
realized external P&L effect = -F
```

A fully failed settlement can still be POSTABLE when `P=0` and a real externally evidenced fee exists. Only the fee expense is posted; distribution equity is unchanged.

Unused authorized fee budget is never posted as revenue, expense, capital or profit.

## Regression vector

Starting external cash/equity = 30.

Full settlement:
- principal = 18
- actual external fee = 1.9
- cash after posting = 10.1
- equity after posting = 12
- fee expense = 1.9
- realized external P&L effect = -1.9.

Failed settlement with aggregate actual fee 0.5:
- principal posting = none
- fee expense posting = 0.5
- equity stays 30
- realized external P&L effect = -0.5.

## Next boundary

The next additive generation must model later external compensation/refund separately:
- returned owner-distribution principal reverses EXTERNAL_CAPITAL;
- refunded settlement fee reverses the previously posted EXTERNAL_EXPENSE only to the amount externally refunded;
- authorization remains consumed;
- BudgetState may restore fee-adjusted entitlement only from canonical fee-expense reversal/refund evidence, never from unused fee budget.
