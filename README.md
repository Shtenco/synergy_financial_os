# SYNERGY Financial OS — RUBC/RUBX AI-CB EVM V2.2

Research implementation of an inflation-neutral triangular settlement engine around:

- `RUBC/USDC`
- `RUBX/USDC`
- `RUBC/RUBX`

Two profit directions are optimized independently: `USDC -> RUBX -> RUBC -> USDC` and `USDC -> RUBC -> RUBX -> USDC`.

## Two separate atomic primitives

`execute()` is the profit primitive. It may accept a cycle only when a real external USDC surplus remains after flash repayment/costs. Self-emission is never credited as profit.

`resetGradientNeutral()` is the accounting-neutral gradient primitive. It is allowed only for a 100%-protocol-owned RUBC/RUBX cross-pool and performs `REMOVE100 -> temporary mint -> ADD100(principal+gradient) -> REMOVE100 -> ADD100(exact principal) -> burn 100% temporary mint`. It must restore cross reserves, LP ownership and RUBC/RUBX supply exactly.

## V2.2 strict asset ledger

Every RUBC/RUBX unit used to pair USDC in ADDLP comes from tracked pre-existing protocol inventory. Every cycle reconciles public-pool reserves, cross-pool reserves, protocol free inventory, external holdings and fixed total supplies.

Conservative HardTVL counts only protocol-owned canonical USDC: treasury USDC plus the protocol's proportional USDC claim inside RUBC/USDC and RUBX/USDC. RUBC/RUBX self-marks are excluded.

Strict 5000-cycle result, seed 42 with independent order flow:

- accepted: `2804 / 5000` (`56.08%`)
- HardTVL: `1000 -> 33299.853639 USDC`
- cumulative consolidated accepted-trade PnL: `+31997.099470 USDC`
- treasury: `7436.002392 USDC`
- protocol-owned LP hard-USDC leg: `25863.851247 USDC`
- RUBC supply delta: `0`
- RUBX supply delta: `0`
- end-of-cycle flash debt: `0`
- asset conservation: `PASS`

The 5000-cycle `order flow = 0` falsification control accepts `0` cycles and leaves HardTVL exactly `1000 USDC`.

## Quotes / Base fork path

- deterministic exact CPMM integer quote path: `src/TriangleMath.sol`;
- Base Uniswap V3 QuoterV2 / SwapRouter02 adapter: `src/BaseV3Adapter.sol`;
- fork test performs an actual `100 USDC -> WETH -> USDC` QuoterV2 round-trip quote at fee tier 500.

Pinned Base integration:

- chain id `8453`
- USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- WETH `0x4200000000000000000000000000000000000006`
- QuoterV2 `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`
- SwapRouter02 `0x2626664c2603336E57B271c5C0b26F421741e481`
- WETH/USDC 0.05% pool `0xd0b53D9277642d899DF5C87A3966A349A798F224`

See `RESULTS.md`, `python/simulate_strict_v22.py`, and `results/strict_v22_summary.json`.
