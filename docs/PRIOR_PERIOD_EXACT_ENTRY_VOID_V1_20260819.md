# Prior-period exact-entry void v1 — 2026-08-19

This layer is **not** a refund/chargeback mechanism.

A refund or chargeback is a new external economic event and belongs to `revenue.adjustment-authorization/v1` / `revenue.reversal-authorization/v1`.

`accounting.prior-period-correction-authorization/v1` is for a different fact: after a reporting period has been immutably closed, evidence proves that one previously sealed ReportingEntry itself was erroneous, duplicated or misclassified and must be voided exactly.

## Immutable-history rule

The historical objects are never changed:

```
ReportingEntry N
LedgerEvent v2
AccountingClose v2
PeriodClose N
```

remain byte-for-byte historical facts.

The correction occurs later:

```
PeriodClose N
   ↓ immutable ancestry proof
Target Period M
   ↓ human/multisig correction authorization
NEW exact opposite ReportingEntry
```

The new entry carries the correction authorization digest as evidence and metadata identifying the original PeriodClose, AccountingClose, LedgerEvent and ReportingEntry.

## V1 is intentionally narrow

Only:

```
correction_scope = EXACT_ENTRY_VOID
```

is supported.

Every original debit becomes an equal correction credit and every original credit becomes an equal correction debit.

V1 does not guess a replacement value, account or economic class. If the historical entry should be replaced by a different valid entry, that replacement must go through its own ordinary evidence/recognition/posting path after the erroneous entry is voided.

## No current-period P&L distortion

A prior-period accounting error is not a new current-period economic loss or gain. The exact-void entry therefore uses:

```
FlowType.INTERNAL
current_period_pnl_treatment = EXCLUDED_FROM_CURRENT_PERIOD_PNL
restatement_required = YES
```

Its balance-sheet consequences are real and immediately affect current NAV, but `realized_external_pnl_since()` does not classify the correction as current-period P&L.

Example: an erroneous prior-period revenue entry was:

```
Dr cash                    125
    Cr revenue             118
    Cr tax liability         5
    Cr refund reserve        2
```

Exact-entry void in a later period:

```
Dr revenue                 118
Dr tax liability             5
Dr refund reserve            2
    Cr cash                125
```

If all original components remain directly reversible, current HardNAV changes by the required correction amount while current-period realized P&L remains zero.

A separate `restated.period-view` generation will be responsible for presenting the affected historical period as restated. That presentation must not mutate the original PeriodClose.

## Fail-closed cases

V1 refuses exact void when:

- the original LedgerEvent is not proven inside the original AccountingClose;
- immutable PeriodClose ancestry to the target period is not proven;
- target accounting policy / requirement-registry binding differs from the authorization;
- the original entry has already been consumed by a real `REVENUE_REVERSAL` or `REVENUE_POST_CLOSE_ADJUSTMENT`;
- a prior `PRIOR_PERIOD_ENTRY_VOID` already exists;
- a current account balance is no longer sufficient to apply the exact opposite side safely.

The last rule is important. If, for example, the original tax liability was already remitted, V1 does not invent a tax receivable or expense. That is a more complex correction allocation and belongs to a later generation.

## Authority

- correction decision: `HUMAN_COMMITTEE` or `MULTISIG_GOVERNANCE`;
- AI authority: `NONE`;
- posting authority is separate;
- the posting path re-verifies the original closed-period proof and period ancestry immediately before ledger mutation;
- historical closes remain immutable.
