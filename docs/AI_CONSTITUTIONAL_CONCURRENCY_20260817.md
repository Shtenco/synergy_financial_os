# SINERGY Financial OS — AI constitutional concurrency boundary

Status: **additive draft hardening note**. Historical OLGA/NEXUS models and `ai.policy-proposal/v1` remain preserved.

## Problem

Binding an AI proposal only to a financial snapshot is insufficient.

A proposal can reference:

```text
REQ-FIN-009
```

but the meaning of that requirement may later change while the identifier stays the same.

Therefore two independent concurrency dimensions exist:

```text
financial state concurrency
constitutional state concurrency
```

## `ai.policy-proposal/v2` binding

The current draft proposal binds:

```text
input_snapshot_digest
input_ledger_sequence
input_valuation_policy_digest
input_requirement_registry_digest
expires_at
```

and carries:

```text
authorization = NONE
```

## Review rule

Financial OS receives the **current full requirement registry object**.

It independently derives:

```text
known REQ-* identifiers
SHA-256 of the full canonical registry
```

from that same object.

This prevents a caller from supplying:

```text
IDs from registry A
+ digest from registry B
```

## Stale conditions

Any mismatch produces `STALE` rather than execution:

```text
snapshot digest changed
ledger sequence changed
valuation policy changed
requirement registry changed
proposal expired
```

Changing only the statement text under an unchanged requirement ID changes the registry digest and therefore invalidates the old proposal.

## Unknown requirement references

If the proposal's bound registry digest equals the current registry digest, every `hard_invariant_ref` must actually exist in that registry.

Therefore:

```text
REQ-FAKE-999
```

is rejected even though it is syntactically shaped like a requirement ID.

## Invariant failures

Even an otherwise current proposal is `BLOCKED` when the current `financial.snapshot/v2` already contains invariant failures.

## Authority ceiling

The strongest positive review state is:

```text
REVIEWABLE
```

Never:

```text
APPROVED
EXECUTABLE
AUTHORIZED
```

A later governed policy/execution object must be a different schema with its own authority, signer and evidence rules.

## Implementation

Central Financial OS:

- `sinergy_financial_os/governance.py`
- `sinergy_financial_os/ai_boundary.py`
- `tests/test_governance.py`
- `tests/test_ai_boundary.py`

AI schema authority:

- `Shtenco/agi_olga/integration/policy_proposal_v2.schema.json`

Runner verification remains pending until the configured CI runner actually executes the tests.
