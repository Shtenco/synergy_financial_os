# SYNERGY Financial OS

> **Канонический финансово-бухгалтерский слой экосистемы SYNERGY: HardNAV, double-entry accounting, ликвидность, обязательства, распределение капитала, признание внешней прибыли, продуктивное финансирование и доказательная денежная политика.**

**Статус:** R&D / Federation V3 / regulatory-sandbox candidate.  
**Authority:** `canonical_accounting`.  
**Главный принцип:** **внутренняя переоценка не является внешней прибылью, а финансовый факт существует только после проверяемого evidence + accounting recognition.**

---

## 1. Что это за репозиторий

`synergy_financial_os` — финансовая операционная система СИНЕРГИИ.

Если говорить просто, это слой, который отвечает на пять главных вопросов:

1. **Сколько у системы реально есть внешних активов?**
2. **Сколько у неё обязательств?**
3. **Что из поступивших денег действительно является прибылью, а что — капиталом, долгом, возвратом principal или внутренним перемещением?**
4. **Сколько система может безопасно инвестировать, распределить, направить в проекты или выпустить в денежный контур?**
5. **Какими доказательствами подтверждён каждый финансовый факт?**

Financial OS намеренно не пытается быть одновременно торговым роботом, платёжной системой, блокчейном, AI-центробанком и промышленным симулятором.

Он является **судьёй экономического факта**.

```text
MIDAS / MetaPay / AI-CB / Eurasian / Budget / Apps
                    │
                    ▼
            evidence / intents
                    │
                    ▼
        ┌────────────────────────┐
        │  SYNERGY FINANCIAL OS  │
        │                        │
        │  ledger                │
        │  HardNAV               │
        │  liabilities           │
        │  liquidity             │
        │  accounting close      │
        │  profit recognition    │
        │  capital capacity      │
        │  risk / distribution   │
        └────────────────────────┘
                    │
          accounting commitments
                    │
                    ▼
        Blockchain / MetaChain / UI
```

---

## 2. Почему `main` раньше выглядел пустым

Исторически разработка этого репозитория велась почти полностью через **stacked feature branches и pull requests**.

Поэтому до этого README ветка `main` содержала только короткую заглушку, хотя большая система уже существовала в нескольких линиях разработки.

Ключевые линии:

| Линия | Роль | Статус |
|---|---|---|
| `feat/distribution-available-capacity-v4-refund-restored-20260828` | Terminal Economic OS / Financial OS lineage | большой кандидат на канонизацию |
| PR #33 | перенос terminal Economic OS lineage в `main` | OPEN / DRAFT |
| `federation-v3-domain-expansion` | Federation V3 contracts + Financial OS boundary | OPEN через PR #39 |
| PR #37–#38 | External Profit Bus / External Profit Import | отдельные fail-closed consumers |
| PR #34–#36 | RUBC/RUBX/AI-CB/HardTVL research | R&D / falsification line |

На момент формирования этой документации PR #33 содержит **443 коммита, 365 изменённых файлов и ~39k additions** относительно пустого `main`. Это не означает production-ready статус; это показывает, почему внешний вид `main` не отражал реальный объём проведённой работы.

Этот README специально становится **единым индексом всего проекта**, не уничтожая историю веток и PR.

---

# 3. Конституция Financial OS

## 3.1. Основное правило

```text
INTERNAL VALUE CREATION != EXTERNAL ECONOMIC PROFIT
```

И в более жёсткой форме:

```text
NO EXTERNAL SETTLEMENT
        ↓
NO EXTERNAL PROFIT RECOGNITION
```

Financial OS не должен признавать прибыль только потому, что:

- был сделан `mint`;
- токен вырос в цене;
- собственный AMM изменил marginal price;
- вырос отображаемый TVL;
- был получен flash loan;
- капитал переложили между собственными кошельками;
- principal кредита вернулся;
- AI спрогнозировал будущий доход;
- backtest показал прибыль;
- blockchain записал hash.

---

## 3.2. Capital, Reserve, Money и Credit — разные сущности

```text
CAPITAL != RESERVE != MONEY != CREDIT
```

Историческая модель СИНЕРГИИ разделяет роли:

- **SYNA** — капитал / equity / upside / junior risk / governance research;
- **SYNR** — резервный / сберегательный / страховой капитал;
- **SYNT** — абстрактный интерфейс transaction money;
- **USDS** — USD-linked monetary/credit research family;
- **Credit** — временное отношение `asset ↔ liability` со сроком, expected loss и источником фондирования.

