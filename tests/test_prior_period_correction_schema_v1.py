from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.prior_period_correction_v1 import PriorPeriodCorrectionAuthorizationV1


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/prior_period_correction_authorization_v1.schema.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def payload():
    return PriorPeriodCorrectionAuthorizationV1(
        authorization_id="prior-error-void-001",
        affected_period_id="period-n",
        target_period_id="period-n-plus-2",
        reason="DUPLICATE_ENTRY",
        original_period_close_digest="11" * 32,
        original_accounting_close_digest="22" * 32,
        original_ledger_event_digest="33" * 32,
        original_reporting_entry_digest="44" * 32,
        period_chain_proof_digest="55" * 32,
        correction_evidence_digest="66" * 32,
        decision_evidence_digest="77" * 32,
        accounting_policy_digest="88" * 32,
        requirement_registry_digest="99" * 32,
        decision_authority="MULTISIG_GOVERNANCE",
        decided_at=dt("2026-08-19T12:10:00Z"),
        effective_at=dt("2026-08-19T12:20:00Z"),
    ).to_dict()


def test_runtime_payload_validates_against_schema():
    jsonschema.Draft202012Validator(load(SCHEMA)).validate(payload())


def test_schema_locks_scope_current_pnl_and_ai_authority():
    schema = load(SCHEMA)
    for field, value in (
        ("correction_scope", "PARTIAL_REWRITE"),
        ("current_period_pnl_treatment", "CURRENT_PERIOD_EXPENSE"),
        ("ai_authority", "NEXUS"),
    ):
        bad = copy.deepcopy(payload())
        bad[field] = value
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(bad)
