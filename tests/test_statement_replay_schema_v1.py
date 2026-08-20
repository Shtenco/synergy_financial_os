from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.statement_replay_contract_v1 import verify_statement_replay_payload_v1
from sinergy_financial_os.statement_replay_v1 import StatementReplayV1, StatementReplayV1Error


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/statement_replay_v1.schema.json").read_text(encoding="utf-8"))
H = "ab" * 32


def sample() -> StatementReplayV1:
    return StatementReplayV1(
        replay_id="replay-schema-001",
        affected_period_id="period-1",
        original_period_close_digest=H,
        original_accounting_close_digest="ac" * 32,
        original_financial_snapshot_digest="ad" * 32,
        opening_period_close_digest="ae" * 32,
        opening_accounting_close_digest="af" * 32,
        account_registry_artifact_digest="b0" * 32,
        account_registry_digest="b1" * 32,
        valuation_policy_artifact_digest="b2" * 32,
        valuation_policy_digest="b3" * 32,
        restated_period_view_digest="b4" * 32,
        overlay_digests=("b5" * 32,),
        excluded_reporting_entry_digests=("b6" * 32,),
        opening_sequence=1,
        closing_sequence=2,
        original_event_count=2,
        retained_event_count=1,
        excluded_event_count=1,
        replayed_ledger_digest="b7" * 32,
        replayed_last_entry_digest="b8" * 32,
        hard_external_assets=Decimal("100"),
        liquid_haircut_assets=Decimal("100"),
        economic_haircut_assets=Decimal("100"),
        external_liabilities=Decimal("0"),
        hard_nav=Decimal("100"),
        liquid_nav=Decimal("100"),
        economic_nav=Decimal("100"),
        realized_external_revenue=Decimal("0"),
        realized_external_pnl=Decimal("0"),
        generated_at=datetime(2026, 8, 20, 3, 0, tzinfo=UTC),
    )


def test_schema_and_runtime_accept_same_canonical_payload():
    payload = sample().to_dict()
    jsonschema.Draft202012Validator(SCHEMA).validate(payload)
    verified = verify_statement_replay_payload_v1(payload)
    assert verified.digest == payload["digest"]
    assert verified.hard_nav == Decimal("100")


def test_noncanonical_decimal_fails_even_if_outer_digest_is_recomputed():
    payload = sample().to_dict()
    payload["hard_nav"] = "100.0"
    body = dict(payload)
    body.pop("digest")
    import hashlib
    payload["digest"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    with pytest.raises((StatementReplayV1Error, jsonschema.ValidationError)):
        jsonschema.Draft202012Validator(SCHEMA).validate(payload)
        verify_statement_replay_payload_v1(payload)


def test_unsafe_sequence_and_forbidden_liquidity_claim_fail_closed():
    unsafe = sample().to_dict()
    unsafe["closing_sequence"] = 9_007_199_254_740_992
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(SCHEMA).validate(unsafe)

    claimed = sample().to_dict()
    claimed["liquidity_metrics"] = "CALCULATED"
    with pytest.raises((StatementReplayV1Error, jsonschema.ValidationError)):
        jsonschema.Draft202012Validator(SCHEMA).validate(claimed)
        verify_statement_replay_payload_v1(claimed)
