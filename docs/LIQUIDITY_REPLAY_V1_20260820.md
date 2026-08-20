# Liquidity Replay v1

This generation deliberately separates three facts that were previously supplied to FinancialSnapshot as already-combined `LiquidityHorizonState` values.

## 1. `liquidity.resources/v1`

Measures available reporting-currency resources at 1, 4 and 8 weeks for one exact `accounting.statement-replay/v1`.

Rules:
- exact StatementReplay digest binding;
- exact account-registry and valuation-policy digest binding;
- one liquidity-policy digest;
- one evidence digest per horizon;
- 1w <= 4w <= 8w resources;
- each resource amount <= restated liquid haircut assets.

NAV alone is not used as a substitute for horizon-specific availability.

## 2. `maturity.translation/v1`

Binds one exact `maturity.snapshot/v1` digest to one reporting-currency translation.

Rules:
- same-currency translation = exactly 1;
- cross-currency translation requires evidence digest;
- translation carries an explicit as-of time;
- v1 liquidity replay requires maturity/translation as-of equal to the original FinancialSnapshot as-of.

## 3. `liquidity.replay/v1`

The replay independently verifies every maturity snapshot and then requires the supplied maturity digest set to equal the original `FinancialSnapshot.maturity_snapshot_refs` set exactly.

For each horizon:

`expected_net_outflows = sum(translated callable + cumulative non-callable maturity outflows)`

`LCR = evidenced liquid resources / expected net outflows`

`liquidity surplus = evidenced liquid resources - expected net outflows`

The field values are recomputed by the runtime verifier. Recalculating an outer JSON digest cannot legalize a false LCR.

## Authority

Liquidity replay is reference-only.

It does not:
- mutate the ReportingLedger;
- recognize profit;
- authorize distributions;
- execute payments;
- introduce unreferenced maturity snapshots retrospectively.

A later restated-snapshot/distribution layer may consume this artifact together with StatementReplay, but must preserve separate policy and authorization gates.
