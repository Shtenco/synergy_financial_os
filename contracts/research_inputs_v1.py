from __future__ import annotations
from typing import Any

BRIDGE_HEALTH_CONTRACT_ID = "synergy.economy.bridge-health/v1"
SCENARIO_EVIDENCE_CONTRACT_ID = "synergy.economy.scenario-evidence/v1"


def consume_bridge_health(payload: dict[str, Any]) -> dict[str, Any]:
    hf = int(payload.get("health_factor_bps", -1))
    if hf < 0:
        raise ValueError("invalid health factor")
    status = str(payload.get("status", "")).upper()
    if status not in {"HEALTHY", "BELOW_TARGET", "EMERGENCY_STOP"}:
        raise ValueError("unknown bridge health status")
    if bool(payload.get("accounting_authority")):
        raise ValueError("bridge telemetry cannot claim accounting authority")
    return {
        "kind": "BRIDGE_HEALTH",
        "observation_id": str(payload["observation_id"]),
        "health_factor_bps": hf,
        "status": status,
        "canonical_accounting": False,
        "capital_authorization": False,
    }


def consume_scenario_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status", "")).upper()
    if status not in {"SCENARIO", "STRESS", "COUNTERFACTUAL"}:
        raise ValueError("scenario evidence status required")
    digest = str(payload.get("evidence_digest", "")).lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid scenario evidence digest")
    for field in ("accounting_authority", "settlement_authority", "capital_authorization"):
        if bool(payload.get(field)):
            raise ValueError(f"{field} must remain false")
    return {
        "kind": "SCENARIO_EVIDENCE",
        "scenario_id": str(payload["scenario_id"]),
        "status": status,
        "evidence_digest": digest,
        "canonical_accounting": False,
        "settlement_authority": False,
        "capital_authorization": False,
    }
