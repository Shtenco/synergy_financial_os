# Distribution Execution Ticket v1

`distribution.execution-ticket/v1` is the final Financial OS gate before MetaPay receives an approved distribution batch.

It is intentionally separate from both DistributionAuthorization and payment execution.

## Creation

At `verified_at`, Financial OS re-runs the complete current bundle check:

- exact DistributionPlan digest;
- exact DistributionCapacityReplay digest;
- exact LiquidityReplay digest;
- plan total <= current capacity;
- exact beneficiary-set digest;
- exact source account/currency;
- current requirement-registry digest;
- current approver-policy digest;
- DistributionAuthorization TTL.

A ticket is produced only if that check is clean.

## TTL

The ticket has its own expiry and may never outlive the underlying human/multisig DistributionAuthorization.

## Authority

`authority = FINANCIAL_OS_EXECUTION_HANDOFF_GATE`

`payment_authority = METAPAY_ONLY`

`execution_authority = NONE`

`ai_authority = NONE`

The ticket therefore means only:

> Financial OS re-verified this exact batch under current state and is handing it to MetaPay.

It does not reserve funds, execute payments, prove settlement, or consume the authorization.

## Next boundary

MetaPay must create a one-time exact batch attempt from the ticket. The attempt/utilization protocol must prevent the same DistributionAuthorization from being economically consumed twice, even if a second caller presents the same still-valid ticket.