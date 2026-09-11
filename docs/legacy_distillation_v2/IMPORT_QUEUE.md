# LEGACY DISTILLATION V2 — Import Queue

Canonical owner: `Shtenco/synergy_financial_os`

Nothing in this queue is auto-promoted to production. Every mechanism must pass the listed gate in this repository authority boundary.

| Priority | ID | Family | Action | Occurrences | Test gate | Representative |
|---|---|---|---|---:|---|---|
| P0_PROMOTE_WITH_GATE | M180 | TREASURY_RESERVE_CAPITAL | PROMOTION_CANDIDATE | 145 | `treasury_reconciliation` | addToReserveR |
| P0_PROMOTE_WITH_GATE | M181 | TREASURY_RESERVE_CAPITAL | PROMOTION_CANDIDATE | 133 | `treasury_reconciliation` | traderReserve |
| P1_PROMOTE_WITH_GATE | M001 | ACCOUNTING_NAV_PNL | PROMOTION_CANDIDATE | 65 | `double_entry_conservation` | swap |
| P1_REWRITE | M168 | STAKING_REWARD | FALSIFICATION_FIXTURE_OR_REWRITE | 26 | `reward_funding_source` | stake |
| P1_REWRITE | M169 | STAKING_REWARD | REWRITE_REQUIRED | 21 | `reward_funding_source` | reward_fee |
| P1_PROMOTE_WITH_GATE | M002 | ACCOUNTING_NAV_PNL | PROMOTION_CANDIDATE | 53 | `double_entry_conservation` | pnl |
| P1_PROMOTE_WITH_GATE | M182 | TREASURY_RESERVE_CAPITAL | PROMOTION_CANDIDATE | 35 | `treasury_reconciliation` | aggregate_capital |
| P1_REWRITE | M004 | ACCOUNTING_NAV_PNL | FALSIFICATION_FIXTURE_OR_REWRITE | 14 | `double_entry_conservation` | recordArbResult |
| P1_PROMOTE_WITH_GATE | M183 | TREASURY_RESERVE_CAPITAL | PROMOTION_CANDIDATE | 31 | `treasury_reconciliation` | addToMcgFund |
| P1_PROMOTE_WITH_GATE | M003 | ACCOUNTING_NAV_PNL | PROMOTION_CANDIDATE | 19 | `double_entry_conservation` | _distributeProfit |
| P1_REWRITE | M170 | STAKING_REWARD | REWRITE_REQUIRED | 5 | `reward_funding_source` | CASRG_INFINITE |
| P1_REWRITE | M184 | TREASURY_RESERVE_CAPITAL | FALSIFICATION_FIXTURE_OR_REWRITE | 5 | `treasury_reconciliation` | step |
| P1_PROMOTE_WITH_GATE | M005 | ACCOUNTING_NAV_PNL | PROMOTION_CANDIDATE | 5 | `double_entry_conservation` | getInvariant |
