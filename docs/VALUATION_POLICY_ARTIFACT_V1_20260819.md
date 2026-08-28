# Portable valuation policy artifact v1 — 2026-08-19

`ValuationPolicy` already has a deterministic `valuation-policy/v1` canonical body and digest used by `FinancialSnapshot v2`.

This generation does not change those semantics. It packages the exact policy body into a portable `valuation.policy-artifact/v1` so an independent historical replay can reconstruct the same `ValuationRule` objects rather than receiving only a digest.

## Two hashes, two purposes

- `valuation_policy_digest` is the existing `ValuationPolicy.digest` and must match FinancialSnapshot v2.
- artifact `digest` hashes the complete portable wrapper, including generated-at/provenance authority fields.

Changing a haircut, price-source class, external-enforceability flag, intragroup-elimination flag, staleness limit or note changes the inner policy digest. Recomputing only the outer artifact hash cannot preserve an old FinancialSnapshot binding.

## Reconstructed fields

Each rule retains:

- valuation class;
- hard/liquid/economic factors;
- closed price-source class;
- external-enforceability requirement;
- intragroup-elimination requirement;
- maximum staleness;
- notes.

Decimal factors must use one canonical non-exponent representation. JSON integer/bool fields are type checked explicitly.

## Authority

The artifact has `REFERENCE_ONLY` valuation authority and no execution authority. It describes the already-selected policy; it cannot change policy or authorize valuation decisions.

## Restatement replay use

Together with `account.registry/v1`, this closes the two semantic inputs missing from RestatedPeriodView v1:

```
account.registry/v1
+ valuation.policy-artifact/v1
+ verified historical LedgerEvent v2 prefix
+ immutable original FinancialSnapshot / AccountingClose
+ RestatedPeriodView overlays
        ↓
future deterministic statement replay
```

The replay layer must require exact account-registry and valuation-policy digest equality with the immutable original FinancialSnapshot before calculating any restated metric.
