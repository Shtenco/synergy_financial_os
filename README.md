# SINERGY Financial OS

**Canonical federation root for the SINERGY economic and financial operating system.**

This repository is intentionally **not** a replacement for the historical SINERGY repositories. It is the canonical integration, constitution and schema layer above them.

## Non-destructive evolution rule

SINERGY uses append-only architectural evolution:

- historical repositories, branches, contracts, simulations and negative tests are preserved;
- old mechanisms are not silently rewritten into new claims;
- a mechanism may move between evidence statuses, but its original evidence remains immutable;
- new canonical behavior is added through specifications, schemas, adapters, manifests and additive branches;
- contradictory historical experiments remain provenance and falsification evidence.

> **Do not delete history to make the current architecture look cleaner.**

## One-sentence definition

SINERGY is a programmable financial operating system that connects household capital formation, maturity-matched savings and credit, payment/FX routing, productive investment and real-economy verification while constraining issuance, risk and distributions by a canonical double-entry ledger, external balance-sheet truth and hard constitutional invariants.

## Core monetary separation

```text
CAPITAL != RESERVE != MONEY != CREDIT
```

Reference roles:

- **SYNA** — capital/equity/upside/governance/junior risk;
- **SYNR** — reserve/savings/insurance/junior protection capital;
- **SYNT** — abstract transaction-money / unit-of-account interface;
- **USDS** — concrete USD-linked monetary/credit implementation family and research line;
- **Credit** — temporary asset/liability relation with maturity, expected-loss and funding-duration accounting, not a speculative fourth money.

## Canonical accounting truth

```text
HardNAV     = hard externally redeemable assets - external liabilities
LiquidNAV   = haircut liquid assets             - external liabilities
EconomicNAV = haircut economic assets           - external liabilities
```

Own-token market capitalization, internal AMM marks, virtual reserves, mint/burn/rebase operations and recycled internal fees do not become external assets merely because they raise a displayed price or TVL.

Reference distributable-profit rule:

```text
DistributableProfit_t =
max(0, HardNAV_t - HardNAV_(t-1) - NetNewCapital_t)
```

Deposits, sponsor capital, principal repayments, flash-loan principal and internal transfers are not revenue by themselves.

## Hard constitutional invariants

```text
sum(debits) == sum(credits)
unbacked_hard_money_mint == 0
flash_debt_at_accounting_commit == 0
loan_maturity < funding_maturity
buyback_budget <= realized_distributable_profit_budget
own_token_market_cap not in HardNAV
internal_price_mark not in HardNAV
principal_repayment not classified as profit
new_participant_capital not classified as profit
```

Additional risk limits include HardNAV coverage, liquidity coverage, maturity walls, NPL/default ceilings, concentration, FX/bridge/provider risk and bounded external-return sleeves.

## Operating modes

- `GROWTH` — bounded expansion only against verified productive demand and risk capacity;
- `NORMAL` — ordinary policy;
- `DEFENSE` — reduce risk, tighten credit, build liquidity/reserves;
- `EMERGENCY` — stop new risk creation and protect settlement/redemption;
- `NO_ACTION` — always valid when no safe positive decision exists.

## Federation architecture

```text
Household / Business
        |
        v
synergy_matrix_sota
Savings / independent tranches / maturity / mutual-P2P credit
        |
        v
synergy_financial_os  <---- canonical constitution and schemas
        |
        +---- ai_financial_system     financial R&D, HardNAV, AI-CB, QE/QT, AMM/MEV history
        +---- usds                    elastic/credit-money research implementation
        +---- synergy_pay_system      MetaPay routing, settlement, compliance, reconciliation
        +---- synergychain            portal/control plane / Growth OS / OGAS surface
        +---- synergy_ai_blockchain   trust/state/proof layer
        +---- synergy_eurasian        real economy / EIIOM / productive projects
        +---- agi_olga                OLGA/NEXUS intelligence
        +---- ai_language             semantic engineering and requirement traceability
        +---- ai_compress             lossless memory/archive/MDL layer
        +---- ai_coder                autonomous engineering orchestration
```

Historical/public lineage remains separate and preserved:

