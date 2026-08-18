# LedgerEvent v2 -> AccountingClose v2 -> EconomicCycleTrace v6

This generation closes the gap between the operational/audit LedgerEvent object and the internal ReportingLedger state captured by FinancialSnapshot v2.

## Why v1 was insufficient

`ledger.event/v1` preserved journal lines and recognition evidence, while `FinancialSnapshot v2` preserved the internal `ReportingLedger.digest` and `ledger_last_entry_digest`. The two were not the same hash domain, so a Merkle root of LedgerEvent v1 values did not independently prove that its final event was the ReportingEntry chain head used by the snapshot.

## V2 bridge

`ledger.event/v2` adds:

- `previous_reporting_entry_digest`;
- `reporting_entry_digest`;
- canonical reconstruction of the ReportingEntry body;
- balance validation;
- canonical decimal/time validation;
- closed FlowType validation.

`accounting.close/v2` seals a strict genesis-based prefix (`sequence = 1..N`) of LedgerEvent v2 objects and requires:

- `event_count == FinancialSnapshot.sequence`;
- the ReportingEntry digest chain to start at the genesis digest;
- the final LedgerEvent `reporting_entry_digest == FinancialSnapshot.ledger_last_entry_digest`;
- event reporting currency to match the snapshot;
- every sealed event to be no later than the snapshot;
- exact FinancialSnapshot digest, ledger digest, account-registry digest and valuation-policy digest to be copied into the close;
- one domain-separated Merkle root over the exact LedgerEvent v2 bytes.

`ledger.inclusion-proof/v2` proves both the target LedgerEvent v2 digest and its underlying ReportingEntry digest against that close root.

## Trace v6

The latest non-circular trace has twelve phases and ends with:

1. `LEDGER_EVENT -> ledger.event/v2`
2. `ACCOUNTING_SNAPSHOT -> financial.snapshot/v2`
3. `ACCOUNTING_CLOSE -> accounting.close/v2`
4. `LEDGER_INCLUSION_PROOF -> ledger.inclusion-proof/v2`

Trust remains external: `trust_finalization = EXTERNAL_COMMITMENT_REQUIRED`.

Trace v6 additionally checks the economic posting shape of recognized revenue. A fresh-hash attacker cannot change 125 gross / 118 recognized / 5 tax / 2 refund into another balanced journal while retaining the same RevenueRecognition v2 root: the gross debit and exact positive-credit component multiset are independently compared with the recognition decision.

## Canonical vector

- ReportingEntry: `f38f6ce7c8a23bea46b95681b21aa490af7b8b1797252ec6645f76c2c3eb6086`
- LedgerEvent v2: `6711f4bc972b8c36f8866ba747c6458cf3165deaf5e1e66c0209f89edf9b2776`
- FinancialSnapshot v2: `cc90650d55d69b6e2066c00f2590e2faf7b991de75fb3d277a1da7b8d741ae1b`
- AccountingClose v2: `aa880abd2c32fd4ef6a6360e46ea802f224d91e66f3154f5ae175f60796d6617`
- LedgerInclusionProof v2: `111f446397399b9a4213226e7924dbc7964a4de1711431ac07f895333ed910cf`
- EconomicCycleTrace v6: `566b1570f55b4327270e94fbbc0fec61a3c5618b327dc432ac9b366e6a2657c2`

## Authority boundary

LedgerEvent is an audit projection. AccountingClose is a Financial OS sealing fact. InclusionProof and EconomicCycleTrace are provenance-only. None of them authorizes payments, recognizes new revenue, posts new ledger entries, changes a closed period, or grants AI financial authority.
