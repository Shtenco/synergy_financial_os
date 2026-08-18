import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_registry_v8_is_append_only_over_v7_and_tracks_latest_accounting_bridge() -> None:
    registry = json.loads((ROOT / "config/schema_registry_v8.json").read_text(encoding="utf-8"))
    assert registry["schema"] == "sinergy.schema-registry/v8"
    assert registry["base_registry"] == "config/schema_registry_v7.json"
    assert registry["evolution_policy"] == "APPEND_ONLY_OVERLAY"
    added = {item["schema_id"] for item in registry["additions"]}
    assert {
        "ledger.event/v2",
        "accounting.close/v2",
        "ledger.inclusion-proof/v2",
        "economic.cycle-trace/v6",
    } <= added
    superseded = {item["schema_id"]: item["superseded_by"] for item in registry["supersessions"]}
    assert superseded["ledger.event/v1"] == "ledger.event/v2"
    assert superseded["accounting.close/v1"] == "accounting.close/v2"
    assert superseded["ledger.inclusion-proof/v1"] == "ledger.inclusion-proof/v2"
    assert superseded["economic.cycle-trace/v5"] == "economic.cycle-trace/v6"
