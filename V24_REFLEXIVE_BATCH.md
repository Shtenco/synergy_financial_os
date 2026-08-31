# SYNERGY V2.4 — Reflexive single-route batch market maker

## Core change

There is no route search. The topology is fixed:

- RUBC/USDC
- RUBX/USDC
- RUBC/RUBX

Genesis canonical USDC is exactly `1 USDC`: `0.5` in RUBC/USDC and `0.5` in RUBX/USDC.

A single Balancer V2 flash principal of `200 USDC` is reused many times inside one atomic external-buyer batch:

`flash200 -> ADDLP200 -> buyer $1 -> REMOVE200 -> internal sync/policy -> ADDLP200 -> buyer $1 -> ... -> repay200 once`.

The same borrowed 200 USDC is a temporary execution-liquidity flywheel. It is not retained and is not counted as protocol wealth.

## Why $200 is interesting for a $1 buyer quantum

For a CPMM USD leg with persistent USDC reserve `u0`, proportional temporary liquidity `F`, and an external buyer input `b`, zero-fee pool price moves by

`p1/p0 = (1 + b/(u0 + F))^2`.

With `u0 = 0.5`, `F = 200`, `b = 1`:

`p1/p0 ~= 1.00999994`.

So a single external $1 buyer quantum creates almost exactly a +1% marginal-price step while the buyer trades against ~200.5 USDC of temporary depth. Proportional REMOVE100 of the temporary LP does not change that post-trade marginal price.

This is the reason V2.4 uses 200 USDC as a price-step damper rather than as a source of profit.

## Internal reflexive synchronizer

After temporary LP is removed, most of the external buyer dollar is held by the protocol. A tiny part can be moved from treasury into the lower-priced second USD leg to buy/burn its token and synchronize it upward.

Moving protocol-owned USDC from treasury to a protocol-owned pool does not change consolidated canonical USDC, but it does change the reserve ratio and therefore the internal marginal price.

This is the source of the marked-NAV multiplier.

### Exact first-quantum example, before the emission-band dampener

Starting with 1,000,000 RUBC and 1,000,000 RUBX marked at $1:

- canonical hard cash: `$1 -> $2` after one external buyer dollar;
- RUBC marginal price: approximately `$1 -> $1.01`;
- synchronizing RUBX to the same price costs only about `$0.00249` of internal treasury movement;
- both million-token supplies are then marginally marked about 1% higher;
- the reflexive marked-NAV increase is about `$20,000` from one external `$1` shock.

This is a marginal-price valuation effect, not $20,000 of withdrawable USDC.

## Directed AI-CB monetary policy

The requested asymmetry is retained exactly at the policy level:

- every +1% price step creates a sell allowance equal to 1% of the **active emission band**;
- every -1% price step creates a buy-and-burn allowance equal to 2% of the **active emission band**.

The active emission band is liquidity-normalized. Applying 1–2% to the full million-token supply against $1 genesis liquidity would be mechanically non-executable: the order would dwarf the pool. V2.4 therefore defines an active monetary tranche (simulation default: 10% of the currently active pool-side token inventory), while the rest of supply is a locked monetary reserve.

The 1:2 expansion/contraction asymmetry is preserved; only the base to which it is applied is made executable.

## Dual accounting

V2.4 intentionally exposes two different economic surfaces:

### HardCashUSDC

Canonical USDC actually owned by the system after flash repayment. Internal swaps cannot increase this number by themselves.

### SystemicMarkedNAV

`HardCash + RUBC supply * RUBC marginal price + RUBX supply * RUBX marginal price`.

This metric can grow strongly from internal reserve-ratio reconfiguration even while canonical USDC is unchanged. It is useful as a systemic monetary/valuation state, but it must not be presented as 1:1 withdrawable cash.

A third `liquidationNAVUSDC(fractionBps)` metric is supplied by `SystemicNAVAccountingV24.sol` to expose how much USDC a specified liquidation fraction can actually obtain from the pool curves.

## 100-dollar recycled-flash experiment

Parameters:

- genesis hard cash: `1 USDC`;
- one Balancer flash principal: `200 USDC`;
- 100 microcycles inside the modeled batch;
- one external buyer dollar per microcycle;
- 1,000,000 RUBC and 1,000,000 RUBX initial supplies;
- active emission band ratio: 10%;
- +1% -> sell 1% active band;
- internal upward synchronization with token burn;
- flash debt at final settlement: zero.

Result:

- external USDC: `100`;
- HardCash: `1 -> 101 USDC`;
- RUBC price: `1 -> 2.213739`;
- RUBX price: `1 -> 2.213739`;
- RUBC supply end: `999,999.938788`;
- RUBX supply end: `999,999.938379`;
- spot-marked systemic NAV: about `2,000,001 -> 4,427,579 USDC-equivalent`;
- incremental marked NAV: about `+2,427,578`;
- average incremental marked-NAV multiplier per external USDC: about `24,275.78x`;
- canonical cash multiplier per external USDC: exactly `1x`;
- cash conservation: PASS;
- end flash debt: `0`.

Without the +1% sell-band dampener, the same toy model reaches a price around `2.70284` after 100 buyer dollars and an average incremental marked-NAV multiplier around `34,058x` per external dollar.

## Important interpretation

The design deliberately maximizes a **reflexive marked-value multiplier** while preserving exact canonical-cash accounting. It does not claim that marginally marking two million tokens at the internal pool price creates the same amount of immediately withdrawable USDC.

That separation is what makes the architecture testable rather than circular: the system can aggressively exploit internal revaluation and still expose, side by side, how much real external reserve and liquidation capacity exists.
