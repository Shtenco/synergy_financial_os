import pytest

from sinergy_financial_os import AccountingInvariantError, requirement_ids_from_registry


def _registry(requirements=None) -> dict:
    return {
        "schema": "sinergy.requirement-registry/v1",
        "as_of": "2026-08-17",
        "default_verification_status": "PENDING_RUNNER",
        "requirements": requirements
        if requirements is not None
        else [
            {"id": "REQ-FIN-001", "statement": "balanced"},
            {"id": "REQ-AI-002", "statement": "snapshot bound"},
        ],
    }


def test_valid_requirement_registry_returns_known_ids() -> None:
    ids = requirement_ids_from_registry(_registry())
    assert ids == frozenset({"REQ-FIN-001", "REQ-AI-002"})


def test_wrong_registry_schema_fails_closed() -> None:
    registry = _registry()
    registry["schema"] = "sinergy.requirement-registry/v999"
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(registry)


def test_duplicate_requirement_ids_fail_closed() -> None:
    registry = _registry(
        [
            {"id": "REQ-FIN-001"},
            {"id": "REQ-FIN-001"},
        ]
    )
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(registry)


def test_non_req_identifier_fails_closed() -> None:
    registry = _registry([{"id": "FIN-001"}])
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(registry)


def test_empty_requirement_registry_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(_registry([]))


def test_non_object_requirement_item_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(_registry(["REQ-FIN-001"]))
