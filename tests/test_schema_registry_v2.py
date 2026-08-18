import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V1_PATH = ROOT / "config/schema_registry_v1.json"
V2_PATH = ROOT / "config/schema_registry_v2.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v1_registry_remains_present_as_provenance() -> None:
    assert V1_PATH.exists()
    assert _load(V1_PATH)["schema"] == "sinergy.schema-registry/v1"


def test_v2_schema_ids_are_unique() -> None:
    registry = _load(V2_PATH)
    ids = [item["schema_id"] for item in registry["schemas"]]
    assert len(ids) == len(set(ids))


def test_superseded_generations_remain_registered_with_successors() -> None:
    registry = _load(V2_PATH)
    by_id = {item["schema_id"]: item for item in registry["schemas"]}
    expected = {
        "financial.snapshot/v1": "financial.snapshot/v2",
        "project.proposal/v1": "project.proposal/v2",
        "ai.policy-proposal/v1": "ai.policy-proposal/v2",
        "commitment.envelope/v1": "commitment.envelope/v2",
    }
    for old, new in expected.items():
        assert by_id[old]["status"] == "SUPERSEDED_DRAFT"
        assert by_id[old]["superseded_by"] == new
        assert new in by_id


def test_new_engineering_and_usds_contracts_have_correct_authorities() -> None:
    by_id = {item["schema_id"]: item for item in _load(V2_PATH)["schemas"]}
    engineering = by_id["engineering.change-set/v1"]
    usds = by_id["usds.experiment-result/v1"]
    assert engineering["schema_authority"] == "Shtenco/ai_coder"
    assert engineering["producer"] == "Shtenco/ai_coder"
    assert "no merge" in engineering["authority_note"].lower()
    assert usds["schema_authority"] == "Shtenco/usds"
    assert usds["producer"] == "Shtenco/usds"
    assert usds["consumers"] == ["Shtenco/synergy_financial_os"]
    assert "only Financial OS" in usds["authority_note"]


def test_semantic_binding_and_archive_contracts_have_narrow_authority() -> None:
    by_id = {item["schema_id"]: item for item in _load(V2_PATH)["schemas"]}
    binding = by_id["requirement.binding/v1"]
    archive = by_id["archive.manifest/v1"]
    assert binding["schema_authority"] == "Shtenco/ai_language"
    assert binding["producer"] == "Shtenco/ai_language"
    assert set(binding["consumers"]) == {
        "Shtenco/ai_coder",
        "Shtenco/synergy_financial_os",
    }
    assert "does not review code" in binding["authority_note"]
    assert archive["schema_authority"] == "Shtenco/ai_compress"
    assert archive["producer"] == "Shtenco/ai_compress"
    assert "do not gain current financial" in archive["authority_note"]


def test_commitment_v2_does_not_claim_financial_authority() -> None:
    by_id = {item["schema_id"]: item for item in _load(V2_PATH)["schemas"]}
    commitment = by_id["commitment.envelope/v2"]
    assert commitment["schema_authority"] == "Shtenco/synergy_ai_blockchain"
    assert "not financial authorization" in commitment["authority_note"]
