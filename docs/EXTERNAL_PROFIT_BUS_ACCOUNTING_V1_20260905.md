# Financial OS — External Profit Bus Accounting v1

Date: 2026-09-05
Status: additive candidate; not canonical; not production-authorized.

## Purpose

This is the accounting boundary that completes the SYNERGY convergence:

```text
Classic Finance / bank / PAY API / P2P / CEX
                    │
                  MetaPay
                    │
        Classic / hybrid arbitrage
                    │
DEX / bridge / flash / QE opportunity surface
                    │
          External Profit Bus
                    │
                    ▼
              Financial OS
```

MetaPay and DEX components may report settlement evidence and propose an economic classification. Financial OS independently rechecks the minimum external-value invariants and decides whether a realized-P&L posting is admissible.

## Realized arbitrage/routing P&L

Only `REALIZED_EXTERNAL_PNL` can produce the accounting instruction:

```text
Dr  EXTERNAL_ASSET_CASH_OR_SETTLEMENT
Cr  REALIZED_EXTERNAL_TRADING_OR_ROUTING_INCOME
```

for exactly `canonical_external_pnl`.

The consumer requires:

- an eligible Classic/DEX/hybrid source;
- positive canonical external P&L;
- real external settlement;
- independent external counterparty/market evidence;
- flash principal repaid when used;
- provider/venue references;
- route/evidence digest;
- recognized P&L not greater than the observed external cash delta.

## Internal mint/revaluation

`internal_mint_quantity` and `internal_mark_delta` may be included for provenance. They are ignored when determining the recognized amount.

An `INTERNAL_MARK_NOT_EXTERNAL_VALUE` classification must carry `canonical_external_pnl = 0` or the import is rejected.

## Capital reallocation

Moving owned capital from a bank/provider balance into DEX reserves can require balance-sheet transfer accounting elsewhere, but it creates no realized P&L in this importer.

`CAPITAL_REALLOCATION_PNL_ZERO -> NO_PNL_POSTING`.

This is the formal boundary behind:

> DEX HardTVL can rise while system-wide HardNAV stays unchanged.

## Issuance proceeds

An external cash inflow from issuance/sale of an internally created token can be real cash but is not automatically arbitrage/trading revenue.

`EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION` produces no automatic posting. A human/accounting policy must classify the inflow as revenue, liability, equity/capital or another valid class.

## Failure modes

No P&L is recognized from:

- stale/quote-only opportunities;
- internal mint/burn/revaluation;
- non-positive routes;
- unrepaid flash principal;
- missing settlement evidence;
- missing external counterparty evidence;
- synthetic/reference FX without an executable edge;
- movement of protocol-owned reserves.

## Authority

This module prepares an accounting decision only. It does not authorize payments, trades, signing, chain submission, capital allocation or production deployment. Canonical promotion and merge remain `HUMAN_MAINTAINER_ONLY`.
