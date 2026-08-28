# Valuation and consolidation boundary

## Why this is explicit

A canonical ledger can be perfectly balanced and still produce economically wrong NAV if account classification, consolidation perimeter or valuation policy is wrong. Therefore journal conservation and valuation are separate layers.

## Three valuation tiers

The preferred public hierarchy is:

```text
HardNAV <= LiquidNAV <= EconomicNAV
```

Conceptually:

- **Hard** — externally redeemable/enforceable assets admitted under the strictest policy;
- **Liquid** — assets eligible after liquidity/market/custody haircuts;
- **Economic** — broader eligible performing economic assets after risk/expected-loss haircuts.

A valuation class is mapped to three explicit factors rather than being counted implicitly.

Example policy shape:

```text
class                     hard  liquid  economic
BANK_CASH                 1.00  1.00    1.00
LIQUID_MARKET_ASSET       0.00  0.85    0.90
PERFORMING_CREDIT         0.00  0.00    0.75
OWN_ISSUED_INSTRUMENT     0.00  0.00    0.00
INTRA_GROUP_CLAIM         0.00  0.00    0.00  after consolidation
```

Numbers above are illustrative only, not a production policy.

## Accounting perimeter first

Every FinancialSnapshot declares its accounting perimeter. Before NAV calculation:

1. identify entities inside the perimeter;
2. identify reciprocal intra-group claims/liabilities;
3. eliminate them according to consolidation policy;
4. only then classify remaining external assets and liabilities.

A claim by one consolidated SINERGY entity on another consolidated SINERGY entity is not new external wealth merely because it appears as an asset in one legal entity's standalone accounts.

## Own-issued instruments

A system's own token, synthetic liability, own equity instrument or own consolidated sovereign-style claim cannot be counted as a hard asset of the same consolidated issuer merely because an internal or external market quotes a price.

It may still be relevant for:

- market analytics;
- collateral/liquidity operations under explicit rules;
- standalone legal-entity accounting;
- governance;
- ownership distribution.

But it is not external consolidated backing by itself.

## Price source hierarchy

A valuation rule records its price-source class. Suggested authority ordering for valuation inputs is context-specific but should distinguish at least:

```text
par / reconciled bank balance
externally audited NAV
executable market price
approved oracle
model estimate
none
```

A stale or non-executable quote must not silently receive the same authority as a reconciled balance.

## Valuation factors

For an eligible positive asset value `V` and factors `h`, `l`, `e`:

```text
0 <= h <= l <= e <= 1
HardValue     = V * h
LiquidValue   = V * l
EconomicValue = V * e
```

External liabilities are not haircut upward to manufacture coverage. Liability valuation policy must be conservative and separately documented where currency/contingency valuation is required.

## Revenue is not valuation gain by default

An unrealized market-value increase may increase an economic valuation under policy, but it is not automatically realized distributable profit. Distribution policy remains tied to the canonical HardNAV/capital-flow rule and realized external evidence requirements.

## Schema separation

- `chart-of-accounts/v1` defines account kind, consolidation class and valuation class;
- `valuation-policy/v1` defines current valuation factors and admissible price sources;
- `ledger.event/v1` records balanced events;
- `financial.snapshot/v1` records the resulting published state.

This separation is deliberate: changing a haircut or accounting perimeter must be visible as a policy/version change instead of silently changing journal history.
