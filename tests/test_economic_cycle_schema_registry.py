import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config/schema_registry_v2.json"


def _by_id() -> dict[str, dict]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["schema_id"]: item for item in registry["schemas"]}


def test_project_evidence_is_owned_by_eurasian_and_consumed_by_financial_os() -> None:
    evidence = _by_id()["project.evidence/v1"]
    assert evidence["schema_authority"] == "Shtenco/synergy_eurasian"
    assert evidence["producer"] == "Shtenco/synergy_eurasian"
    assert "Shtenco/synergy_financial_os" in evidence["consumers"]


def test_capital_authorization_is_separate_from_screening_and_payment_execution() -> None:
    schemas = _by_id()
    authorization = schemas["capital.authorization/v1"]
    screening = schemas["project.screening/v1"]
    assert authorization["schema_authority"] == "Shtenco/synergy_financial_os"
    assert screening["schema_authority"] == "Shtenco/synergy_financial_os"
    assert "Shtenco/synergy_pay_system" in authorization["consumers"]
    note = authorization["authority_note"].lower()
    assert "ai cannot authorize" in note
    assert "cannot execute payment" in note


def test_economic_cycle_trace_is_provenance_not_profit_or_execution() -> None:
    trace = _by_id()["economic.cycle-trace/v1"]
    assert trace["schema_authority"] == "Shtenco/synergy_financial_os"
    assert set(trace["consumers"]) == {
        "Shtenco/synergychain",
        "Shtenco/synergy_ai_blockchain",
        "Shtenco/ai_language",
    }
    note = trace["authority_note"].lower()
    assert "cannot execute" in note
    assert "recognize profit" in note
