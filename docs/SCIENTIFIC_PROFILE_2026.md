# SYNERGY Financial OS — scientific profile of canonical accounting

## Key original architectural idea

**A financial fact belongs to one canonical authority and must be justified by reconciled external evidence.** Trading signals, simulation results, blockchain token valuations and user interfaces may propose interpretations, but they must not self-certify revenue, NAV or authorization to distribute capital. This project forms the accounting boundary inside a multi-repository AI and financial architecture.

The [recognition contract](../contracts/accounting_recognition_v1.py) accepts only explicitly reconciled settled events when settlement information is supplied. It classifies revenue, expense, transfers, liability changes, trading PnL, capital flow and non-recognized items. The journal checks debits and credits by asset with exact Decimal arithmetic. The [research-input contract](../contracts/research_inputs_v1.py) explicitly prevents monetary simulations and bridge telemetry from claiming settlement or capital authority.

## Mathematical foundation

For each denomination a, double-entry balance requires:

$$
\sum_{j \in D(a)}v_j=\sum_{j \in C(a)}v_j.
$$

This is an accounting balance invariant, **not proof** that both sides describe genuine external transfers. External evidence, legal entitlement and control of obligations are separate conditions. For a conservative net asset view, assets and enforceable liabilities should be recognised under consistent valuation and settlement policy:

$$
NAV_{\mathrm{external}}=A_{\mathrm{eligible}}-L_{\mathrm{recognized}}.
$$

A token exchange on an internal controlled venue cannot increase externally realizable capital solely through a change in internal mark price.

## Implemented evidence boundary

- Accounting payloads include settlement event ID, recognition UUID, classification, accounting period, policy references and separately named hard/liquid/economic NAV deltas.
- Settlement reconciliation checks exclude unresolved breaks before recognition.
- Simulation-only payloads cannot assert realised external profit.
- Bridge health and scenario reports remain informative research inputs, not ledger authority.
- The full existing README describes a broader federated target architecture, multiple historical branches and integration planning. Those sections remain unchanged.

## Application and scientific programme

The most valuable use case is an **independent audit-grade economic truth layer** for payment rails, algorithmic trading, autonomous agents and token economies. A rigorous test suite should include asset-specific double-entry balance, idempotency, duplicate settlement denial, conflicting evidence, unexpected negative exposures, valuation independence from internal prices and downstream capital distribution limits.

For future production use, distinguish **reconciled external funds**, **accounting recognized PnL**, **capital legally available for use**, and **AI recommendations**. This separation is the system's principal scientific and commercial differentiator.

[Recognition contract](../contracts/accounting_recognition_v1.py) · [Research inputs](../contracts/research_inputs_v1.py) · [Tests](../tests/test_accounting_recognition_contract.py)