Один и тот же токен не должен без явной модели одновременно быть:

- стабильной валютой;
- акцией;
- страховым резервом;
- кредитом;
- speculative upside asset.

---

# 4. Три уровня NAV

Financial OS отделяет реально погашаемую стоимость от более мягких экономических оценок.

```text
HardNAV
    = Hard External Assets
    - External Liabilities

LiquidNAV
    = Haircut Liquid Assets
    - External Liabilities

EconomicNAV
    = Haircut Economic Assets
    - External Liabilities
```

Рекомендуемый порядок:

```text
HardNAV <= LiquidNAV <= EconomicNAV
```

### HardNAV

Самая консервативная поверхность стоимости. В неё должны попадать только активы, которые имеют реальную внешнюю погашаемость/settlement semantics и проходят заданный accounting perimeter.

### LiquidNAV

Добавляет активы, которые можно превратить в ликвидность, но после haircut и с учётом сроков/риска.

### EconomicNAV

Может учитывать более широкий класс производственных и экономических активов, но только через явную методику оценки и haircut.

### Что не должно автоматически попадать в HardNAV

```text
own-token market cap
internal AMM mark
virtual reserves
minted internal token
unrealized internal revaluation
flash-loan principal
self-paid fee
```

---

# 5. Event-sourced double-entry accounting

Базовая архитектура:

```text
External / Operational Event
            ↓
Evidence Validation
            ↓
Economic Classification
            ↓
Balanced Journal Entry
            ↓
Append-only Reporting Ledger
            ↓
Accounting Period
            ↓
Accounting Close
            ↓
Financial Snapshot
            ↓
Digest / Merkle Root
            ↓
Optional Blockchain Commitment
```

Главный инвариант:

```text
sum(debits) == sum(credits)
```

Financial OS строился как **append-only accounting system**: старый финансовый факт не должен бесследно переписываться новым.

Коррекции, рестейтменты, reversals и refunds создают новый слой доказательств и проводок.

---

# 6. Базовые модули terminal Economic OS lineage

Terminal-ветка содержит уже большой Python-контур `sinergy_financial_os/`.

Среди явно присутствующих модулей:

- `account_registry_v1.py` — реестр счетов и экономических типов;
- `accounting_period_v1.py` — accounting periods;
- `accounting_period_chain_v1.py` — связанная цепочка периодов;
- `accounting_close_v1.py` / `accounting_close_v2.py` — закрытие периода;
- `accounting_restatement_view_v1.py` — restatement view;
- `authorized_prior_period_correction_v1.py` — контролируемые корректировки прошлых периодов;
- `authorized_revenue_adjustment_v1.py` — evidence-bound корректировка revenue;
- `ai_boundary.py` — граница между AI proposal и финансовой authority;
- многочисленные поколения maturity/liquidity/distribution contracts;
- schema registry, fixtures, strict JSON schemas и тесты.

В `docs/` terminal lineage также присутствуют отдельные спецификации по:

- architecture;
- account registry;
- accounting close + Merkle;
- canonical JSON profile;
- AI constitutional concurrency;
- audit corrections;
- capital authorization;
- economic-cycle trace;
- distribution accounting;
- последующим поколениям settlement/reversal/budget/capacity.

---

# 7. Account Registry

Financial OS не должен считать, что любой внешний `account_id` автоматически является бухгалтерским счётом.

Необходим явный mapping:

```text
Operational Source Account
          ↓
Verified Mapping
          ↓
Canonical Reporting Account
          ↓
Economic Class
```

Типовые классы:

```text
EXTERNAL_ASSET
EXTERNAL_LIABILITY
EXTERNAL_EQUITY
EXTERNAL_REVENUE
EXTERNAL_EXPENSE
INTERNAL / MEMO / CONTROL surfaces
```

Это особенно важно при интеграции с MetaPay: платёжный `source_account_id` не должен автоматически определять бухгалтерскую природу проводки.

---

# 8. Accounting Period, Close, Merkle и Restatement

Financial OS содержит отдельную модель периодов и закрытий.

Задача close — зафиксировать:

- ledger sequence;
- набор признанных проводок;
- HardNAV / LiquidNAV / liabilities;
- realized P&L;
- liquidity/maturity state;
- evidence references;
- digest / Merkle commitment.

После close нельзя просто изменить старую строку ledger.

Исправление строится как:

