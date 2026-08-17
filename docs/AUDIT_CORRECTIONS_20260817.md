# SINERGY federation audit corrections — 2026-08-17

Status: **canonical-root correction record**. Historical source repositories and old research formulas are not rewritten or deleted. This document records why the new federation root intentionally differs from some earlier drafts.

## Correction 1 — HardNAV movement is not distributable profit

### Historical simplification

An earlier research rule used:

```text
max(0, HardNAV_t - HardNAV_(t-1) - NetNewCapital_t)
```

as a distributable-profit proxy.

### Counterexample

Suppose the system owns a performing credit asset of 40 reporting units. The valuation policy admits it to EconomicNAV but not HardNAV. Borrower principal is then repaid:

```text
Dr cash              40
Cr performing credit 40
```

No revenue exists. Nevertheless hard assets rise by 40 because an economic asset became hard cash.

Therefore:

```text
principal repayment -> HardNAV can rise
principal repayment -> realized P&L = 0
```

The same issue applies to other asset-tier migrations and liquidity hardening.

### Canonical correction

The old expression survives only as a diagnostic:

```text
HardNAVSurplusAfterCapital =
HardNAV_t - HardNAV_(t-1) - NetNewCapital_t
```

Realized external P&L is derived from explicit externally evidenced revenue/expense/loss accounts and allowed flow classes.

```text
ProfitBudget = max(
  0,
  RealizedExternalPnL
  - RequiredRetention
  - LossCarryforward
)
```

Final distribution is additionally solvency bounded:

```text
DistributionCapacity = min(
  ProfitBudget,
  max(0, HardNAV - RequiredHardNAVBuffer)
)
```

Implemented in:

- `sinergy_financial_os/core.py`;
- `sinergy_financial_os/reporting.py`;
- `sinergy_financial_os/reporting_metrics.py`;
- `sinergy_financial_os/snapshot.py`.

Regression evidence is encoded in:

- `tests/test_reporting_metrics.py`;
- `tests/test_reporting_semantics.py`;
- `tests/test_snapshot_v2.py`.

## Correction 2 — principal and interest must be separate accounting flows

One external borrower payment may contain principal and interest. That does not mean they share one accounting meaning.

Rejected entry shape:

```text
flow_type = CREDIT_REPAYMENT
Dr cash        45
Cr loan        40
Cr revenue      5
```

Canonical representation uses two entries bound to the same external evidence digest:

```text
CREDIT_REPAYMENT
Dr cash 40
Cr loan 40

EXTERNAL_REVENUE
Dr cash     5
Cr revenue  5
```

This makes it impossible for a principal/notional flow to hide revenue or loss lines.

## Correction 3 — callable savings must not be counted twice in LCR outflows

An early `MaturitySnapshot` exposed both:

```text
immediately_callable_principal
scheduled_unlock / cumulative_unlock
```

but the contractual schedule also contained callable tranches. A naive Financial OS adapter could therefore calculate:

```text
callable now + callable again at contractual maturity
```

and double-count the same liability.

### Canonical correction

`maturity.snapshot/v1` now preserves two schedules:

```text
scheduled_unlock / cumulative_unlock
    -> complete contractual audit schedule

scheduled_noncallable_unlock / cumulative_noncallable_unlock
    -> future maturity outflow excluding balances already callable now
```

Financial OS contractual horizon outflow is:

```text
immediately_callable_principal
+ cumulative_noncallable_unlock(horizon)
```

The central maturity bridge verifies the Matrix snapshot SHA-256 digest before using it and requires explicit FX translation evidence for foreign-currency liabilities.

Implemented in:

- `Shtenco/synergy_matrix_sota` `MaturityBook.scheduled_noncallable_unlocks()`;
- `Shtenco/synergy_matrix_sota` maturity snapshot exporter;
- central `schemas/maturity_snapshot_v1.schema.json`;
- central `sinergy_financial_os/maturity_bridge.py`.

## Correction 4 — a settlement fee needs an economic role before it can affect P&L

A field called `fee` is economically ambiguous. It may represent:

- revenue charged by SINERGY;
- provider cost;
- network/gas cost;
- tax;
- an uncategorized amount requiring manual/accounting review.

Therefore `settlement.receipt/v1` fee components now require:

```text
economic_role =
  PROTOCOL_REVENUE
  PROVIDER_COST
  NETWORK_COST
  TAX
  OTHER
```

The MetaPay exporter does not derive realized fees from quote estimates. It exports only fee components explicitly supplied by the settlement/reconciliation layer.

## Correction 5 — native operational accounting and reporting-currency accounting are different layers

`synergy_pay_system` correctly balances native assets separately. The canonical consolidated financial statement ledger must instead use one declared reporting currency after approved translation/valuation.

Canonical sequence:

```text
native event / receipt
 -> per-asset conservation
 -> approved translation + evidence
 -> reporting-currency journal
 -> NAV / P&L / liquidity / distribution policy
```

Never nominally add KZT + USD + CNY.

## Correction 6 — valuation policy itself is part of snapshot evidence

A ledger digest alone cannot reproduce NAV if haircut/source rules can change.

`FinancialSnapshot v2` therefore binds:

```text
ledger_digest
ledger_last_entry_digest
account_registry_digest
valuation_policy_id
valuation_policy_digest
valuation_policy_as_of
```

Changing a haircut, price-source class or policy vintage changes the valuation-policy digest and therefore changes the published snapshot evidence.

## Historical preservation rule

None of these corrections authorizes deletion of the historical mechanism that exposed the problem. The old source remains provenance. New canonical code records the corrected interpretation side-by-side and adds regression tests that prevent silent reintroduction.
