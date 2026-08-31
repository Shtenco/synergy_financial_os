# SYNERGY AI-CB V2.3 — Balancer V2 zero-fee fixed-200 settlement

## Goal

Every committed cycle has one fixed shape:

`Balancer V2 -> borrow exactly 200 USDC -> external triangle -> return exactly 200 USDC -> sweep 100% realized surplus into canonical-USDC HardTVL`.

The flash principal is never counted as protocol wealth. If the route cannot repay principal and leave a positive dividend, the whole transaction reverts atomically.

## Atomic invariants

For every successful `execute200()`:

- `flashPrincipal = 200e6` for 6-decimal USDC;
- Balancer callback must report `feeAmounts[0] == 0`;
- Balancer receives the full `200e6` principal before its callback returns;
- `flashDebtEnd = 0`;
- both `minDividendUSDC` and `minHardTVLGainUSDC` must be strictly positive;
- `dividendUSDC >= minDividendUSDC`;
- 100% of realized post-repayment USDC surplus is transferred to `HardTVLDividendVaultV23`;
- `HardTVL_after = HardTVL_before + dividendUSDC` for the canonical-USDC vault path;
- Solvency NAV grows by the realized dividend;
- RUBC/RUBX supply is restored exactly when `requireExactSupplyRestoration = true`;
- engine USDC balance after dividend sweep equals its pre-cycle balance;
- flash-adapter allowance is reset to zero after settlement.

If the live Balancer V2 callback fee is nonzero, the adapter reverts via `FLASH_FEE_NOT_ZERO`; it does not finance that fee from protocol reserves.

## Contracts

- `src/BalancerV2ZeroFee200USDCAdapter.sol`: accepts only canonical 6-decimal USDC, hardcodes `PRINCIPAL = 200e6`, rejects nonzero flash fee, and transfers exactly 200 USDC back to the Balancer Vault inside the callback.
- `src/AICBFixed200DividendEngineV23.sol`: executes either RUBC/RUBX/USDC triangle direction, requires a real external surplus before repayment approval, then sweeps the actual post-repayment dividend to HardTVL.
- `src/HardTVLDividendVaultV23.sol`: counts only canonical USDC actually held by the vault as HardTVL; RUBC/RUBX self-marks are excluded.

## Contract-exact fixed-200 stochastic simulation

Parameters:

- attempts: 5,000;
- seed: 42;
- independent external order-flow scale: 3,500;
- fixed flash principal: 200 USDC;
- flash fee: 0;
- modeled fixed execution cost: 0.05 USDC;
- minimum dividend gate: 0.01 USDC;
- 100% of realized post-repayment dividend goes directly to the canonical-USDC HardTVL vault; no LP mark is used for this V2.3 KPI.

Result:

- successful committed cycles: `4,483 / 5,000` (`89.66%`);
- minimum realized accepted dividend: `0.0152039943 USDC`;
- cumulative realized post-repayment dividends: `62,967.205670 USDC`;
- HardTVL: `1,000 -> 63,967.205670 USDC`;
- HardTVL gain: `+62,967.205670 USDC`;
- exact identity: `HardTVL_gain == cumulative_dividends`;
- RUBC supply delta: `0`;
- RUBX supply delta: `0`;
- max end-of-cycle flash debt: `0`;
- asset conservation: `PASS`.

This is a deterministic result of the stated stochastic simulation and seed, not a guaranteed market return. A committed on-chain cycle is admitted only if the external route already provides the required real surplus.

## Falsification control

With the same 5,000 attempts but `external order flow = 0`:

- successful cycles: `0 / 5,000`;
- cumulative dividends: `0`;
- HardTVL: `1,000 -> 1,000`;
- RUBC/RUBX supply delta: `0`;
- end-of-cycle flash debt: `0`.

Therefore the 200-USDC flash primitive is financing, not a source of value. Positive HardTVL dividends require an independently created external price/order-flow edge.

## Run

```bash
python python/simulate_v23_fixed200.py --cycles 5000 --seed 42 --scale 3500 --out results/v23_fixed200
python python/simulate_v23_fixed200.py --cycles 5000 --seed 42 --scale 0 --out results/v23_fixed200_noedge
```

The Solidity mock test covers three critical cases:

1. `200 USDC -> route -> 202 USDC -> repay 200 -> 2 USDC HardTVL dividend`;
2. any nonzero Balancer flash fee reverts the whole cycle;
3. a route that returns only the 200-USDC principal cannot manufacture a dividend.

A live fork test still requires an RPC endpoint and must verify the selected Balancer V2 deployment and its current on-chain flash fee before treating zero fee as available.