```text
Original Close
     ↓
New Evidence / Correction Authorization
     ↓
Append-only Correction Entry
     ↓
Restatement View
     ↓
New Close / Snapshot Generation
```

Таким образом Financial OS сохраняет одновременно:

- первоначально опубликованный факт;
- последующую корректировку;
- причину корректировки;
- authorization/evidence;
- новое состояние.

---

# 9. Profit Recognition

Базовая логика distributable profit:

```text
DistributableProfit_t = max(
    0,
    HardNAV_t
    - HardNAV_(t-1)
    - NetNewCapital_t
)
```

Это защищает систему от одной из самых опасных ошибок финансовых моделей: принять новое финансирование за доход.

### Не является прибылью само по себе

- deposit;
- sponsor contribution;
- capital injection;
- principal repayment;
- flash principal;
- internal transfer;
- mint;
- burn;
- rebase;
- собственная LP-переоценка;
- новое обязательство;
- authorization;
- backtest P&L.

### Может стать внешней прибылью после evidence/reconciliation

- реализованный торговый P&L;
- внешний arbitrage/routing P&L;
- внешняя комиссия от независимого контрагента;
- выручка от товара/услуги;
- инвестиционный income;
- иная внешняя settlement-backed экономическая выгода.

---

# 10. External Profit Bus и External Profit Import

В отдельных PR #37 и #38 создан fail-closed путь для приёма внешней прибыли.

Общая идея:

```text
MetaPay / DEX / External Venue
            ↓
Settlement Evidence
            ↓
External Profit Bus
            ↓
Financial OS Consumer
            ↓
Classification
            ↓
Reporting Ledger
```

Financial OS должен независимо проверять:

- external counterparty / venue evidence;
- settlement reference;
- route digest;
- realized result;
- fees/costs;
- repayment flash principal, если он использовался;
- currency semantics;
- accounting perimeter.

В External Profit Import V1 применяется fail-closed правило: положительный `REALIZED_EXTERNAL_PNL` не должен превышать подтверждённый внешний cash delta.

Также V1 сознательно не смешивает автоматически `USD` и `USDT`.

---

# 11. MetaPay boundary

`synergy_pay_system` и Financial OS имеют разные полномочия.

```text
Financial OS
   │
   ├─ определяет экономические ограничения
   ├─ выдаёт approved economic/payment handoff
   ▼
MetaPay
   │
   ├─ routing
   ├─ provider / venue selection
   ├─ funding / reservation
   ├─ execution
   ├─ settlement
   ▼
Settlement Evidence
   │
   ▼
Financial OS
   │
   └─ accounting recognition
```

Принцип:

> **MetaPay знает, что физически/финансово settled. Financial OS решает, что это означает экономически и бухгалтерски.**

---

# 12. Distribution System: от прибыли к безопасной выплате

Одна из самых глубоких линий репозитория — последовательное развитие owner-distribution accounting.

Она строится не как `profit > 0 → payout`, а как длинная цепочка доказательств.

```text
Period Profit
    ↓
Distribution Budget State
    ↓
Available Capacity
    ↓
Distribution Plan
    ↓
Human / Multisig Authorization
    ↓
Short-lived Execution Ticket
    ↓
MetaPay Batch Attempt
    ↓
Settlement Receipts
    ↓
Utilization
    ↓
Financial OS Accounting
```

---

## 12.1. Current capacity

Ключевая идея поздних поколений:

```text
final_available_capacity = min(
    remaining_period_profit_budget,
    current_solvency_headroom,
    current_liquidity_distribution_capacity
)
```

Если есть blocker:

```text
final_available_capacity = 0
```

То есть распределить прибыль можно только если одновременно хватает:

- реальной прибыли периода;
- текущего HardNAV/solvency buffer;
- текущей ликвидности по горизонтам.

---

## 12.2. Fee-aware distribution

Поздние поколения добавили payer-borne external settlement fees.

Authorization обязан учитывать:

```text
principal_total + external_fee_budget
    <= final_available_capacity
```

Неиспользованный fee budget:

```text
!= revenue
!= expense
!= profit
```

Он просто остаётся неиспользованной capacity.

Фактически понесённая внешняя комиссия после settlement становится отдельным `EXTERNAL_EXPENSE`.

---

## 12.3. Principal payout не является expense/P&L

При выплате владельцу/участнику principal accounting отделён от внешней комиссии.

Концептуально:

```text
Settled principal P
    → external capital outflow
    → excluded from realized P&L

Actual settlement fee F
    → external expense
    → realized P&L effect = -F
```

