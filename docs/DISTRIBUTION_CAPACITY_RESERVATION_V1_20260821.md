# Distribution Capacity Reservation / Commitment State v1

## Problem closed by this generation

`distribution.available-capacity/v2` closes economic replay across sequential payout cycles, but a concurrency race remains if two different Plans are created/authorized against the same current capacity before either settlement reaches canonical accounting.

Example:

```text
current available capacity = 8
Plan A = 8
Plan B = 8
```

Single-use Authorization protects A from being replayed and B from being replayed, but does not by itself prevent both distinct authorizations from consuming the same 8 at the same time.

V1 adds a non-accounting commitment layer between current capacity and authorization.

## Authority separation

A reservation is **not** a ReportingLedger entry. It does not change P&L, NAV, equity or cash.

It is a temporary risk/commitment claim that says part of the currently available distribution capacity has been promised and cannot be promised again until the reservation is settled/accounted or safely released.

```text
accounting_authority = COMMITMENT_ONLY
authorization_authority = REFERENCE_ONLY on aggregate state
payment_authority = NONE
execution_authority = NONE
AI authority = NONE
```

## 1. `distribution.capacity-reservation/v1`

One reservation is immutable-by-version and bound to:

- exact future/desired Plan digest;
- affected period;
- reporting/distribution currency;
- exact `distribution.available-capacity/v2` basis;
- exact current snapshot/ledger digest and sequence;
- exact reserved amount;
- TTL.

Lifecycle:

```text
ACTIVE
  ├─> RELEASED_EXPIRED
  └─> ATTEMPTED
        ├─> RELEASED_TERMINAL_FAILED
        └─> SETTLED_PENDING_ACCOUNTING
              └─> ACCOUNTED
```

Each version increments by one and binds `previous_reservation_digest`.

Skipping a lifecycle stage is invalid even when each individual object has a valid digest.

## 2. `distribution.commitment-state/v1`

The aggregate state binds one exact current available-capacity object and the latest version digest of every reservation.

For one currency domain:

```text
outstanding_commitments
  = sum(latest reservation.outstanding_amount)

remaining_authorizable_capacity
  = max(0,
        current_available_capacity
        - outstanding_commitments)
```

If outstanding commitments exceed a newly reduced current capacity, the state becomes `NO_ACTION` with blocker:

```text
OUTSTANDING_COMMITMENTS_EXCEED_CURRENT_CAPACITY
```

If current available-capacity itself is `NO_ACTION`, commitment state remains representable but cannot create or start new distribution attempts.

## Concurrent reservation example

```text
current available capacity = 8

reserve Plan A = 5
outstanding = 5
remaining authorizable = 3

reserve Plan B = 4
=> rejected

reserve Plan B = 3
outstanding = 8
remaining authorizable = 0
```

Thus two distinct authorizations cannot serially reserve 16 against the same 8 in the reference state machine.

Production must enforce the same transition with durable transactional compare-and-swap; see the deployment boundary below.

## Partial settlement

Suppose one exact batch reserves 8 and MetaPay terminal utilization says:

```text
settled = 3
failed remainder = 5
```

Reservation becomes:

```text
SETTLED_PENDING_ACCOUNTING
settled_amount = 3
outstanding_amount = 3
```

The failed 5 are released immediately. The settled 3 remain reserved until canonical Financial OS accounting posts the actual owner distribution.

This prevents the settlement-to-accounting gap from creating temporary duplicate capacity.

## Accounting reconciliation

A reservation is not allowed to become `ACCOUNTED` merely because a caller provides a 64-character entry digest.

Canonical reconciliation verifies the current ReportingLedger and requires the referenced entry to be exactly:

```text
FlowType.EXTERNAL_CAPITAL
economic_class = OWNER_DISTRIBUTION
affected_period_id = reservation.affected_period_id
distribution_plan_digest = reservation.plan_digest
distribution_utilization_digest = reservation.utilization_digest

Dr external equity
Cr external cash
amount == reservation.settled_amount
```

The refreshed `distribution.available-capacity/v2` must bind that exact ReportingLedger sequence/digest and must be based on a later closed ledger than the reservation's pre-payout basis.

Until that refreshed close/capacity exists, the settled amount stays outstanding. Delayed accounting can therefore only make the system more conservative, never create extra authorization capacity.

## Terminal failure

A terminal MetaPay utilization with zero settlement transitions:

```text
ATTEMPTED -> RELEASED_TERMINAL_FAILED
outstanding_amount = 0
```

This releases capacity, but it does **not** revive the consumed DistributionAuthorization. A later retry requires a new Plan/Reservation/Authorization cycle.

## Expiry

Only an unattempted `ACTIVE` reservation may be released by TTL expiry.

Once an attempt exists, expiry cannot release the commitment because settlement may still be in flight. The reservation must wait for a terminal utilization result.

## Capacity deterioration

An existing reservation survives capacity refresh. If current capacity falls below total outstanding commitments:

```text
outstanding > current available capacity
```

new attempts are blocked. Existing settlement/accounting outcomes can still be recorded so the system can recover deterministically.

## Currency domain

One commitment book cannot aggregate outstanding reservations of different reporting currencies. Nominal USD and KZT amounts are never added together.

A future multi-currency coordinator may maintain one independent commitment domain per reporting currency and consolidate risk only through explicit valuation/oracle policy.

## Production concurrency boundary

`DistributionCommitmentBookV1` is a reference serial in-memory state machine for deterministic tests and protocol specification. It is **not** production distributed locking.

Live deployment must preserve at least these storage invariants transactionally:

1. unique `reservation_id`;
2. unique active/reserved Plan digest;
3. compare-and-swap on `previous_commitment_state_digest` / state version;
4. durable latest reservation version per reservation id;
5. atomic outstanding-capacity calculation + reservation insert;
6. no payment handoff before that transaction commits.

Recommended production primitive:

```text
BEGIN SERIALIZABLE
  read current commitment_state FOR UPDATE
  verify expected previous_state_digest
  verify current available-capacity basis
  verify remaining_authorizable_capacity >= plan total
  insert immutable reservation v1
  insert next commitment_state version
COMMIT
```

Only after COMMIT may DistributionAuthorization v2 / ExecutionTicket v2 be considered usable.

## Next generation

The next layer is:

```text
DistributionPlan v2
        ↓ exact digest
CapacityReservation ACTIVE
        ↓
DistributionAuthorization v2
        ↓
ExecutionTicket v2
        ↓
MetaPay attempt
```

Authorization v2 must bind both the exact Plan v2 digest and exact ACTIVE reservation digest / commitment-state digest. A plan without a committed reservation must not be executable.
