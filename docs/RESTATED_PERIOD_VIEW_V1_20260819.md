# Immutable restatement overlay / period view v1 — 2026-08-19

A historical `PeriodClose` is an immutable accounting fact. Discovering an accounting error later must never rewrite the old close, the old FinancialSnapshot or the old ledger event.

This generation therefore separates three facts:

1. the historical bytes that actually existed;
2. the later evidence-bound exact-entry correction posted into a current period;
3. the presentation treatment that tells a comparative-reporting engine which proven erroneous historical entry must be excluded.

## `accounting.restatement-overlay/v1`

The overlay is built only after a completed `accounting.prior-period-correction-authorization/v1` exact-entry void has itself been posted, exported as `ledger.event/v2`, included in a later `accounting.close/v2`, and declared by the later `accounting.period-close/v1`.

The builder independently re-verifies:

- original immutable PeriodClose / AccountingClose / LedgerEvent / inclusion proof;
- PeriodClose ancestry into the correction period;
- correction authorization;
- correction PeriodClose and AccountingClose;
- correction LedgerEvent evidence binding;
- correction inclusion proof;
- exact opposite line multiset of original and correction events;
- `economic_class=PRIOR_PERIOD_ENTRY_VOID` and `restatement_required=YES`.

Its only v1 presentation action is:

```
EXCLUDE_ORIGINAL_ENTRY
```

It has no ledger mutation or execution authority.

## `accounting.restated-period-view/v1`

A view combines one or more independently proven restatement overlays for the same original PeriodClose.

It is append-only:

```
View v1
  overlays {A}
      ↓
View v2
  overlays {A,B}
      ↓
View v3
  overlays {A,B,C}
```

Every later view must be a strict superset of the previous overlay set and stores the previous view digest. An existing view is never edited to add a correction.

## Deliberate honesty about historical metrics

V1 contains:

```
recalculated_financial_metrics = NOT_PERFORMED
```

This is intentional.

`FinancialSnapshot v2` currently contains `account_registry_digest`, but a digest alone cannot reconstruct the actual account registry. Independent historical replay requires the content-addressed account specifications themselves, plus the frozen valuation policy and relevant ledger prefix.

Therefore v1 does **not** claim a recalculated HardNAV, P&L, LCR or distribution capacity. It proves only the treatment manifest: which historical ReportingEntry digests must be excluded by a later deterministic replay engine.

Producing plausible-looking numbers without reconstructible account classes, consolidation classes and valuation classes would weaken the audit model.

## Immutable-history invariant

For an affected Period N:

```
PeriodClose N                     unchanged
FinancialSnapshot N               unchanged
AccountingClose N                 unchanged
Original ReportingEntry           unchanged
Original LedgerEvent              unchanged
        │
        └── later exact-void correction evidence
                       │
                       ▼
             RestatementOverlay
                       │
                       ▼
             RestatedPeriodView
```

The view is a new presentation artifact, not a replacement ledger state.

## Next prerequisite for deterministic replay

The next safe generation should export a content-addressed `account.registry/v1` from the frozen ReportingLedger chart of accounts. A replay artifact can then prove:

```
account.registry/v1
+ valuation-policy/v1
+ historical LedgerEvent v2 prefix
+ RestatedPeriodView overlays
        ↓
restated statement replay
```

Until those inputs are reconstructible, historical financial metrics must remain `NOT_PERFORMED` in this presentation layer.
