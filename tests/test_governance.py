import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    requirement_ids_from_registry,
    requirement_registry_digest,
)


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


def test_requirement_registry_digest_is_deterministic() -> None:
    registry = _registry()
    assert requirement_registry_digest(registry) == requirement_registry_digest(registry)
    assert len(requirement_registry_digest(registry)) == 64


def test_requirement_registry_digest_changes_when_meaning_changes_under_same_id() -> None:
    first = _registry(
        [
            {"id": "REQ-FIN-001", "statement": "debits equal credits"},
            {"id": "REQ-AI-002", "statement": "authorization is NONE"},
        ]
    )
    second = _registry(
        [
            {"id": "REQ-FIN-001", "statement": "debits approximately equal credits"},
            {"id": "REQ-AI-002", "statement": "authorization is NONE"},
        ]
    )
    assert requirement_ids_from_registry(first) == requirement_ids_from_registry(second)
    assert requirement_registry_digest(first) != requirement_registry_digest(second)


def test_wrong_registry_schema_fails_closed_for_ids_and_digest() -> None:
    registry = _registry()
    registry["schema"] = "sinergy.requirement-registry/v999"
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(registry)
    with pytest.raises(AccountingInvariantError):
        requirement_registry_digest(registry)


def test_duplicate_requirement_ids_fail_closed() -> None:
    registry = _registry(
        [
            {"id": "REQ-FIN-001"},
            {"id": "REQ-FIN-001"},
        ]
    )
    with pytest.raises(AccountingInvariantError):
        requirement_ids_from_registry(registry)
    with pytest.raises(AccountingInvariantError):
        requirement_registry_digest(registry)


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
