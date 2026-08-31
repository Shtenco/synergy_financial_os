# SYNERGY Financial OS — EVM V2

RUBC / RUBX / AI Central Bank research implementation for inflation-neutral triangular settlement.

## Markets

- `RUBC/USDC`
- `RUBX/USDC`
- `RUBC/RUBX`

Two optimized triangle directions:

- A: `USDC -> RUBX -> RUBC -> USDC`
- B: `USDC -> RUBC -> RUBX -> USDC`

`HardTVL` counts only protocol-owned canonical USDC equity. RUBC/RUBX self-marks do not create HardTVL. Flash debt must end at zero.

## Two deliberately separate primitives

### 1. Profit route

`execute()` uses flash USDC, executes one of the two triangle directions and accepts settlement only when a real external USDC surplus remains after flash repayment/costs. No self-emission is credited as profit.

### 2. REMOVE100 -> ADD100 gradient reset

`resetGradientNeutral()` is allowed only when the RUBC/RUBX cross-pool is `100%` protocol-owned. It performs:

`REMOVE100 -> temporary mint -> ADD100(principal+gradient) -> REMOVE100 -> ADD100(exact principal) -> burn 100% temporary mint`.

The call succeeds only if cross reserves, LP ownership and RUBC/RUBX supplies are restored exactly. Public RUBC/USDC and RUBX/USDC LP is never touched by this mode.

The separation is intentional: trying to force exact reserve restoration and a one-way cross-pool arbitrage into the same primitive creates a self-contradictory reserve condition. V2 therefore refuses to count gradient geometry as PnL.

## Quotes

- deterministic exact CPMM integer quote path: `src/TriangleMath.sol`;
- Base Uniswap V3 exact on-chain quotes through deployed `QuoterV2` and execution through `SwapRouter02`: `src/BaseV3Adapter.sol`.

Pinned Base integration:

- chain id `8453`
- USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- WETH `0x4200000000000000000000000000000000000006`
- QuoterV2 `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`
- SwapRouter02 `0x2626664c2603336E57B271c5C0b26F421741e481`
- WETH/USDC 0.05% pool `0xd0b53D9277642d899DF5C87A3966A349A798F224`

## 5000-cycle deterministic result

Baseline seed 42 with fresh independent order flow:

- accepted cycles: `2997 / 5000` (`59.94%`)
- direction A: `1491`
- direction B: `1506`
- HardTVL: `1000 -> 38529.58973951109 USDC`
- cumulative external PnL: `+37529.58973951106 USDC`
- RUBC supply: `1,000,000 -> 1,000,000`
- RUBX supply: `1,000,000 -> 1,000,000`
- max end-of-cycle flash debt: `0`
- final solvency NAV: `38529.58973951114 USDC`

No-order-flow control, also 5000 cycles:

- accepted cycles: `0`
- HardTVL remains exactly `1000 USDC`
- external PnL: `0`

Therefore temporary emission, flash liquidity and LP reconfiguration do not create dollar value by themselves. Persistent compounding requires fresh external order flow, fees, yield, or another independent external-value source.

See `RESULTS.md` for the exact interpretation and fork status.
