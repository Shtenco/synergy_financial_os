# SettlementReceipt v2 — Financial OS consumer boundary

This layer is additive. `settlement.receipt/v1`, legacy settlement adapters, CapitalAuthorization v1/v2 and prior EconomicCycleTrace generations remain present.

Financial OS treats MetaPay receipts as external evidence, never as accounting authority.

For productive capital funding, a v2 receipt is accepted as causal evidence only when it matches the authoritative `CapitalAuthorizationV2` on:

- project id;
- authorization digest;
- exact funding source;
- exact funding destination;
- source asset;
- exact authorized source amount;
- payment idempotency key;
- payment purpose.

For project revenue, Financial OS verifies project + authorization + project-evidence lineage. This is deliberately **not** revenue recognition. External-counterparty/invoice/contract/economic-classification evidence remains a separate accounting gate.

A recomputed receipt hash cannot legitimize altered economics because Financial OS independently compares the receipt to its own authoritative objects.
