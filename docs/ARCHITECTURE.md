# SINERGY Financial OS — Canonical Architecture

## 1. Purpose

This document defines the canonical integration architecture above the preserved historical repositories. It does not erase or reinterpret their original evidence.

## 2. Five planes

### 2.1 Household capital plane
Owned by `Shtenco/synergy_matrix_sota`.

Responsibilities:
- voluntary/contractual savings contributions;
- independent tranches;
- 1–100 week maturity ladder;
- liquidity buckets;
- mutual/P2P credit funding availability;
- duration matching;
- household reserve and capital formation state.

### 2.2 Monetary/accounting plane
Owned canonically by this repository; research/reference implementations live in `Shtenco/ai_financial_system` and `Shtenco/usds`.

Responsibilities:
- canonical double-entry accounting;
- HardNAV/LiquidNAV/EconomicNAV;
- capital/reserve/money/credit separation;
- productive credit/QE and repayment/QT rules;
- insurance/loss waterfalls;
- policy modes and hard invariants;
- investment-bank allocation constraints.

### 2.3 Payment/settlement plane
Owned by `Shtenco/synergy_pay_system`.

Responsibilities:
- payment intent;
- compliance and provider readiness;
- fiat/crypto/CBDC routing;
- RFQ/liquidity reservation;
- settlement state machine;
- reconciliation and settlement receipts.

### 2.4 Real-economy plane
Owned by `Shtenco/synergy_eurasian`.

Responsibilities:
- EIIOM/input-output models;
- project graph and sector constraints;
- CAPEX/OPEX/cash-flow scenarios;
- verified productive demand;
- goods/inventory/logistics/production evidence;
- productive-capital proposals.

### 2.5 Intelligence/control plane
`Shtenco/agi_olga` owns OLGA/NEXUS intelligence; `Shtenco/synergychain` owns portal/OGAS control-plane integration; `Shtenco/synergy_ai_blockchain` is the future trust/state/proof layer.

AI proposes. Constitutions and deterministic validators authorize.

## 3. Canonical accounting perimeter

Every financial snapshot must state the legal/consolidation perimeter. Internal claims eliminate on consolidation unless the issuer is legally outside the reporting perimeter and the claim is externally enforceable.

Own-token market capitalization is never a hard asset of its own issuer.

## 4. Capital, reserve, money, credit

```text
SYNA -> equity / governance / upside / junior risk
SYNR -> reserve / savings capital / insurance/junior protection
SYNT -> abstract transactional monetary interface
USDS -> USD-linked monetary/credit implementation research family
Credit -> temporary claim and liability with maturity + expected loss
```

No single instrument should simultaneously promise stable redemption, speculative upside, reserve backing and unlimited credit elasticity.

## 5. Event-sourced accounting

Reference model:

```text
External/operational event
 -> evidence validation
 -> balanced journal
 -> append-only ledger sequence
 -> financial snapshot
 -> digest/signature
 -> optional blockchain commitment
```

Every monetary effect must be reconstructible from accepted events.

## 6. NAV hierarchy

```text
HardNAV     = HardExternalAssets - ExternalLiabilities
LiquidNAV   = HaircutLiquidAssets - ExternalLiabilities
EconomicNAV = HaircutEconomicAssets - ExternalLiabilities
```

Reference public ordering:

```text
HardNAV <= LiquidNAV <= EconomicNAV
```

## 7. Profit

```text
DistributableProfit_t = max(
  0,
  HardNAV_t - HardNAV_(t-1) - NetNewCapital_t
)
```

Not profit by themselves:
- deposits;
- new participant contributions;
- sponsor capital;
- principal repayment;
- mint/burn/rebase;
- internal transfer fees;
- flash principal;
- own-token repricing;
- internal AMM marks.

## 8. Savings and duration

Funding is modeled by maturity, not merely by token lockups.

```text
loan_maturity < funding_maturity
```

The system must publish unlock curves and liquidity coverage windows. A loan cannot be funded by capital that contractually exits before the loan matures without an explicit replacement-liquidity facility.

## 9. Productive credit

Reference maximum envelope:

```text
QE_max = min(
  reserve_capacity,
  liquidity_capacity,
  verified_productive_demand,
  risk_capacity
)
```

Authorization is not cash, HardNAV or profit. Monetary liability arises only at verified release. Principal repayment retires the corresponding liability through QT; collected interest/fees become revenue only after external settlement.

## 10. Twin elevators

### Asset elevator
External settlement, hard reserve inflow, realized external profit and eligible performing claims after haircut increase asset capacity.

### Liability elevator
Principal repayment, authorized redemption and profit-funded retirement reduce outstanding monetary/credit liabilities.

Internal price appreciation cannot close the liability elevator.

## 11. Debt metrics

Do not reuse one ambiguous `DebtGap` sign convention.

```text
DebtCapacityGap = DebtCapacity - DebtOutstanding
CoverageDeficit = max(DebtOutstanding - DebtCapacity, 0)
```

Positive `DebtCapacityGap` means remaining capacity. Positive `CoverageDeficit` means a problem.

## 12. Risk modes

`GROWTH`, `NORMAL`, `DEFENSE`, `EMERGENCY`, plus explicit `NO_ACTION`.

AI/RL cannot bypass mode-specific hard constraints.

## 13. Loss waterfall

Reference ordering:

```text
borrower collateral
 -> expected-loss reserve
 -> event-specific insurance
 -> general reserve / SYNR junior capital
 -> sponsor first-loss capital
 -> protected saver capital only as residual last resort
```

## 14. AMM / QE / MEV / flash historical research

These mechanisms remain in `ai_financial_system` and must not be deleted. Their reusable execution ideas include graph routing, solver auctions, protocol-owned liquidity, bounded flash funding and stateful route simulation.

Accounting correction:

```text
internal repricing != external wealth
flash principal != revenue
self-paid fee != consolidated profit
```

A route contributes to financial profit only after consolidated external post-cost value rises.

## 15. MetaPay boundary

Financial OS emits economic intents and constraints. `synergy_pay_system` selects/executes approved routes and returns settlement evidence. The payment system does not invent accounting profit; the canonical ledger recognizes receipts after reconciliation.

## 16. Real-economy bridge

Productive projects expose:
- funded private/bank capital;
- project maturity;
- risk and concentration;
- FX exposure/hedge state;
- production/goods/inventory milestones;
- external settlement evidence.

Conditional authorization can be released only as verified productive state advances.

## 17. AI boundary

```text
Constitution
 -> deterministic baseline
 -> bounded AI/RL residual
 -> hard safety shield
 -> proposal/action
```

If the model is unavailable or uncertainty exceeds policy, AI residual becomes zero or the system returns `NO_ACTION`.

## 18. Blockchain boundary

Blockchain is a trust anchor, not the whole economy. Preferred commitments include ledger/snapshot digests, settlement finality, governance decisions, ownership state and evidence references. Private provider credentials, internal databases and full accounting logic remain off-chain where appropriate.

## 19. Legacy preservation

Every historical mechanism reused by this architecture must be bound by:
- repository;
- branch/tag/commit;
- files/contracts;
- original claim;
- current evidence status;
- canonical accounting interpretation;
- known negative controls.

No destructive migration is permitted by architecture policy.
