# Post-close revenue adjustment v1 — 2026-08-19

This layer is additive above `revenue.reversal-authorization/v1`. The FULL_ONLY reversal path remains unchanged and remains the simplest path when the complete original revenue posting is still directly reversible in the immediately succeeding period.

`revenue.adjustment-authorization/v1` exists for a different class of facts: a real post-close refund or chargeback that may arrive several immutable reporting periods later and whose accounting components are no longer a mirror image of the original entry.

## Period ancestry first

A late adjustment may not identify an old sale by free-form metadata alone. `accounting.period-chain-proof/v1` binds an ordered, cycle-free chain of immutable `accounting.period-close/v1` digests from the original closed period through the opening close of the target period.

The proof is provenance-only. It cannot post entries or reopen a prior close. The authorization binds the proof digest, and the proof must have existed no later than the authorization decision time.

## Explicit allocation; no guessed accounting

The authorization records a customer refund and requires the following identity:

```
customer_refund_amount
=
revenue_reduction_amount
+ refund_reserve_release_amount
+ tax_adjustment_amount
```

Any processor/chargeback fee is separate:

```
total_cash_outflow_amount
=
customer_refund_amount
+ external_fee_expense_amount
```

Tax treatment is explicit and evidence-bound:

- `LIABILITY_RELEASE` — the original tax liability still exists and is debited;
- `RECOVERABLE_RECEIVABLE` — tax has already been remitted or otherwise requires a recoverable external tax asset; separate tax evidence is mandatory;
- `NONRECOVERABLE_EXPENSE` — the tax component is an external period expense; separate tax evidence is mandatory;
- `NONE` — tax adjustment must be exactly zero and no tax evidence may be supplied.

An external processor/chargeback fee requires independent fee evidence.

## Cumulative ceiling

Multiple partial adjustments are allowed, but the canonical posting path scans the immutable ReportingLedger and aggregates all prior `REVENUE_POST_CLOSE_ADJUSTMENT` entries bound to the same original ReportingEntry.

Cumulative amounts may never exceed the original recognition components:

```
Σ revenue reduction <= original recognized revenue
Σ refund-reserve release <= original refund reserve
Σ tax adjustment <= original tax component
Σ customer refunds <= original gross settlement
```

If a prior `REVENUE_REVERSAL` exists for the same original ReportingEntry, the partial-adjustment path is closed entirely.

This prevents two independent authorizations from consuming the same original economics twice.

## Canonical example

Original recognized posting in Period N:

```
Dr cash                    125
    Cr revenue             118
    Cr tax liability         5
    Cr refund reserve        2
```

In Period N+1 the tax liability is remitted:

```
Dr tax liability             5
    Cr cash                   5
```

In Period N+2 an externally evidenced chargeback refunds 30 to the customer and incurs a separate processor fee of 1. The authorized allocation is:

```
revenue reduction           27
refund reserve release       1
tax recoverable receivable   2
processor fee expense        1
cash outflow                31
```

Posting:

```
Dr revenue                  27
Dr refund reserve            1
Dr tax recoverable           2
Dr processor fee expense     1
    Cr cash                 31
```

The target-period realized P&L effect is `-28`, not `-31`:

- 27 is a reduction of previously recognized revenue;
- 1 is a new external processor expense;
- 1 consumes an already-existing refund-reserve liability;
- 2 becomes a recoverable tax asset rather than current-period expense.

The example deliberately demonstrates why a late refund cannot be handled by blindly negating the original journal entry.

## Authority boundary

- decision authority: `HUMAN_COMMITTEE` or `MULTISIG_GOVERNANCE`;
- AI authority: `NONE`;
- authorization cannot post the ledger itself;
- canonical posting re-verifies original recognition, LedgerEvent v2, inclusion proof, original AccountingClose, immutable PeriodClose ancestry, target policy/requirement-registry bindings and cumulative utilization immediately before mutation.

## Deliberately unsupported in v1

V1 does **not** guess or automate:

- correction of an accounting error with no new external economic event;
- prior-period restatement;
- non-cash store credit or replacement goods;
- multi-currency refund translation;
- jurisdiction-specific tax recovery rules beyond the explicitly selected treatment and evidence;
- allocation after the original recognized components are already fully consumed;
- reopening or mutation of any historical PeriodClose.

Those are separate accounting-policy problems. In particular, error correction/restatement belongs to a different generation and must not be disguised as a customer refund.
