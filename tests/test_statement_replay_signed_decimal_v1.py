from decimal import Decimal
import json
from pathlib import Path

import jsonschema

from sinergy_financial_os.statement_replay_v1 import StatementReplayV1

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/statement_replay_v1.schema.json").read_text(encoding="utf-8"))


def test_negative_fractional_pnl_is_canonical_and_schema_valid():
    replay = StatementReplayV1(
        replay_id="fractional",
        affected_period_id="period",
        original_period_close_digest="10"*32,
        original_accounting_close_digest="11"*32,
        original_financial_snapshot_digest="12"*32,
        opening_period_close_digest="13"*32,
        opening_accounting_close_digest="14"*32,
        account_registry_artifact_digest="15"*32,
        account_registry_digest="16"*32,
        valuation_policy_artifact_digest="17"*32,
        valuation_policy_digest="18"*32,
        restated_period_view_digest="19"*32,
        overlay_digests=("1a"*32,),
        excluded_reporting_entry_digests=("1b"*32,),
        opening_sequence=1,
        closing_sequence=2,
        original_event_count=2,
        retained_event_count=1,
        excluded_event_count=1,
        replayed_ledger_digest="1c"*32,
        replayed_last_entry_digest="1d"*32,
        hard_external_assets=Decimal("1"),
        liquid_haircut_assets=Decimal("1"),
        economic_haircut_assets=Decimal("1"),
        external_liabilities=Decimal("0"),
        hard_nav=Decimal("1"),
        liquid_nav=Decimal("1"),
        economic_nav=Decimal("1"),
        realized_external_revenue=Decimal("0"),
        realized_external_pnl=Decimal("-0.5"),
        generated_at=__import__("datetime").datetime(2026,8,20,3,0,tzinfo=__import__("datetime").UTC),
    )
    payload = replay.to_dict()
    assert payload["realized_external_pnl"] == "-0.5"
    jsonschema.Draft202012Validator(SCHEMA).validate(payload)
