# SINERGY Capital Authorization + Economic Cycle Trace V1 — 2026-08-18

## Why this layer exists

The federation intentionally made `project.screening/v1` non-authorizing. `REVIEWABLE` means a project may proceed to underwriting/governance review; it must never silently turn into a payment.

That creates a necessary explicit boundary:

```text
Project Screening
    -> Capital Authorization
    -> MetaPay Funding Handoff
```

This branch adds that missing decision record and then uses it inside a strict cross-repository economic-cycle trace.

## CapitalAuthorization v1

A capital authorization is a Financial OS record bound to:

- exact project screening digest;
- exact FinancialSnapshot digest and ledger sequence;
- exact valuation-policy digest;
- exact requirement-registry digest;
- immutable decision evidence;
- funding asset and approved amount;
- decision time and expiration time.

Decision authority is limited to `HUMAN_COMMITTEE` or `MULTISIG_GOVERNANCE`. AI authority is structurally `NONE`.

The record does not contain an execute method and locks:

```text
execution_authority = SEPARATE_METAPAY_HANDOFF
```

Before handoff, current snapshot/sequence/valuation/constitution and TTL are checked again. A changed state makes the authorization stale rather than allowing a previously approved decision to execute against new conditions.

## EconomicCycleTrace v1

The trace contains no monetary calculation. It is a content-addressed causal chain of domain facts.

The required full cycle is:

```text
1 FUNDING_STATE
  maturity.snapshot/v1
  synergy_matrix_sota

2 PROJECT_PROPOSAL
  project.proposal/v2
  synergy_eurasian

3 PROJECT_SCREENING
  project.screening/v1
  synergy_financial_os

4 CAPITAL_AUTHORIZATION
  capital.authorization/v1
  synergy_financial_os

5 FUNDING_SETTLEMENT
  settlement.receipt/v1
  synergy_pay_system

6 PROJECT_EVIDENCE
  project.evidence/v1
  synergy_eurasian

7 REVENUE_SETTLEMENT
  settlement.receipt/v1
  synergy_pay_system

8 ACCOUNTING_SNAPSHOT
  financial.snapshot/v2
  synergy_financial_os

9 TRUST_COMMITMENT
  commitment.envelope/v2
  synergy_ai_blockchain
```

References must form a strict causal prefix. A later phase cannot exist in the trace while an earlier mandatory boundary is missing. Observation time cannot move backwards. Project-domain references must bind the same project identity.

## What COMPLETE means

`TRACE_COMPLETE` means all nine required fact classes are present in causal order.

It does **not** mean:

- the project was profitable;
- the investment should be repeated;
- distributable profit exists;
- a payment is authorized;
- a legal/regulatory approval exists.

The trace is permanently:

```text
authority = PROVENANCE_ONLY
profit_recognition = NOT_PERFORMED
execution_authority = NONE
```

Financial profit remains a Financial OS ledger/P&L conclusion. Settlement remains MetaPay-owned. Trust commitments remain evidence of bytes, not economic authorization.

## Non-destructive evolution

This work is stacked above repository-federation/schema-registry v2. No v1 schema, historical Financial OS module, R&D experiment or existing consumer is deleted or rewritten. Future capital-decision/trace generations should be added side-by-side.
