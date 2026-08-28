# Content-addressed account registry v1 — 2026-08-19

`FinancialSnapshot v2` already binds `account_registry_digest`, and `ReportingLedger.account_registry_digest` already hashes the sorted canonical account specifications.

That digest proves identity but does not contain the account specifications needed for an independent historical replay.

`account.registry/v1` does **not** change the existing digest definition. It packages the exact canonical account specifications whose hash is already used by ReportingLedger and FinancialSnapshot.

## Two distinct digests

The artifact intentionally exposes two hashes:

1. `account_registry_digest` — SHA-256 of the sorted list of `ReportingAccountSpec.canonical_dict()` objects. This must equal the pre-existing `ReportingLedger.account_registry_digest` and the value stored in `FinancialSnapshot v2`.
2. `digest` — SHA-256 of the complete portable `account.registry/v1` artifact, including reporting currency, generation time and authority metadata.

The second hash does not replace the first.

## Reconstructible semantics

For every account the artifact preserves:

- account id;
- human-readable name;
- `AccountClass`;
- `ConsolidationClass`;
- valuation class;
- immediate-liability flag;
- derived normal side.

A verifier reconstructs real `ReportingAccountSpec` objects, checks `normal_side`, recomputes the original account-registry digest and can instantiate an empty ReportingLedger with the identical frozen chart semantics.

## Authority boundary

The registry is a Financial OS accounting-definition artifact, but it cannot mutate a ledger and cannot execute financial actions.

It also does not contain balances. Balances are derived from verified ledger events.

## Why this is required for historical restatement replay

A restated-period presentation currently knows which historical ReportingEntry must be excluded, but a digest alone cannot answer whether an account is an external asset, intra-group claim, liability, revenue or expense.

With this artifact, the future deterministic replay inputs become reconstructible:

```
account.registry/v1
+ valuation-policy/v1
+ original LedgerEvent v2 prefix
+ original FinancialSnapshot / AccountingClose
+ RestatedPeriodView overlays
        ↓
replay ledger under the same chart semantics
        ↓
restated comparative metrics
```

A future replay layer must still fail closed if the supplied registry digest differs from the immutable original FinancialSnapshot.
