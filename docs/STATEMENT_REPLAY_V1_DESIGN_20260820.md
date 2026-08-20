# Deterministic Statement Replay v1 — design note

This note defines the next additive accounting generation. It does not modify any historical ledger, close, snapshot, restatement view, account registry, or valuation policy.

Goal: independently replay one immutable accounting period from content-addressed inputs and calculate only metrics whose full semantic inputs are available.

Required evidence:
- `account.registry/v1` matching `FinancialSnapshot v2.account_registry_digest`;
- `valuation.policy-artifact/v1` matching `FinancialSnapshot v2.valuation_policy_digest`;
- the exact genesis-based `ledger.event/v2` prefix sealed by the period `accounting.close/v2`;
- the immutable `accounting.period/v1` and `accounting.period-close/v1`;
- if the period is not the genesis period, the exact opening `accounting.period-close/v1` and its `accounting.close/v2`, used only to derive the opening ledger sequence;
- `accounting.restated-period-view/v1` plus its `accounting.restatement-overlay/v1` objects.

The original full prefix is verified first against AccountingClose v2 and the original FinancialSnapshot v2. Restatement never changes this proof.

A derived replay ledger is then created from `account.registry/v1`. Every verified LedgerEvent v2 is replayed in original order except ReportingEntry digests explicitly excluded by the RestatedPeriodView. The derived ledger has its own new digest chain; it never claims to be the original historical ledger.

Period boundary:
- genesis period: opening sequence = 0;
- later period: opening sequence = previous AccountingClose v2.event_count;
- closing sequence = current AccountingClose v2.event_count;
- period P&L/revenue are calculated only from original ledger-event positions `(opening_sequence, closing_sequence]` that survive the restatement treatment.

V1 recalculates:
- hard external assets;
- liquid haircut assets;
- economic haircut assets;
- external liabilities;
- HardNAV;
- LiquidNAV;
- EconomicNAV;
- realized external revenue for the affected period;
- realized external P&L for the affected period.

V1 deliberately does NOT recalculate LCR, liquidity horizons, distribution capacity, retained-profit policy, maturity state, or tax jurisdiction policy. Those require additional independently replayable inputs.

Authority is `FINANCIAL_OS_REPLAY_DERIVATION`; ledger mutation and execution authority remain `NONE`.