Это не позволяет системе искусственно ухудшать или улучшать operating profit из-за перемещения собственного капитала.

---

## 12.4. Settlement reversals

Если ранее состоявшаяся выплата позднее была компенсирована/возвращена провайдером, Financial OS создаёт отдельный reversal accounting path.

Returned principal:

```text
Dr External Cash
Cr Distribution Equity
```

и не становится новой прибылью.

Fee refund и новая reversal-processing fee учитываются отдельно.

Это позволяет получить правильную экономику:

```text
returned principal        → capital recovery
refunded old fee          → expense recovery
new reversal fee          → new external expense
```

Authorization при этом не должен «оживать» и использоваться второй раз.

---

# 13. Remaining Profit Budget / Anti-Replay

Financial OS содержит отдельную идею **экономического replay protection**.

Проблема:

если owner distribution не уменьшает realized P&L, то без дополнительного состояния система могла бы снова взять тот же gross-period profit и повторно построить новый distribution plan.

Для этого введён `DistributionBudgetState`.

Он учитывает:

- gross period profit budget;
- уже проведённые owner distributions;
- canonical reversals;
- settlement fees;
- fee refunds;
- reversal processing fees;
- оставшееся право на распределение.

Поздняя формула:

```text
net_post_close_distribution_fee_cost
    = settlement_fee_expense
    - valid_fee_refunds
    + reversal_processing_fees

fee_adjusted_period_profit_budget
    = min(
        gross_period_profit_budget,
        max(0, gross_period_profit_budget - net_fee_cost)
      )

remaining_period_profit_budget
    = max(
        0,
        fee_adjusted_period_profit_budget
        - net_consumed_distribution_principal
      )
```

Fee refund может **восстановить ранее потерянную capacity**, но не может создать новую прибыль сверх исходного gross budget.

---

# 14. Maturity и Liquidity

Financial OS моделирует не только величину капитала, но и время.

Главный принцип:

```text
loan_maturity < funding_maturity
```

Если капитал может быть выведен раньше, чем заканчивается финансируемый кредит/проект, то такой источник не должен считаться безопасным funding без отдельного replacement-liquidity facility.

Система отслеживает liquidity horizons и ограничения вида:

```text
resources_horizon >= required_outflows_horizon × LCR_floor
```

и стрессовые surplus floors.

Это связывает:

- household savings;
- P2P/credit;
- project financing;
- owner distributions;
- redemptions;
- settlement reserves.

---

# 15. Development Fund / Capital Engine

В Federation V3 Financial OS переводит старую идею «фонда развития» из абстрактного общего пула в бухгалтерски проверяемую структуру.

Каждый capital allocation должен быть привязан к:

```text
proposal_id
approved_amount
payment_ticket
settlement_evidence
asset_or_project_ledger
realized_cash_flow
impairment_or_revaluation_policy
```

### Distribution capacity Development Fund

```text
DistributableCapacity <= max(
    0,
    LiquidNAV
    - liabilities
    - required_reserves
    - committed_capital
    - stress_buffer
)
```

---

# 16. Synergy Eurasian / продуктивная экономика

`synergy_eurasian` является отдельным владельцем физической/производственной модели.

Financial OS не должен сам себе рисовать произведённые товары или мощность.

```text
Synergy Eurasian
    ↓
Productive / Physical Evidence
    ↓
Financial OS
    ↓
Accounting / valuation / HardNAV boundary
```

Проекты могут включать:

- промышленность;
- оборудование;
- инфраструктуру;
- логистику;
- сельское хозяйство;
- экспорт;
- SME;
- локализацию производства.

Financial OS отвечает не за инженерную истинность проекта, а за его **финансовый периметр, финансирование, settlement, liabilities, impairment, cash flow и признание стоимости**.

---

# 17. AICB V5 — Productive Monetary System

В текущем Federation V3 / AICB V5 контуре Financial OS является одним из двух независимых ключей продуктивной эмиссии.

Архитектура:

```text
AICB V5
  │
  └─ TargetEmissionProposal
         ↓
Independent Risk Approval
         ↓
Mint into Emission Escrow
         ↓
    ┌───────────────┐
    │               │
    ▼               ▼
Synergy Eurasian   Financial OS
ProductiveGrowth   EligibleAssetGrowth
Attestation        Attestation
    │               │
    └───────┬───────┘
            ▼
       DUAL-GATE RELEASE
```

