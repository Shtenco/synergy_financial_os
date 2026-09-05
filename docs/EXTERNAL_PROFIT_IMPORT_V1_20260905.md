# Financial OS External Profit Import v1

Date: 2026-09-05
Status: additive R&D/accounting integration candidate; not merged; not production-authorized.

## Purpose

MetaPay and DEX Finance can discover and settle profitable routes, but they do not own canonical accounting. This generation adds a fail-closed Financial OS importer for evidence already classified by the MetaPay External Profit Bus.

The importer accepts the economic classification as input, then independently checks the posting boundary again.

## Postable class

Only this source classification can become an automatic posting candidate:

```text
REALIZED_EXTERNAL_PNL
```

and only when:

- `canonical_external_pnl > 0`;
- source decision explicitly says `admissible_for_financial_os_pnl=true`;
- canonical P&L does not exceed the externally settled cash delta;
- evidence digest is hex64;
- route digest is hex64;
- provider/venue references are retained;
- settlement asset equals the ReportingLedger reporting currency in v1;
- target cash account is an `EXTERNAL ASSET`;
- target P&L account is an `EXTERNAL REVENUE` account.

Posting is:

```text
Dr external cash                         canonical_external_pnl
Cr realized external arbitrage revenue canonical_external_pnl
```

with `FlowType.EXTERNAL_REVENUE` and the external evidence digest bound to the append-only ReportingEntry.

## Non-posting classes

`EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION`
: Real cash may exist, but Financial OS must first determine whether it is revenue, equity/capital, liability or another class. It is not imported as arbitrage profit.

`CAPITAL_REALLOCATION_PNL_ZERO`
: Moving owned external capital between bank/CEX/DEX/bridge inventory does not create system P&L.

`INTERNAL_MARK_NOT_EXTERNAL_VALUE`
: Mint, QE and internal mark changes do not create external P&L.

`NOT_REALIZED`
: Quote/simulation/opportunity evidence is not settlement.

`NON_POSITIVE_EXTERNAL_PNL`
: No positive P&L exists to post.

`INADMISSIBLE`
: Fail closed.

## USD is not USDT

V1 deliberately refuses direct posting if the settlement asset differs from the ReportingLedger reporting currency. A future cross-currency generation must bind an explicit FX/valuation artifact. Therefore a USD settlement cannot silently be posted into a USDT ledger, or vice versa.

## Internal values remain provenance only

The amount posted comes only from `canonical_external_pnl`. Metadata may preserve internal mint quantity, internal revaluation or DEX/QE provenance, but those fields never alter the amount.

## Authority

The importer performs deterministic validation and explicit ledger posting only when called. It grants no trading, payment, signing, capital-allocation, blockchain-submission or autonomous accounting authority to AI/NEXUS. Merge authority remains `HUMAN_MAINTAINER_ONLY`.
