# AccountingClose v1 + LedgerInclusionProof v1

This layer is additive. FinancialSnapshot v2, ReportingLedger and prior trace generations remain unchanged.

`AccountingClose v1` seals a specific contiguous prefix of canonical `ledger.event/v1` objects and binds that prefix to one exact `financial.snapshot/v2` digest.

The ledger root uses explicit domain separation:

- leaf: `SHA256("SINERGY_LEDGER_LEAF_V1\\0" || canonical_json(event))`;
- node: `SHA256("SINERGY_LEDGER_NODE_V1\\0" || left || right)`;
- odd tree levels duplicate the last node deterministically.

The close also binds event count, first/last sequence, close time, valuation-policy digest and requirement-registry digest.

`LedgerInclusionProof v1` proves that one exact LedgerEvent belongs to the sealed root. A changed event cannot reuse an old proof; a rebuilt root cannot claim an old AccountingClose digest.

Neither object executes transactions or recognizes revenue. The close is a Financial OS sealing fact; the proof is provenance-only.
