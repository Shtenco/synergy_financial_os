# Adoption decisions from `ai_financial_system` Financial OS V4/V5

Source reference: `Shtenco/ai_financial_system`, branch `feat/financial-os-v4-20260809`.

This document records which ideas are deliberately salvaged, tightened or separated in the new canonical federation root. The source branch remains unchanged and authoritative for its own historical evidence.

## 1. What is retained

From `financial_os_v4/accounting.py`:

- an append-only double-entry ledger;
- explicit account classes;
- normal-balance calculation;
- trial-balance conservation;
- monotonic sequence;
- flow classification such as external capital, external revenue, liability issuance/redemption, credit origination/repayment/loss and settlement;
- external-vs-internal distinction;
- reporting-unit financial statements;
- deterministic canonical-state digest;
- explicit recognition that browser prices and internal token marks cannot silently become HardNAV.

From `snapshot_v2.py`:

- ledger sequence + digest binding;
- Hard/Liquid/Economic NAV ordering;
- external liabilities and immediate liabilities;
- capital-flow-adjusted distributable profit;
- realized external revenue;
- maturity/unlock information;
- nullable coverage ratios rather than non-finite JSON values;
- policy mode + invariant failures.

## 2. What is tightened

### Decimal-only canonical arithmetic

The new reference core does not convert canonical monetary results to binary `float` merely for convenience. Decimal/native integer representation is preferred until a presentation boundary explicitly needs a float.

### Duplicate identity

A canonical event id/reference must not silently accept a different payload. Duplicate identities are rejected unless a future explicit idempotency layer proves byte-for-byte/economic equivalence.

### Valuation policy separated from account registration

V4 placed haircut factors directly on `AccountSpec`. The new root separates:

```text
ChartOfAccounts
ValuationPolicy
LedgerEvents
FinancialSnapshot
```

so a haircut/source/staleness change is an explicit versioned policy change rather than a silent account-definition mutation.

### Consolidation class explicit

The new chart distinguishes `EXTERNAL`, `INTRA_GROUP` and `MEMO`. Intra-group claims are eliminated before consolidated external NAV.

### Own-issued instruments explicit

Own-issued instruments and internal claims receive zero consolidated valuation factors in the reference valuation engine.

## 3. Native operational state vs reporting ledger

This is the most important structural separation.

`synergy_pay_system` correctly keeps a multi-asset operational ledger and balances each asset independently. FX routes use clearing/settlement structure rather than summing unlike currencies.

The canonical financial statement ledger, by contrast, must be in an explicitly declared reporting unit after approved valuation/translation.

Therefore the federation has two layers:

```text
native operational events / settlement evidence
        |
        v
approved FX/valuation translation + accounting policy
        |
        v
reporting-currency double-entry ledger
        |
        v
HardNAV / LiquidNAV / EconomicNAV / profit / coverage
```

The existing `AppendOnlyJournal` in the new root is a native-unit conservation primitive. It is not by itself the reporting ledger from which consolidated NAV should be computed.

## 4. Maturity and LCR separation

V4 `FinancialSnapshotV2` correctly computed LCR only after combining maturity outflows with a liquid reserve. The new federation strengthens the ownership boundary:

- `synergy_matrix_sota` emits pure maturity/funding-liability state;
- `synergy_financial_os` combines that state with liquid assets/inflows/stress buffers and computes LCR.

Thus a household funding subsystem never claims an LCR without knowing the asset side.

## 5. Flow evidence

Flow types remain useful but are not sufficient evidence by themselves. An event labeled `EXTERNAL_REVENUE` must also have admissible external evidence/settlement provenance. Classification cannot create revenue.

## 6. Next canonical step

The new root should implement a small Decimal reporting ledger with:

- registered account specs;
- one reporting currency;
- balanced entries;
- explicit flow type;
- evidence/reference binding;
- duplicate rejection;
- canonical digest;
- no embedded market-price lookup;
- NAV calculation delegated through versioned valuation policy.

This is an adaptation of V4 research, not a replacement or deletion of it.