- `Shtenco/cashero` — cyclic-token/liquidity/adaptive-supply research ancestor;
- `Shtenco/shtenco.github.io` — historical personal research surface;
- `Shtenco/shtencoauantai.github.io` — historical SHTENCO Quant/AI public surface and additive experiments;
- `Shtenco/synergychain.github.io` — public static presentation build for SINERGYCHAIN.

## End-to-end capital cycle

```text
income
 -> household delta
 -> savings/reserve
 -> independent maturity tranches
 -> funding capacity
 -> P2P / bank / investment-bank allocation
 -> productive claim / CFA / equity / project finance
 -> production / inventory / logistics / infrastructure
 -> verified goods/services
 -> external settlement and revenue
 -> principal repayment + realized profit
 -> QT / reserves / saver return / reinvestment
 -> larger household and system capital
```

The monetary-credit cycle is separate but connected:

```text
verified productive demand
 -> bounded credit-money authorization
 -> verified release
 -> production
 -> external revenue
 -> principal repayment
 -> QT / liability destruction
```

## Two-lift model

The historical twin-elevator idea is retained in balance-sheet form.

**Asset lift**

```text
external settlement
+ realized external profit
+ eligible performing claims after haircut
+ hard reserve inflow
 -> asset capacity rises
```

**Liability lift**

```text
principal repayment
+ authorized redemption/settlement
+ profit-funded liability retirement
 -> transaction/credit liabilities fall
```

Unrealized appreciation of a system-issued token cannot retire consolidated liabilities.

## Repository status model

Every cross-repository mechanism must receive one claim-specific evidence status:

- `LEGACY` — historical provenance; not current authority;
- `EXPERIMENTAL` — research hypothesis;
- `VERIFIED_SIM` — deterministic/statistical simulation evidence;
- `FORK_VERIFIED` — executable fork/integration evidence;
- `CANONICAL` — accepted architecture rule or schema;
- `PRODUCTION` — independently governed live deployment with legal, custody, security and operational readiness.

A contract may be `FORK_VERIFIED` for execution while its economic-return hypothesis remains `EXPERIMENTAL`.

## Source-of-truth hierarchy

When sources conflict, prefer:

1. reconciled external settlement evidence;
2. canonical balanced ledger events;
3. signed/digestible financial snapshots;
4. audited eligible performing claims after disclosed haircuts;
5. executable funded market quotes;
6. market marks;
7. simulations;
8. AI forecasts;
9. token-price narratives.

## Repository ownership boundary

This repository owns:

- monetary/accounting constitution;
- cross-repository schemas and versioning;
- federation manifests;
- canonical invariant definitions;
- compatibility/evidence registries;
- reference integration tests.

It does **not** own:

- payment-provider credentials or execution adapters (`synergy_pay_system`);
- real-economy sector models (`synergy_eurasian`);
- historical DeFi experiments (`ai_financial_system`);
- AI model weights/architectures (`agi_olga`);
- public portal rendering (`synergychain` / `synergychain.github.io`).

## Immediate build order

1. Freeze the repository-federation manifest and legacy policy.
2. Define versioned schemas for `FinancialSnapshot`, `MaturitySnapshot`, `CreditProposal`, `PaymentIntent`, `SettlementReceipt`, `ProjectProposal` and `PolicyProposal`.
3. Import no legacy code destructively; bind reusable implementations by repository + branch/commit + evidence status.
4. Add cross-repository contract tests.
5. Build the canonical event-sourced double-entry ledger interface.
6. Connect `synergy_matrix_sota` funding-duration state.
7. Connect `synergy_pay_system` settlement receipts.
8. Connect `synergy_eurasian` productive-project evidence.
9. Connect bounded OLGA/NEXUS policy proposals through a safety shield.
10. Commit signed snapshot digests to the blockchain trust layer.

## Safety and claims boundary

This is research and systems engineering. Software does not itself provide a banking licence, CBDC participation, exchange access, custody approval, guaranteed yield or legal authority to issue regulated financial instruments. Live operation requires jurisdiction-specific legal structure, contracts, security review, custody/key management, provider readiness, audit and explicit governance.
