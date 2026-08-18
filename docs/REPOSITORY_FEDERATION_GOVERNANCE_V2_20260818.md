# SINERGY Repository Federation Governance V2 — 2026-08-18

## Purpose

The project is intentionally a federation of repositories, not a monorepo. V2 makes repository authority machine-readable so historical experiments, public surfaces, temporary compute branches and current domain roots cannot silently exchange roles.

The existing `config/repository-federation.yaml` is preserved as v1 documentation. V2 is added beside it as `config/repository_federation_v2.json`.

## Core principle

A repository may contain useful code, CI, artifacts or historical experiments without becoming authoritative for the economic meaning of those artifacts.

Repository location does not create authority.

Examples:

- a training job in `synergychain.github.io` does not make the public Pages repository an AI-policy authority;
- a Polygon fork in a historical public branch does not make that repository the accounting authority;
- an AMM/QE experiment in `ai_financial_system` does not override Financial OS profit recognition;
- a trust-layer commitment does not approve a project;
- an OLGA/NEXUS proposal does not execute monetary policy.

## Exclusive authorities

The v2 registry assigns one owner to each domain authority.

- accounting, NAV/profit, monetary/risk constitution and capital-allocation screening: `synergy_financial_os`;
- household maturity schedule: `synergy_matrix_sota`;
- payment routing, settlement and reconciliation: `synergy_pay_system`;
- real-economy project model: `synergy_eurasian`;
- trust commitments: `synergy_ai_blockchain`;
- AI policy proposals: `agi_olga`;
- requirement semantics: `ai_language`;
- lossless archive/compression: `ai_compress`;
- engineering orchestration: `ai_coder`;
- portal/control plane: `synergychain`;
- public static surface: `synergychain.github.io`.

Research and lineage repositories remain first-class preserved sources but do not gain financial authority merely by containing executable code.

## Public and temporary compute repositories

`synergychain.github.io` has accumulated legitimate temporary build, Android, model-training and research branches. They are preserved. V2 classifies such use as non-authoritative compute/artifact activity.

The same rule applies to historical CI branches in `shtencoauantai.github.io` and provenance content in `shtenco.github.io`.

No deletion is required to regain architectural clarity; the federation registry supplies the missing semantic boundary.

## New repository rule

A new repository should be created only when a genuinely new domain requires an exclusive authority that cannot be cleanly assigned to an existing root. A new implementation, model version, benchmark, UI or temporary workflow is not sufficient reason by itself.

This prevents repository sprawl while preserving the user's requirement that old generations remain intact.

## Verification status

The accompanying test validates the exact 16-repository set, unique authority ownership, public-surface restrictions, non-execution status of AI/trust layers, deny-by-default MetaPay execution boundary and mandatory history preservation.

Presence of tests is not equivalent to executed verification. Until GitHub Actions actually assigns a runner and completes the workflow, status remains `PENDING_RUNNER`.
