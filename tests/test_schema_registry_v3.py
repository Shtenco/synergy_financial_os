import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "config/schema_registry_v2.json"
V3 = ROOT / "config/schema_registry_v3.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v2_registry_is_preserved_and_v3_is_overlay_only() -> None:
    assert V2.exists()
    v2 = _load(V2)
    v3 = _load(V3)
    assert v2["schema"] == "sinergy.schema-registry/v2"
    assert v3["schema"] == "sinergy.schema-registry/v3"
    assert v3["base_registry"] == "config/schema_registry_v2.json"
    assert v3["evolution_policy"] == "APPEND_ONLY_OVERLAY"


def test_v3_supersessions_point_to_new_additions_without_deleting_old_ids() -> None:
    v2_ids = {item["schema_id"] for item in _load(V2)["schemas"]}
    v3 = _load(V3)
    additions = {item["schema_id"]: item for item in v3["additions"]}
    expected = {
        "capital.authorization/v1": "capital.authorization/v2",
        "economic.cycle-trace/v1": "economic.cycle-trace/v2",
    }
    for item in v3["supersessions"]:
        old = item["schema_id"]
        new = item["superseded_by"]
        assert old in v2_ids
        assert item["new_status"] == "SUPERSEDED_DRAFT"
        assert expected[old] == new
        assert new in additions


def test_v3_addition_ids_are_unique_and_not_already_present_in_v2() -> None:
    v2_ids = {item["schema_id"] for item in _load(V2)["schemas"]}
    additions = _load(V3)["additions"]
    ids = [item["schema_id"] for item in additions]
    assert len(ids) == len(set(ids))
    assert set(ids).isdisjoint(v2_ids)


def test_capital_authorization_v2_keeps_financial_and_execution_authority_separate() -> None:
    additions = {item["schema_id"]: item for item in _load(V3)["additions"]}
    auth = additions["capital.authorization/v2"]
    assert auth["schema_authority"] == "Shtenco/synergy_financial_os"
    assert "Shtenco/synergy_pay_system" in auth["consumers"]
    note = auth["authority_note"].lower()
    assert "ai cannot authorize" in note
    assert "execution remains metapay-owned" in note


def test_cycle_trace_v2_remains_provenance_only() -> None:
    additions = {item["schema_id"]: item for item in _load(V3)["additions"]}
    trace = additions["economic.cycle-trace/v2"]
    note = trace["authority_note"].lower()
    assert "provenance-only" in note
    assert "cannot execute" in note
    assert "recognize profit" in note
