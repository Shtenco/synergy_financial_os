from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.accounting_restatement_view_v1 import (
    AccountingRestatementOverlayV1,
    RestatedPeriodViewV1,
)


ROOT = Path(__file__).resolve().parents[1]
OVERLAY_SCHEMA = ROOT / "schemas/accounting_restatement_overlay_v1.schema.json"
VIEW_SCHEMA = ROOT / "schemas/restated_period_view_v1.schema.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def overlay():
    return AccountingRestatementOverlayV1(
        overlay_id="overlay-001",
        affected_period_id="period-n",
        correction_target_period_id="period-n-plus-2",
        original_period_close_digest="11" * 32,
        original_accounting_close_digest="22" * 32,
        original_ledger_event_digest="33" * 32,
        original_reporting_entry_digest="44" * 32,
        correction_authorization_digest="55" * 32,
        period_chain_proof_digest="66" * 32,
        correction_period_close_digest="77" * 32,
        correction_accounting_close_digest="88" * 32,
        correction_ledger_event_digest="99" * 32,
        correction_reporting_entry_digest="aa" * 32,
        generated_at=dt("2026-08-19T14:00:00Z"),
    )


def view():
    item = overlay()
    return RestatedPeriodViewV1(
        view_id="view-001",
        affected_period_id=item.affected_period_id,
        original_period_close_digest=item.original_period_close_digest,
        overlay_digests=(item.digest,),
        excluded_reporting_entry_digests=(item.original_reporting_entry_digest,),
        view_version=1,
        generated_at=dt("2026-08-19T14:10:00Z"),
    )


def test_runtime_payloads_validate_against_strict_schemas():
    jsonschema.Draft202012Validator(load(OVERLAY_SCHEMA)).validate(overlay().to_dict())
    jsonschema.Draft202012Validator(load(VIEW_SCHEMA)).validate(view().to_dict())


def test_overlay_schema_locks_presentation_only_authority():
    schema = load(OVERLAY_SCHEMA)
    for field, value in (
        ("presentation_action", "REWRITE_ORIGINAL_ENTRY"),
        ("authority", "ACCOUNTING_MUTATION"),
        ("original_history_mutation", "ALLOWED"),
        ("execution_authority", "WRITE"),
    ):
        bad = copy.deepcopy(overlay().to_dict())
        bad[field] = value
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(bad)


def test_view_schema_rejects_invented_metrics_and_unsafe_version():
    schema = load(VIEW_SCHEMA)
    bad = view().to_dict()
    bad["recalculated_financial_metrics"] = "HARDNAV_RECALCULATED"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(bad)
    bad = view().to_dict()
    bad["view_version"] = 9007199254740992
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(bad)
