# SYNERGY EVM V2.2 STRICT LEDGER — results 2026-08-31

## What V2.2 proves

The strict model closes the accounting perimeter around every asset used by the engine. RUBC/RUBX used for ADDLP must come from explicit protocol inventory; no matching token can appear from nowhere. Public-pool reserves, the 100%-protocol RUBC/RUBX cross-pool, protocol free inventory, external holder inventory and total supply are reconciled every cycle.

HardTVL is deliberately conservative:

`HardTVL = protocol treasury USDC + protocol proportional USDC claim in RUBC/USDC + protocol proportional USDC claim in RUBX/USDC`.

RUBC/RUBX self-marks are excluded. Temporary gradient mint is intracycle debt and is burned 100% before the cycle closes. End-of-cycle flash debt must equal zero.

## 5000-cycle strict run

Seed 42. Fresh independent outside order flow scale 3500 USDC. External pool fee 30 bp. Cross fee 5 bp. Fixed execution reserve 0.05 USDC. Zero flash-fee baseline. Both triangle directions optimized each cycle.

- accepted: **2804 / 5000 = 56.08%**
- HardTVL: **1000.000000 -> 33299.853639 USDC**
- HardTVL gain: **+32299.853639 USDC**
- cumulative consolidated accepted-trade PnL: **+31997.099470 USDC**
- additional net HardTVL change through protocol-owned LP exposure to later outside flow: **+302.754169 USDC**
- treasury end: **7436.002392 USDC**
- protocol-owned LP USDC leg: **25863.851247 USDC**
- protocol share RUBC/USDC LP: **1.099054%**
- protocol share RUBX/USDC LP: **1.053555%**
- protocol free RUBC remaining: **1,990,011.897771**
- protocol free RUBX remaining: **1,990,857.821065**
- RUBC total-supply delta: **0**
- RUBX total-supply delta: **0**
- maximum end-of-cycle flash debt: **0**
- final Solvency NAV: **33299.853639 USDC**
- full asset conservation: **PASS**

The `+302.754169 USDC` difference is not mint profit. It is the net change of the protocol's USDC claim inside POL after subsequent independent outside trades. It contains fee capture and inventory-direction effects, so it is not a guaranteed yield.

## 5000-cycle no-order-flow control

With the same initial state and `outside order flow = 0`:

- accepted: **0 / 5000**
- HardTVL: **1000 -> 1000 USDC**
- cumulative PnL: **0**
- RUBC/RUBX total-supply delta: **0**
- end-of-cycle flash debt: **0**
- asset conservation: **PASS**

This is the central falsification test: temporary emission, flash liquidity and REMOVE100->ADD100 geometry do not create canonical dollars by themselves.

## REMOVE100 -> ADD100

V2.2 keeps gradient reconfiguration separate from profit accounting. `resetGradientNeutral()` is permitted only for a 100%-protocol-owned RUBC/RUBX cross-pool and must end with exact original reserves, exact protocol ownership and exact pre-cycle RUBC/RUBX total supplies. Public RUBC/USDC and RUBX/USDC LP is never removed by this primitive.

## Base / Uniswap V3 fork path

`BaseV3Adapter.sol` uses deployed Base Uniswap V3 QuoterV2 and SwapRouter02. `BaseForkQuote.t.sol` performs an actual fork quote `100 USDC -> WETH -> USDC` on the 0.05% WETH/USDC pool and requires the round trip to return less than 100 USDC because of fees/slippage.

This container has no outbound Base RPC and no Foundry/solc installation. Therefore the Base fork test is included but **not claimed as executed here**. Python economic simulations, Python compile checks, strict conservation assertions and Solidity structural checks are local PASS; that is not a substitute for compiler/fork/security verification.
