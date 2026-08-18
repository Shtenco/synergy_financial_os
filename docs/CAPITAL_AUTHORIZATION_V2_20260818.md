# SINERGY CapitalAuthorization V2 — 2026-08-18

## Why v2 exists

`capital.authorization/v1` correctly separated project screening from payment execution, but it authorized only project + asset + amount. A payment could still be constructed with another payer/payee while retaining matching project metadata.

V2 is additive and leaves v1 unchanged. It binds one exact funding payment scope into the authorization bytes:

- `funding_source_id`;
- `funding_destination_id`;
- `payment_idempotency_key`;
- `payment_purpose = productive_capital_funding`;
- `usage_policy = SINGLE_EXACT_PAYMENT`.

It also adds `approver_policy_digest`, so a change to human committee / multisig quorum policy makes an existing authorization stale.

## Usage boundary

V2 deliberately supports one exact payment only. Partial drawdowns, multiple disbursements or revolving use require a separate utilization ledger and a later schema version. They are not inferred implicitly.

## Authority boundary

Decision authority remains limited to HUMAN_COMMITTEE or MULTISIG_GOVERNANCE. AI authority is `NONE`. Execution authority remains `SEPARATE_METAPAY_HANDOFF`.

Financial OS decides whether capital may be allocated. MetaPay separately verifies that the PaymentIntent matches the exact authorized payer, payee, asset, amount, purpose, idempotency key, project and authorization digest before its own compliance/readiness/liquidity/execution pipeline.

## Concurrency binding

The authorization remains bound to the exact FinancialSnapshot digest + sequence, valuation-policy digest and requirement-registry digest. V2 additionally binds the exact approver-policy digest. Any mismatch blocks the handoff.

## Canonical fixture

`fixtures/conformance/capital_authorization_v2_canonical.json`

Digest:

`1e814153a18850865543e08b498b60d9bce80dbd34bfb2f4c378f3fe502fe89f`

## Non-destructive evolution

V1 remains available for provenance and previous conformance work. V2 is a new draft candidate and does not rewrite the v1 module, schema, fixture or tests.
