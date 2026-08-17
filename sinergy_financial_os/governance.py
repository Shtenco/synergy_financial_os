from __future__ import annotations

from typing import Any, Mapping

from .canonical_json import canonical_json_digest
from .errors import AccountingInvariantError


def requirement_ids_from_registry(registry: Mapping[str, Any]) -> frozenset[str]:
    """Validate the central requirement registry shape and return its known IDs."""

    if registry.get("schema") != "sinergy.requirement-registry/v1":
        raise AccountingInvariantError("unsupported requirement registry schema")
    requirements = registry.get("requirements")
    if not isinstance(requirements, list):
        raise AccountingInvariantError("requirement registry must contain a requirements array")

    ids: list[str] = []
    for item in requirements:
        if not isinstance(item, Mapping):
            raise AccountingInvariantError("requirement registry item must be an object")
        requirement_id = str(item.get("id", "")).strip()
        if not requirement_id.startswith("REQ-"):
            raise AccountingInvariantError(
                f"invalid requirement id in registry: {requirement_id or '<empty>'}"
            )
        ids.append(requirement_id)

    if len(ids) != len(set(ids)):
        raise AccountingInvariantError("requirement registry contains duplicate IDs")
    if not ids:
        raise AccountingInvariantError("requirement registry must not be empty")
    return frozenset(ids)


def requirement_registry_digest(registry: Mapping[str, Any]) -> str:
    """Return canonical SHA-256 of the validated full monetary constitution.

    The digest binds not only REQ-* identifiers but their statements, ownership,
    implementation/test references and verification metadata. Therefore changing
    the meaning of an existing requirement under the same identifier changes the
    digest and makes an older AI proposal stale.
    """

    requirement_ids_from_registry(registry)
    return canonical_json_digest(dict(registry))