## 17.1. Financial key

`EligibleAssetGrowthAttestation` отделяет:

- previous/current HardNAV;
- previous/current liabilities;
- eligible external/real asset growth;
- internal mark change;
- flash principal inflow;
- evidence refs.

Формула:

```text
hardnav_growth
    = max(current_hardnav - previous_hardnav, 0)

liability_increase
    = max(current_liabilities - previous_liabilities, 0)

net_eligible_growth
    = max(eligible_asset_gross_growth - liability_increase, 0)

financial_credit
    = min(hardnav_growth, net_eligible_growth)
```

Допустимые классы в текущем candidate contract:

- `EXTERNAL_CASH`;
- `SETTLED_RECEIVABLE`;
- `VERIFIED_PRODUCTIVE_ASSET`.

`internal_mark_change` и `flash_principal_inflow` хранятся как audit fields, но не создают emission credit.

---

## 17.2. Два независимых ключа

Даже если Financial OS подтверждает рост HardNAV, одной этой подписи недостаточно.

И наоборот, даже если Eurasian подтверждает физический рост выпуска/мощности, этого недостаточно без финансового подтверждения стоимости.

```text
release_credit = min(
    productive_growth_credit,
    financial_growth_credit
)
```

Эта модель защищает от двух противоположных ошибок:

1. **«Завод произвёл много единиц — значит можно печатать деньги»,** даже если стоимость/реализация не подтверждена.
2. **«NAV вырос — значит можно печатать деньги»,** даже если рост является лишь внутренней переоценкой.

---

## 17.3. Emission release не является прибылью

В Federation V3 добавлен `EmissionReleaseRecognition`.

Ключевой инвариант:

```text
recognized_revenue = 0
recognized_profit  = 0
```

для самого факта mint/release.

То есть увеличение circulating monetary liabilities нельзя позже переименовать в P&L.

---

# 18. Transactional Outbox / Federation V3

В `federation-v3-domain-expansion` добавлен `federation_outbox.py`.

Цель — решить классическую проблему dual-write:

```text
Accounting Fact committed
       BUT
Federation Event lost
```

или наоборот.

Правильный путь:

```text
BEGIN TRANSACTION
    write canonical accounting fact
    write signed federation outbox event
COMMIT
```

Для Financial OS реализована transactional outbox-модель для:

- reconciled trading result;
- financial close / chain commitment path.

Exact retry должен быть idempotent, а конфликтующий payload с тем же идентификатором — отклоняться.

---

# 19. MIDAS integration

MIDAS владеет trading intelligence.

Financial OS — accounting truth.

Поток:

```text
MIDAS
  ↓ TradingExecutionIntent
MetaPay
  ↓ external SettlementEvidence
Financial OS
  ↓ ReconciledTradingResult
MIDAS / reporting
```

Financial OS не признаёт:

```text
backtest profit
model expected edge
unsettled fill
internal paper result
```

как реализованный внешний P&L.

Только после settlement + reconciliation возникает authoritative accounting result.

---

# 20. Budget integration

Для государственного/бюджетного контура Financial OS получает settlement evidence и формирует accounting recognition.

Общий контрактный путь Federation V3:

```text
Blockchain Budget
  ↓ BudgetPaymentAuthorization
MetaPay
  ↓ BudgetSettlementEvidence
Financial OS
  ↓ BudgetAccountingRecognition
Budget / Audit Layer
```

Blockchain может фиксировать proof, но не получает права самостоятельно определять бухгалтерскую прибыль/расход.

---

# 21. Blockchain / MetaChain boundary

Financial OS формирует typed accounting commitment.

```text
Financial OS
  ↓ FinancialCommitmentArtifact
PQ Blockchain
  ↓ ChainCommitmentReceipt
MetaChain
  ↓ MetaChainCheckpointProof
```

Blockchain здесь — **trust anchor**, а не бухгалтер.

Он может подтверждать:

- snapshot hash;
- Merkle root;
- sequence/finality;
- ownership/governance commitments;
- evidence references.

Он не должен заново пересчитывать HardNAV по своим правилам.

---

# 22. AI boundary

AI в Financial OS может помогать:

- прогнозировать;
- классифицировать;
- находить anomalies;
- предлагать policy;
- оценивать uncertainty;
- формировать сценарии.

Но архитектура строится так:

```text
Constitution
    ↓
Deterministic Baseline
    ↓
Bounded AI / RL Residual
    ↓
Hard Safety Shield
    ↓
Proposal
    ↓
Explicit Authority / Validator
```

