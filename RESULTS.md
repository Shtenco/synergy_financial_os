# EVM V2 deterministic results — 2026-08-31

## Baseline: fresh outside order flow

Configuration: 5000 cycles, seed 42, two external CPMMs seeded 1,000,000 token / 1,000,000 USDC, protocol cross-pool 500,000 RUBC / 500,000 RUBX, external fee 30 bp, cross fee 5 bp, order-flow scale 3500 USDC, fixed execution reserve 0.05 USDC, zero flash fee baseline.

Result:

- accepted cycles: **2997 / 5000 = 59.94%**
- direction A `U->X->C->U`: **1491**
- direction B `U->C->X->U`: **1506**
- mean accepted trade: **1458.4377 USDC**
- mean accepted net profit: **12.5224 USDC**
- median accepted net profit: **5.1619 USDC**
- maximum single-cycle net profit: **544.3882 USDC**
- HardTVL: **1000 -> 38529.58973951109 USDC**
- external realized PnL: **+37529.58973951106 USDC**
- RUBC supply delta: **0**
- RUBX supply delta: **0**
- max end-of-cycle flash debt: **0**
- final solvency NAV: **38529.58973951114 USDC**

The REMOVE100->ADD100 path is exercised only as a 100%-protocol-owned cross-pool state-reconfiguration invariant. It restores exact pre-cycle cross reserves and burns the temporary mint; it is not credited as PnL.

## Control: no fresh outside order flow

5000-cycle control with order-flow scale 0:

- accepted cycles: **0**
- HardTVL: **1000 -> 1000 USDC**
- external PnL: **0**
- RUBC/RUBX supply unchanged

This rejects the false claim that temporary emission, flash liquidity or LP reconfiguration alone creates dollar wealth. Persistent compounding requires an external source of value/dislocation.

## Fork status

The package contains a Base mainnet fork test that verifies code at Uniswap V3 QuoterV2, SwapRouter02 and the Base WETH/USDC 0.05% pool. This execution environment has no outbound Base RPC / Foundry installation, so that fork test is included but not claimed as executed here.
