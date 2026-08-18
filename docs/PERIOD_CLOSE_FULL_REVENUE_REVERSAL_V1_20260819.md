# PeriodClose N -> full revenue reversal -> PeriodClose N+1

This generation introduces the first closed-period adjustment path without mutating historical accounting facts.

## Immutable period chain

`accounting.period/v1` binds one reporting interval, perimeter, currency, accounting-policy digest, requirement-registry digest and the previous `accounting.period-close/v1` digest.

`accounting.period-close/v1` wraps a verified AccountingClose v2. It requires:

- `FinancialSnapshot.as_of == AccountingPeriod.ends_at`;
- exact perimeter/currency agreement;
- AccountingClose v2 verification against the supplied full ledger prefix and snapshot;
- period requirement-registry digest agreement;
- every declared adjustment authorization digest to occur exactly once as `LedgerEvent.evidence_digest` inside the sealed prefix.

Historical PeriodClose bytes are never rewritten.

## Revenue reversal v1

`revenue.reversal-authorization/v1` supports only `FULL_ONLY` for:

- `REFUND`;
- `CHARGEBACK`;
- `CANCELLATION`.

It binds the original PeriodClose, AccountingClose, RevenueRecognition v2, LedgerEvent v2 and ReportingEntry digests plus external/decision evidence. Authorization is HUMAN_COMMITTEE or MULTISIG_GOVERNANCE; AI authority is NONE and posting is separate.

The target period must directly succeed the original PeriodClose. Authorization must occur after the original period was closed and the effective time must lie in the successor period.

## Canonical economic reversal

For the canonical original posting:

```
Dr cash             125
    Cr revenue      118
    Cr tax            5
    Cr refund reserve 2
```

FULL_ONLY reversal posts a new entry:

```
Dr revenue          118
Dr tax liability      5
Dr refund reserve     2
    Cr cash          125
```

The new entry uses `FlowType.EXTERNAL_EXPENSE` with `economic_class=REVENUE_REVERSAL`. This deliberately preserves `realized_external_revenue` as a non-negative gross-revenue metric while producing signed period P&L of `-118` and HardNAV movement `118 -> 0`.

The original entry, RevenueRecognition, Snapshot, AccountingClose and PeriodClose remain immutable.

## Fail-closed boundary

V1 refuses:

- partial reversal;
- a non-successor target period;
- AI authorization;
- replay after the original balances have already been reversed;
- a simple reversal after tax/refund/cash components are no longer available in their original form;
- a PeriodClose that claims an adjustment authorization which does not occur exactly once in its sealed LedgerEvent prefix.

More complex cases — partial refunds, tax already remitted, foreign-currency adjustments and prior-period accounting errors — require a later adjustment/restatement generation rather than being guessed by v1.