Если AI недоступен или uncertainty слишком велика:

```text
AI residual = 0
```

или:

```text
NO_ACTION
```

`NO_ACTION` считается полноценным корректным решением.

---

# 23. Risk modes

Базовые режимы:

- `GROWTH` — контролируемое расширение;
- `NORMAL` — обычная работа;
- `DEFENSE` — сокращение риска, рост liquidity/reserves;
- `EMERGENCY` — остановка нового риска и защита settlement/redemption;
- `NO_ACTION` — отказ от действия при недостаточном evidence/risk capacity.

AI не может отменить hard limits выбранного режима.

---

# 24. Loss Waterfall

Референсная последовательность покрытия убытков:

```text
borrower collateral
    ↓
expected-loss reserve
    ↓
event-specific insurance
    ↓
general reserve / junior protection capital
    ↓
sponsor first-loss capital
    ↓
protected saver capital only as residual last resort
```

Конкретная юридическая структура зависит от продукта и юрисдикции; эта схема является архитектурным risk principle, а не утверждением о лицензированном банковском продукте.

---

# 25. Исследовательская линия RUBC / RUBX / AI-CB / HardTVL

В PR #34–#36 находится отдельная R&D-линия по programmable liquidity, RUBC/RUBX, flash liquidity, CPMM/triangular mechanics и AI-CB.

Она **не равна canonical accounting core**.

Там исследуются:

- RUBC/USDC;
- RUBX/USDC;
- RUBC/RUBX;
- flash-funded temporary depth;
- mint/burn;
- REMOVE/ADD LP;
- reserve vault;
- AI-CB policy;
- HardTVL / ProtocolMarkedTVL;
- external order flow;
- liquidation-aware realizability.

Financial OS отделяет поверхности:

```text
HardCash / HardNAV
ProtocolMarkedTVL
SystemicMarketValue
Liquidation-Aware Value
```

Главное правило этой линии:

> Рост marginal internal mark на собственном inventory может создавать большую отображаемую market value, но не означает, что вся эта величина может быть выведена во внешний USDC.

Flash principal также не считается источником прибыли.

Эта ветка сохраняется как R&D/falsification evidence.

---

# 26. Hard constitutional invariants

Ключевые правила, которые должны сохраняться при дальнейшей канонизации:

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

capital_reallocation_creates_system_pnl == false

external_profit_requires_realized_settlement == true

flash_principal_is_external_profit == false

internal_mint_is_external_profit == false

internal_revaluation_is_external_profit == false

AI has no accounting authority

Blockchain has no accounting authority
```

---

# 27. Source-of-truth hierarchy

Если разные системы спорят между собой, приоритет должен быть примерно таким:

1. **Reconciled external settlement evidence**;
2. **Canonical balanced ledger events**;
3. **Signed/digestible accounting close / financial snapshot**;
4. **Audited eligible claims/assets after disclosed haircut**;
5. **Executable funded market quotes**;
6. **Market marks**;
7. **Simulation**;
8. **AI forecast**;
9. **Narrative / token-price story**.

Чем ниже источник в списке, тем меньше у него права превращаться в бухгалтерский факт.

---

# 28. Evidence status model

Каждый механизм необходимо оценивать отдельно по конкретному claim.

| Статус | Значение |
|---|---|
| `LEGACY` | историческая линия / provenance |
| `EXPERIMENTAL` | исследовательская гипотеза |
| `VERIFIED_SIM` | подтверждено воспроизводимой симуляцией |
| `FORK_VERIFIED` | подтверждено executable fork/integration тестом |
| `CANONICAL` | принято как архитектурное правило/schema |
| `PRODUCTION` | независимо управляемое live-развёртывание с legal/security/ops readiness |

Один и тот же компонент может иметь разные статусы для разных утверждений.

Например:

```text
contract execution: FORK_VERIFIED
expected economic return: EXPERIMENTAL
```

Это нормально.

---

# 29. Главные PR и поколения

Ниже — карта наиболее важных открытых веток/PR, чтобы история Financial OS читалась как единая эволюция.

| PR | Тема | Смысл |
|---:|---|---|
| #20 | DistributionExecutionTicket v1 | финальный Financial OS handoff перед MetaPay |
| #21 | DistributionAccounting v1 | settled principal как external capital, не P&L |
| #22 | Settlement Reversal Accounting v1 | возврат ранее выплаченного principal |
| #23 | BudgetState + AvailableCapacity v2 | anti-economic-replay и current capacity |
| #24 | Fee-budget Plan/Auth/Ticket v2 | external fee budget внутри authorization |
| #25 | Distribution Fee Accounting v2 | principal и фактическая fee отдельно |
| #26 | DistributionBudgetState v2 | fee-adjusted remaining profit budget |
| #27 | AvailableCapacity v3 | current fee-aware capacity |
| #28 | Plan/Auth/Ticket v3 | новое поколение handoff contracts |
| #29 | Distribution Accounting v3 | MetaPay v3 settlement accounting |
| #30 | Reversal Accounting v2 | principal refund / fee refund / new fee отдельно |
| #31 | BudgetState v3 | восстановление entitlement по canonical fee refund |
| #32 | AvailableCapacity v4 | terminal current distribution capacity |
| #33 | Canonicalization PR | terminal Economic OS lineage → `main` |
| #34 | EVM V2 RUBC/RUBX AI-CB | triangular HardTVL R&D |
| #35 | V2.3 fixed-200 flash settlement | external dividend / HardTVL R&D |
| #36 | V2.4 reflexive single-batch | marked-value vs hard-cash R&D |
| #37 | External Profit Bus consumer | MetaPay/DEX realized external P&L recognition |
| #38 | External Profit Import v1 | generic fail-closed importer |
| #39 | Federation V3 + AICB V5 | canonical accounting contracts / outbox / growth attestation |

Эти PR не следует механически merge'ить по номеру без повторной canonicalization review: часть из них stacked, часть исследовательская, часть появилась позже terminal lineage.

---

# 30. Federation V3 contract layer

В `federation-v3-domain-expansion` существует более компактный современный package:

```text
src/synergy_financial_os/
    contracts.py
    federation_outbox.py
