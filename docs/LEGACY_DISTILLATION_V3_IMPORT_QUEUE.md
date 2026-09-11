# LEGACY DISTILLATION V3 — synergy_financial_os

Assigned primitives:

- P001 ACCOUNTING_NAV_PNL — PROMOTE — ledger/PnL/NAV truth.
- P002 ACCOUNTING_NAV_PNL — PROMOTE — arb/accounting reconciliation lineage.
- P053 STAKING_REWARD — REWRITE — reward funding must remain externally funded and liability-aware.
- P057 TREASURY_RESERVE_CAPITAL — PROMOTE — reserve/capital truth.
- P058 TREASURY_RESERVE_CAPITAL — PROMOTE — vault/treasury sub-ledger lineage.

Non-negotiable gates: external assets minus external liabilities reconcile; own-token marks, self-LP, flash principal and scenario outputs cannot create HardNAV; reward liabilities cannot be counted as both treasury income and participant yield.
