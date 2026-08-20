# Distribution Accounting v1

This layer converts MetaPay distribution settlement evidence into Financial OS accounting without misclassifying owner/participant distributions as operating expense or realized loss.

## Input evidence

Financial OS independently verifies:

- `distribution.plan/v1`;
- `distribution.authorization/v1`;
- `distribution.execution-ticket/v1`;
- `distribution.batch-attempt/v1`;
- one `distribution.settlement-receipt/v1` per planned beneficiary;
- `distribution.utilization/v1`.

It recomputes each MetaPay intent-binding digest from the exact Plan/Auth/Ticket context rather than trusting the digest field.

Only receipts with `status=SETTLED` contribute to accounting outflow. Failed/reversed legs contribute zero.

## Operational account mapping

MetaPay `source_account_id` is not assumed to equal a ReportingLedger account id.

`DistributionAccountingAccountsV1` explicitly binds:
- operational payment source;
- ReportingLedger external cash account;
- ReportingLedger external equity/distribution account;
- one source-account-mapping evidence digest.

Financial OS verifies cash is EXTERNAL ASSET and distribution account is EXTERNAL EQUITY.

## Decision

`distribution.accounting-decision/v1` is POSTABLE only when:
- settled total > 0;
- reported cash balance is sufficient;
- distribution-equity balance is sufficient;
- all execution evidence is internally congruent.

The decision has no ledger mutation or execution authority.

## Canonical posting

The canonical posting function re-runs the complete raw evidence evaluation immediately before `ReportingLedger.post()`.

For actual settled amount D:

`Dr Distribution Equity D`

`Cr External Cash D`

with:

- `FlowType.EXTERNAL_CAPITAL`;
- `economic_class=OWNER_DISTRIBUTION`;
- `capital_direction=OUTFLOW`;
- `pnl_treatment=EXCLUDED_FROM_REALIZED_PNL`.

This produces a negative signed net-capital contribution and a lower HardNAV/cash balance without creating current-period operating expense or negative realized P&L.

## Partial settlement

If an approved batch of 18 settles only 10, Financial OS posts only 10. The failed 8 does not become an accounting liability or expense automatically. Any remaining intended distribution requires a new Financial OS Plan/Capacity/Authorization cycle.

## Replay protection

The ledger entry uses `reference=distribution.utilization.digest`. ReportingLedger reference uniqueness therefore prevents the same utilization artifact from being posted twice.

## Future reversal

A distribution that was SETTLED and later externally reversed/compensated requires a separate distribution-reversal accounting generation. V1 does not silently reinterpret an already posted settled distribution.