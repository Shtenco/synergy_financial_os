# SYNERGY V2.4 — Reflexive single-route batch market maker

## Core change

There is no route search. The topology is fixed:

- RUBC/USDC
- RUBX/USDC
- RUBC/RUBX

Genesis canonical USDC is exactly `1 USDC`: `0.5` in RUBC/USDC and `0.5` in RUBX/USDC.

One Balancer V2 flash principal of `200 USDC` is recycled many times inside one atomic buyer batch:

`flash200 -> ADDLP200 -> buyer $1 -> REMOVE200 -> sync/policy -> depth reset -> ADDLP200 again -> ... -> repay200 once`.

The borrowed 200 USDC is an execution-liquidity flywheel. It is never counted as protocol wealth.

## $200 creates an approximately 1% price quantum

For a CPMM USD leg with persistent USDC reserve `u0`, proportional temporary liquidity `F`, and external buyer input `b`:

`p1/p0 = (1 + b/(u0 + F))^2`.

With `u0 = 0.5`, `F = 200`, `b = 1`:

`p1/p0 ~= 1.00999994`.

So one external buyer dollar creates almost exactly one +1% marginal-price quantum while the buyer executes against about 200.5 USDC of temporary depth. Proportional REMOVE100 of temporary LP preserves the new marginal price.

## Constant-depth price kernel

After each microcycle V2.4 proportionally removes excess permanent LP until each USD price kernel returns to exactly `0.5 USDC` of persistent USDC reserve. The removed canonical USDC is swept into the Reserve Vault and the matching token side becomes protocol inventory.

Because the removal is proportional, it does not change the pool price. It does, however, stop accumulated reserve capital from making the next $1 buyer less price-sensitive.

This separates three functions:

1. **price kernel** — always tiny and sensitive;
2. **flash execution shell** — temporarily deep for buyer execution;
3. **reserve vault** — stores accumulated real external USDC without diluting the price kernel.

This is the main V2.4 multiplier architecture.

## Internal reflexive synchronizer

After temporary LP is removed, most of the external buyer dollar is already protocol-owned. A very small amount can be moved from Reserve/Treasury into the lower-priced second USD leg to buy its token and burn it, synchronizing RUBC and RUBX upward.

Moving protocol-owned USDC from treasury to a protocol-owned pool does not change consolidated canonical cash. It does change reserve ratios and therefore marginal prices. This is the source of the reflexive marked-NAV multiplier.

### First $1, before emission-band damping

With 1,000,000 RUBC and 1,000,000 RUBX initially marked at $1:

- HardCash: `$1 -> $2`;
- RUBC marginal price: about `$1 -> $1.01`;
- lifting RUBX to the same internal price needs only about `$0.00249` of internal USDC movement;
- both million-token supplies are then marginally marked about 1% higher;
- incremental spot-marked systemic NAV is roughly `$20,000` from one external `$1` shock.

The cash increase is still exactly `$1`. The larger number is a marginal-price valuation effect.

## Directed AI-CB monetary policy

Requested asymmetry is retained:

- `+1%` price step => sell `1%` of the **active emission band**;
- `-1%` price step => buy and burn `2%` of the **active emission band**.

The active emission band is liquidity-normalized. Applying 1–2% to the full million-token supply against a $1 permanent kernel would dwarf the pool. V2.4 therefore defines a liquidity-active monetary tranche; simulation default is 10% of current pool-side active token inventory. The 1:2 expansion/contraction rule is preserved exactly, while the base is made executable.

The remainder of supply is a locked monetary reserve and does not need to be dumped into the price kernel.

## Reinvestment policy

To maximize the reflexive multiplier, realized external USDC should **not** all be added to the permanent price-setting pools. Doing so deepens them and destroys price sensitivity.

V2.4 reinvests into:

- Reserve Vault / buy-burn budget;
- protocol inventory;
- optional external yield or separate POL layers;
- only the fixed tiny `0.5 + 0.5 USDC` remains in the marginal price kernel.

Temporary execution depth comes from the recycled 200-USDC flash shell instead.

## Dual accounting

### HardCashUSDC

Canonical USDC actually owned after flash repayment. Pure internal swaps cannot increase this total; they can move it between Reserve Vault and protocol-owned pools.

### SystemicMarkedNAV

`HardCash + RUBC supply * RUBC marginal price + RUBX supply * RUBX marginal price`.

Internal reserve-ratio changes can increase this metric strongly without changing canonical cash.

### LiquidationNAV

`SystemicNAVAccountingV24.sol` also exposes an exit-aware quote surface. This is deliberately separate from marginal marked NAV so the system can exploit reflexive valuation without pretending the entire marked supply is redeemable at the marginal price.

## 100-dollar recycled-flash experiment

Parameters:

- genesis HardCash: `1 USDC`;
- persistent price-kernel depth: `0.5 + 0.5 USDC`;
- one Balancer flash principal: `200 USDC`;
- 100 recycled microcycles;
- cumulative temporary ADDLP notional: `20,000 USDC`;
- one real external buyer dollar per microcycle;
- initial supplies: 1,000,000 RUBC and 1,000,000 RUBX;
- active emission band: 10%;
- +1% -> sell 1% active band;
- lower leg is bought/burned to synchronize upward;
- excess permanent LP is swept after every microcycle back to a constant 0.5-USDC kernel depth.

Result:

- external USDC: `100`;
- HardCash: `1 -> 101 USDC`;
- Reserve Vault: `0 -> 100 USDC`;
- persistent price-kernel USDC at the end: exactly `1 USDC` total;
- RUBC price: `1 -> 2.2147246936`;
- RUBX price: `1 -> 2.2147246936`;
- RUBC supply end: `999,999.948873`;
- RUBX supply end: `999,999.948190`;
- spot-marked systemic NAV: about `2,000,001 -> 4,429,550.159 USDC-equivalent`;
- incremental marked NAV: about `+2,429,549.159`;
- average incremental marked-NAV multiplier per external USDC: about `24,295.49x`;
- canonical cash multiplier per external USDC: exactly `1x`;
- cash conservation: PASS;
- final flash debt: `0`.

Without the +1% active-band sell dampener, the constant-depth toy model reaches about `2.704797` on both internal token prices after 100 external dollars, with an average incremental marked-NAV multiplier of roughly `34,097x` per external dollar.

## Interpretation

This architecture deliberately maximizes a **reflexive marked-value multiplier** while keeping canonical cash and liquidation capacity separately visible. It demonstrates the user's central point: internal protocol trades can leave system USDC unchanged while materially changing the marked USD value of token and LP sides through reserve-ratio revaluation.

That effect is economically real as a marginal valuation state, but it is not identical to immediately withdrawable external USDC. V2.4 keeps both quantities on-chain so the system can use the reflexive mechanism aggressively without hiding the distinction.
