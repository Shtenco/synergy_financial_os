import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_REPOSITORY = "Shtenco/synergy_financial_os"


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_schema_registry_has_unique_schema_ids() -> None:
    registry = _load("config/schema_registry_v1.json")
    assert registry["schema"] == "sinergy.schema-registry/v1"
    ids = [item["schema_id"] for item in registry["schemas"]]
    assert len(ids) == len(set(ids))


def test_schema_supersession_targets_exist_and_do_not_self_reference() -> None:
    registry = _load("config/schema_registry_v1.json")
    by_id = {item["schema_id"]: item for item in registry["schemas"]}
    for item in registry["schemas"]:
        target = item["superseded_by"]
        if target is None:
            continue
        assert target in by_id
        assert target != item["schema_id"]


def test_local_schema_registry_paths_exist() -> None:
    registry = _load("config/schema_registry_v1.json")
    for item in registry["schemas"]:
        if item["schema_authority"] == LOCAL_REPOSITORY:
            assert (ROOT / item["path"]).is_file(), item


def test_financial_snapshot_v1_is_preserved_and_explicitly_superseded() -> None:
    registry = _load("config/schema_registry_v1.json")
    by_id = {item["schema_id"]: item for item in registry["schemas"]}
    old = by_id["financial.snapshot/v1"]
    new = by_id["financial.snapshot/v2"]
    assert old["status"] == "SUPERSEDED_DRAFT"
    assert old["superseded_by"] == "financial.snapshot/v2"
    assert new["status"] == "DRAFT_CANONICAL_CANDIDATE"
    assert (ROOT / old["path"]).is_file()
    assert (ROOT / new["path"]).is_file()


def test_project_proposal_v1_is_preserved_and_v2_is_registered_side_by_side() -> None:
    registry = _load("config/schema_registry_v1.json")
    by_id = {item["schema_id"]: item for item in registry["schemas"]}
    old = by_id["project.proposal/v1"]
    new = by_id["project.proposal/v2"]
    assert old["status"] == "SUPERSEDED_DRAFT"
    assert old["superseded_by"] == "project.proposal/v2"
    assert new["status"] == "DRAFT_DOMAIN_SCHEMA"
    assert new["superseded_by"] is None
    assert old["schema_authority"] == new["schema_authority"] == "Shtenco/synergy_eurasian"


def test_ai_policy_v1_is_preserved_and_v2_is_registered_side_by_side() -> None:
    registry = _load("config/schema_registry_v1.json")
    by_id = {item["schema_id"]: item for item in registry["schemas"]}
    old = by_id["ai.policy-proposal/v1"]
    new = by_id["ai.policy-proposal/v2"]
    assert old["status"] == "SUPERSEDED_DRAFT"
    assert old["superseded_by"] == "ai.policy-proposal/v2"
    assert new["status"] == "DRAFT_DOMAIN_SCHEMA"
    assert new["superseded_by"] is None
    assert old["schema_authority"] == new["schema_authority"] == "Shtenco/agi_olga"


def test_requirement_ids_are_unique_and_namespaced() -> None:
    registry = _load("config/requirement_registry_v1.json")
    assert registry["schema"] == "sinergy.requirement-registry/v1"
    ids = [item["id"] for item in registry["requirements"]]
    assert len(ids) == len(set(ids))
    assert all(item.startswith("REQ-") for item in ids)


def test_local_requirement_implementations_and_tests_exist() -> None:
    registry = _load("config/requirement_registry_v1.json")
    for item in registry["requirements"]:
        if item["owner"] != LOCAL_REPOSITORY:
            continue
        for path in item["implementation"]:
            assert (ROOT / path).exists(), (item["id"], path)
        for path in item["tests"]:
            assert (ROOT / path).is_file(), (item["id"], path)


def test_pending_runner_registry_does_not_claim_verified_execution() -> None:
    registry = _load("config/requirement_registry_v1.json")
    assert registry["default_verification_status"] == "PENDING_RUNNER"
    forbidden = {"VERIFIED", "PASS", "PRODUCTION_VERIFIED"}
    for item in registry["requirements"]:
        if item["verification_status"] == "PENDING_RUNNER":
            assert item["verification_status"] not in forbidden


def test_schema_owners_producers_and_consumers_are_explicit() -> None:
    registry = _load("config/schema_registry_v1.json")
    for item in registry["schemas"]:
        assert item["schema_authority"].startswith("Shtenco/")
        assert item["producer"].startswith("Shtenco/")
        assert item["consumers"]
        assert all(consumer.startswith("Shtenco/") for consumer in item["consumers"])


def test_hardening_controls_use_their_own_namespace_not_req_ids() -> None:
    matrix = _load("config/federation_hardening_matrix_v1.json")
    assert matrix["schema"] == "sinergy.federation-hardening-matrix/v1"
    ids = [item["control_id"] for item in matrix["controls"]]
    assert len(ids) == len(set(ids))
    assert ids
    assert all(control_id.startswith("HARDEN-") for control_id in ids)
    assert all(not control_id.startswith("REQ-") for control_id in ids)


def test_hardening_requirement_refs_resolve_to_real_canonical_requirements() -> None:
    matrix = _load("config/federation_hardening_matrix_v1.json")
    registry = _load("config/requirement_registry_v1.json")
    known = {item["id"] for item in registry["requirements"]}
    for control in matrix["controls"]:
        refs = control["canonical_requirement_refs"]
        assert isinstance(refs, list)
        assert len(refs) == len(set(refs))
        assert set(refs) <= known, control


def test_hardening_matrix_does_not_claim_runner_verification() -> None:
    matrix = _load("config/federation_hardening_matrix_v1.json")
    for control in matrix["controls"]:
        assert control["repository"].startswith("Shtenco/")
        assert control["implementation_status"] == "ADDRESSED"
        assert control["verification_status"] == "PENDING_RUNNER"
        assert control["implementation"]
        assert control["tests"]
