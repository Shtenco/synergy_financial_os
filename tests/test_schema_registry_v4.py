import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "config/schema_registry_v3.json"
V4 = ROOT / "config/schema_registry_v4.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v3_registry_remains_present_and_v4_is_overlay() -> None:
    assert V3.exists()
    assert _load(V3)["schema"] == "sinergy.schema-registry/v3"
    v4 = _load(V4)
    assert v4["schema"] == "sinergy.schema-registry/v4"
    assert v4["base_registry"] == "config/schema_registry_v3.json"
    assert v4["evolution_policy"] == "APPEND_ONLY_OVERLAY"


def test_v4_supersedes_only_named_generations() -> None:
    v4 = _load(V4)
    mapping = {item["schema_id"]: item["superseded_by"] for item in v4["supersessions"]}
    assert mapping == {
        "settlement.receipt/v1": "settlement.receipt/v2",
        "economic.cycle-trace/v2": "economic.cycle-trace/v3",
    }


def test_v4_assigns_settlement_and_trace_authority_to_correct_repositories() -> None:
    v4 = _load(V4)
    additions = {item["schema_id"]: item for item in v4["additions"]}
    receipt = additions["settlement.receipt/v2"]
    trace = additions["economic.cycle-trace/v3"]
    assert receipt["schema_authority"] == "Shtenco/synergy_pay_system"
    assert receipt["producer"] == "Shtenco/synergy_pay_system"
    assert "Shtenco/synergy_financial_os" in receipt["consumers"]
    assert "does not recognize profit" in receipt["authority_note"]
    assert trace["schema_authority"] == "Shtenco/synergy_financial_os"
    assert trace["producer"] == "Shtenco/synergy_financial_os"
    assert "cannot execute transactions or recognize profit" in trace["authority_note"]
