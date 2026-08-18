# Revenue recognition v2 and EconomicCycleTrace v4

This layer is additive. ReportingLedger, SettlementReceipt v1/v2, RevenueRecognition v1 draft and EconomicCycleTrace v1-v3 remain intact.

## Why settlement is not revenue

A reconciled project payment proves that value settled. It does not by itself prove external consolidated revenue. Financial OS v2 recognition therefore requires a separate accounting decision bound to:

- exact SettlementReceipt v2;
- CapitalAuthorization v2/project lineage;
- ProjectEvidence v1;
- exact payer/counterparty and expected revenue destination;
- counterparty externality/KYB evidence;
- contract and invoice evidence;
- invoice amount ceiling;
- separate delivery/performance evidence;
- performance-obligation status;
- dispute/chargeback/refund state;
- reporting currency and external FX evidence when required;
- tax amount, refund reserve and accounting-policy digest.

`INTRA_GROUP` is rejected as external revenue. `UNKNOWN` or `EXTERNAL_RELATED` is conservatively deferred in v2. Unsatisfied performance or open chargeback is deferred. A refunded payment is rejected.

## Canonical example

125 USDC settled from the verified external customer:

- gross reporting amount: 125;
- tax liability: 5;
- refund reserve liability: 2;
- recognized external revenue: 118.

Canonical RevenueRecognition v2 digest:
`422f66737f129a3b714c16a1212287dc0ccf243efa51c4ce1a7eb65cd56fbfa3`

## Double entry

The canonical posting wrapper re-runs recognition from raw receipt/auth/request evidence immediately before posting. It does not accept a caller-supplied decision object.

For the canonical example:

- Dr external cash 125;
- Cr external revenue 118;
- Cr tax liability 5;
- Cr refund reserve liability 2.

The resulting ReportingEntry is exported side-by-side as `ledger.event/v1`; its `evidence_digest` is exactly the RevenueRecognition v2 digest.

Canonical LedgerEvent digest:
`1dcf75a6084615c4a8c3dcdcf04a820ee25311900a7a4f5ade858e6711263771`

## EconomicCycleTrace v4

V4 adds explicit `REVENUE_RECOGNITION` and `LEDGER_EVENT` phases and moves the latest trust phase to `commitment.envelope/v3`.

A complete V4 trace verifies the arrows:

`revenue receipt -> recognition -> reporting entry/ledger event -> accounting snapshot -> trust commitment`.

Trace verification still has no execution authority. It references accounting facts; it does not create them.

Canonical complete trace v4 digest:
`fc43178e61c1a117786a31d73d22b00ee18cd2fc22c98f47aa884b0dd8ccd0cc`