```

Он содержит typed boundary objects, среди которых:

- `ReconciledTradingResult`;
- `ProjectUnderwritingDecision`;
- `BudgetAccountingRecognition`;
- `EligibleAssetGrowthAttestation`;
- `EmissionReleaseRecognition`;
- `FinancialCommitmentArtifact`.

Это не замена большой terminal Economic OS lineage, а новый Federation-facing контрактный слой.

Цель будущей канонизации — **не потерять зрелую accounting/state-machine историю terminal branch и не потерять строгую cross-repo типизацию Federation V3**.

---

# 31. Что Financial OS НЕ должен делать

Financial OS не является:

- брокером;
- торговой стратегией;
- CEX/DEX execution engine;
- платёжным маршрутизатором;
- банком сам по себе;
- эмитентом legal tender сам по себе;
- блокчейном;
- AI-агентом с правом переписывать ledger;
- источником «бесплатной прибыли» из mint/rebase/TVL.

Он должен оставаться **узким источником экономической истины**.

---

# 32. Связи с другими репозиториями СИНЕРГИИ

```text
synergy_app / synergy_matrix_sota
        ↓ household capital evidence

synergy_eurasian
        ↓ productive-project / physical evidence

midas_ai
        ↓ trading intent / realized outcome lineage

synergy_pay_system
        ↓ settlement / reconciliation

blochain_budget
        ↓ public-budget evidence

                    ┌─────────────────────────┐
                    │ SYNERGY FINANCIAL OS    │
                    │ canonical accounting    │
                    └─────────────────────────┘
                             │
                  accounting commitments
                             ↓
                  synergy_ai_blockchain
                             ↓
                    synergy_metachain
