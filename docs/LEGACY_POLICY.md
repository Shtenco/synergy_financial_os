# Immutable Legacy Policy

SINERGY repositories use additive evolution. Historical code, simulations, contracts, benchmark artifacts, failed experiments and negative controls are preserved as provenance.

## Rules

1. Do not delete historical mechanisms merely because a later architecture supersedes them.
2. Do not rewrite old evidence to make it conform to newer accounting rules.
3. Add new canonical behavior through additive files, branches, adapters, manifests and versioned schemas.
4. Every reused mechanism must carry its source repository, source ref/commit, claim-specific evidence status and current accounting interpretation.
5. Negative controls and falsified hypotheses are first-class evidence.
6. A legacy mechanism may be operationally useful without being accepted as a source of HardNAV or profit.
7. Public-facing repositories are presentation surfaces, not accounting authority.
8. Historical snapshots should be content-addressed where practical.

## Claim statuses

`LEGACY`, `EXPERIMENTAL`, `VERIFIED_SIM`, `FORK_VERIFIED`, `CANONICAL`, `PRODUCTION`.

Status is claim-specific. For example, a route executor can be `FORK_VERIFIED` for atomic execution while the associated profitability hypothesis remains `EXPERIMENTAL`.

## Canonical precedence

When historical and current mechanisms conflict, the new system does not erase history. It records the conflict and applies the current constitutional rule for new decisions.
