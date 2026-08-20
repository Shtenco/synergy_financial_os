# Distribution Plan and Authorization v1

The distribution path is intentionally split into three authorities:

1. `distribution.capacity-replay/v1` — mathematical upper bound only;
2. `distribution.plan/v1` — exact beneficiary/payment batch, no approval;
3. `distribution.authorization/v1` — human/multisig decision, no execution.

## DistributionPlan v1

A plan binds one exact current capacity and liquidity replay and freezes:

- affected accounting period;
- same reporting/distribution currency;
- source account;
- every beneficiary id;
- every destination id;
- every beneficiary amount;
- every payment idempotency key;
- beneficiary-set digest;
- total amount;
- exact capacity limit.

The plan is deterministic and sorted by beneficiary id. Beneficiary ids and idempotency keys are unique. Total amount must be positive and must not exceed the exact current capacity.

V1 usage policy is `SINGLE_EXACT_BATCH`. Partial execution and FX conversion are deliberately unsupported until a separate utilization protocol exists.

## DistributionAuthorization v1

Decision authority is limited to:

- HUMAN_COMMITTEE;
- MULTISIG_GOVERNANCE.

AI authority is always `NONE`.

An APPROVED authorization must approve exactly the plan total. A REJECTED authorization approves zero.

The authorization binds:

- exact Plan digest;
- exact CapacityReplay digest;
- exact LiquidityReplay digest;
- affected period;
- currency;
- source account;
- beneficiary-set digest;
- requirement-registry digest;
- approver-policy digest;
- decision-evidence digest;
- decision and expiry times.

`execution_authority = SEPARATE_METAPAY_BATCH_HANDOFF`.

## Staleness

Before handoff, the current bundle is rechecked. Any of the following invalidates the authorization:

- changed beneficiary/destination/amount/idempotency key;
- changed plan digest;
- changed capacity replay;
- capacity no longer available;
- plan exceeds new capacity;
- changed liquidity replay;
- changed requirement registry;
- changed approver policy;
- expired/not-yet-valid authorization.

A changed destination with a newly recomputed valid plan hash is still stale relative to the old authorization and requires a new human/multisig decision.

## Next boundary

Authorization still does not prove one-time execution. The next generation belongs to MetaPay:

`DistributionAuthorization -> exact batch handoff -> settlement receipts -> utilization/consumption record`

A one-time authorization must not be replayable as a second economic payout even when each individual payment has a new execution attempt id.