```

Дополнительно:

- `agi_nexus` / `agi_autopilot` — proposal/control layers, без accounting authority;
- `synergy_meta_os` — runtime orchestration;
- `synergynet` — transport;
- `ai_compress` — Data Fabric / archive compression;
- `ai_financial_system` — AI-CB / monetary / DeFi research lineage;
- `print_money_synergychain` — monetary/liquidity falsification research.

---

# 33. Репозиторная структура и где искать код

## `main`

Пока является landing/documentation branch и не должен восприниматься как доказательство, что вся terminal lineage уже канонически merged.

## Terminal Economic OS lineage

Ветка:

```text
feat/distribution-available-capacity-v4-refund-restored-20260828
```

Основные каталоги:

```text
.github/
config/
docs/
fixtures/
schemas/
sinergy_financial_os/
tests/
pyproject.toml
README.md
```

## Federation V3

Ветка:

```text
federation-v3-domain-expansion
```

Основные каталоги:

```text
.github/
docs/
src/synergy_financial_os/
tests/
pyproject.toml
```

## R&D monetary / HardTVL line

PR #34–#36 и связанные ветки.

## External Profit integration

PR #37–#38.

---

# 34. Тестирование

Репозиторий исторически использует большое количество:

- unit tests;
- schema validation;
- adversarial tests;
- replay/tampering tests;
- accounting balance tests;
- stale-state tests;
- authority tests;
- settlement/reversal tests;
- isolated CI workflows;
- simulation/fork-oriented research tests.

Для новых Federation V3 contract additions отдельный `Financial OS Contracts` workflow уже использовался для проверки Python contracts/tests.

**Нельзя считать весь репозиторий production-green только потому, что один isolated workflow зелёный.**

Перед канонизацией нужен единый CI, который одновременно проверит terminal lineage + Federation V3 + выбранные adapters.

---

# 35. Правильная стратегия канонизации в `main`

Не рекомендуется просто merge'ить подряд все PR #20–#39.

Правильнее собрать новую canonical integration branch:

```text
Terminal Economic OS lineage
        +
Federation V3 contract layer
        +
External Profit boundary
        +
AICB V5 Financial evidence
        -
research-only monetary engines from canonical core
        ↓
CANONICAL FINANCIAL OS RC
```

Этапы:

1. Зафиксировать terminal lineage commit.
2. Зафиксировать Federation V3 commit.
3. Построить inventory всех schemas/types и устранить semantic duplicates.
4. Сохранить старые schema generations immutable.
5. Подключить External Profit Import как отдельный consumer.
6. Подключить `EligibleAssetGrowthAttestation` и `EmissionReleaseRecognition`.
7. Объединить CI.
8. Прогнать ledger/accounting/distribution/reversal regressions.
9. Прогнать multi-repo MetaPay/MIDAS/Eurasian harness.
10. Только после этого поднимать RC в `main`.

---

# 36. Критерии готовности production-класса

Для перехода от research/sandbox к production недостаточно наличия кода.

Нужны как минимум:

- юридически определённый accounting/consolidation perimeter;
- chart of accounts;
- currency/FX policy;
- audit trail;
- immutable evidence retention;
- key management / signing policy;
- reconciliation SLAs;
- disaster recovery;
- access control;
- separation of duties;
- external audit;
- operational monitoring;
- settlement-provider contracts;
- custody model;
- incident response;
- jurisdiction-specific legal review;
- model-risk governance для AI;
- reproducible E2E evidence.

---

# 37. Главная экономическая идея Financial OS

СИНЕРГИЯ может экспериментировать с огромным количеством механизмов:

```text
MIDAS
MetaPay arbitrage
AI Central Bank
productive emission
AMM
flash liquidity
RUBC / RUBX
project finance
P2P credit
industrial investment
blockchain commitments
```

Но Financial OS должен превращать это многообразие в очень простой вопрос:

```text
Что произошло с реальными внешними активами,
обязательствами,
ликвидностью
и капиталом системы
после всех операций и всех расходов?
```

Если ответ невозможно доказать — Financial OS не должен дорисовывать прибыль.

Именно поэтому его роль в СИНЕРГИИ фундаментальна:

> **MIDAS может искать alpha. MetaPay может находить выгодный маршрут. AI-CB может предлагать эмиссию. Eurasian может строить производственную модель. Blockchain может фиксировать доказательство. Но только Financial OS должен определять каноническую бухгалтерскую интерпретацию уже подтверждённого события.**

---

# 38. Короткая формула системы

```text
EVIDENCE
   ↓
ACCOUNTING
   ↓
HARDNAV / LIQUIDITY / LIABILITIES
   ↓
RISK CAPACITY
   ↓
AUTHORIZED CAPITAL ACTION
   ↓
EXTERNAL SETTLEMENT
   ↓
RECONCILIATION
   ↓
NEW EVIDENCE
```

И главный firewall:

```text
NO EVIDENCE
    ↓
NO RECOGNITION
    ↓
NO DISTRIBUTION / RELEASE CLAIM
```

---

## Disclaimer

Этот репозиторий является исследовательским и инженерным проектом. Он сам по себе не предоставляет банковскую лицензию, право эмиссии законного платёжного средства, инвестиционную гарантию, custody approval, доступ к бирже или разрешение на оказание регулируемых финансовых услуг.

Любое live-развёртывание требует отдельного legal/compliance/security/custody/governance review в соответствующей юрисдикции.
