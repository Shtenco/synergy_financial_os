from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Sequence

from .core import AccountingInvariantError


CLOSE_SCHEMA = "accounting.close/v1"
PROOF_SCHEMA = "ledger.inclusion-proof/v1"
LEDGER_EVENT_SCHEMA = "ledger.event/v1"
SNAPSHOT_SCHEMA = "financial.snapshot/v2"
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
HEX = frozenset("0123456789abcdef")
LEAF_DOMAIN = b"SINERGY_LEDGER_LEAF_V1\x00"
NODE_DOMAIN = b"SINERGY_LEDGER_NODE_V1\x00"


class AccountingCloseV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingCloseV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise AccountingCloseV1Error(f"{field_name} must be a 64-character hex digest")
    return result


def _safe_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccountingCloseV1Error(f"{field_name} must be an integer")
    if value < minimum or value > MAX_SAFE_JSON_INTEGER:
        raise AccountingCloseV1Error(
            f"{field_name} must be between {minimum} and {MAX_SAFE_JSON_INTEGER}"
        )
    return value


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingCloseV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AccountingCloseV1Error("payload must be canonical-JSON compatible") from exc


def canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def ledger_event_digest(event: Mapping[str, Any]) -> str:
    if not isinstance(event, Mapping) or event.get("schema") != LEDGER_EVENT_SCHEMA:
        raise AccountingCloseV1Error("ledger event must use ledger.event/v1")
    return canonical_digest(event)


def _leaf_hash(event: Mapping[str, Any]) -> bytes:
    return hashlib.sha256(LEAF_DOMAIN + _canonical_bytes(event)).digest()


def _parent_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_DOMAIN + left + right).digest()


def _validate_ledger_events(events: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if not events:
        raise AccountingCloseV1Error("accounting close requires at least one ledger event")
    normalized: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    expected_sequence: int | None = None
    for index, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise AccountingCloseV1Error(f"ledger event {index} must be an object")
        event = dict(raw)
        if event.get("schema") != LEDGER_EVENT_SCHEMA:
            raise AccountingCloseV1Error(f"ledger event {index} must use {LEDGER_EVENT_SCHEMA}")
        event_id = _text(event.get("event_id"), f"ledger event {index}.event_id")
        if event_id in seen_event_ids:
            raise AccountingCloseV1Error("ledger event ids must be unique")
        seen_event_ids.add(event_id)
        sequence = _safe_int(event.get("sequence"), f"ledger event {index}.sequence", minimum=1)
        if expected_sequence is None:
            expected_sequence = sequence
        elif sequence != expected_sequence:
            raise AccountingCloseV1Error(
                f"ledger sequence must be contiguous; expected {expected_sequence}, got {sequence}"
            )
        expected_sequence = sequence + 1
        # Force deterministic serialization now so non-JSON values fail before sealing.
        _canonical_bytes(event)
        normalized.append(event)
    return tuple(normalized)


def merkle_root_v1(events: Sequence[Mapping[str, Any]]) -> str:
    normalized = _validate_ledger_events(events)
    level = [_leaf_hash(event) for event in normalized]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [_parent_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0].hex()


@dataclass(frozen=True)
class AccountingCloseV1:
    close_id: str
    financial_snapshot_digest: str
    ledger_root: str
    event_count: int
    first_sequence: int
    last_sequence: int
    closed_at: datetime
    valuation_policy_digest: str
    requirement_registry_digest: str
    snapshot_schema: str = SNAPSHOT_SCHEMA
    ledger_event_schema: str = LEDGER_EVENT_SCHEMA
    authority: str = "FINANCIAL_OS_ACCOUNTING_CLOSE"
    profit_recognition: str = "REFERENCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.snapshot_schema != SNAPSHOT_SCHEMA:
            raise AccountingCloseV1Error("unsupported snapshot schema")
        if self.ledger_event_schema != LEDGER_EVENT_SCHEMA:
            raise AccountingCloseV1Error("unsupported ledger event schema")
        if self.authority != "FINANCIAL_OS_ACCOUNTING_CLOSE":
            raise AccountingCloseV1Error("AccountingClose authority must remain Financial OS")
        if self.profit_recognition != "REFERENCE_ONLY":
            raise AccountingCloseV1Error("AccountingClose may reference but cannot perform recognition")
        if self.execution_authority != "NONE":
            raise AccountingCloseV1Error("AccountingClose cannot execute financial actions")
        count = _safe_int(self.event_count, "event_count", minimum=1)
        first = _safe_int(self.first_sequence, "first_sequence", minimum=1)
        last = _safe_int(self.last_sequence, "last_sequence", minimum=first)
        if last - first + 1 != count:
            raise AccountingCloseV1Error("event_count must equal the sealed contiguous sequence span")
        object.__setattr__(self, "close_id", _text(self.close_id, "close_id"))
        object.__setattr__(self, "financial_snapshot_digest", _hex64(self.financial_snapshot_digest, "financial_snapshot_digest"))
        object.__setattr__(self, "ledger_root", _hex64(self.ledger_root, "ledger_root"))
        object.__setattr__(self, "valuation_policy_digest", _hex64(self.valuation_policy_digest, "valuation_policy_digest"))
        object.__setattr__(self, "requirement_registry_digest", _hex64(self.requirement_registry_digest, "requirement_registry_digest"))
        object.__setattr__(self, "closed_at", _utc(self.closed_at, "closed_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": CLOSE_SCHEMA,
            "close_id": self.close_id,
            "snapshot_schema": self.snapshot_schema,
            "financial_snapshot_digest": self.financial_snapshot_digest,
            "ledger_event_schema": self.ledger_event_schema,
            "ledger_root": self.ledger_root,
            "event_count": self.event_count,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "closed_at": self.closed_at.isoformat().replace("+00:00", "Z"),
            "valuation_policy_digest": self.valuation_policy_digest,
            "requirement_registry_digest": self.requirement_registry_digest,
            "authority": self.authority,
            "profit_recognition": self.profit_recognition,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict(include_digest=False))


@dataclass(frozen=True)
class LedgerInclusionSiblingV1:
    side: str
    digest: str

    def __post_init__(self) -> None:
        side = _text(self.side, "side").upper()
        if side not in {"LEFT", "RIGHT"}:
            raise AccountingCloseV1Error("proof sibling side must be LEFT or RIGHT")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "digest", _hex64(self.digest, "digest"))

    def to_dict(self) -> dict[str, str]:
        return {"side": self.side, "digest": self.digest}


@dataclass(frozen=True)
class LedgerInclusionProofV1:
    close_digest: str
    ledger_root: str
    event_digest: str
    event_id: str
    event_sequence: int
    leaf_index: int
    event_count: int
    siblings: tuple[LedgerInclusionSiblingV1, ...]
    authority: str = "PROVENANCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "PROVENANCE_ONLY" or self.execution_authority != "NONE":
            raise AccountingCloseV1Error("inclusion proof is provenance-only")
        object.__setattr__(self, "close_digest", _hex64(self.close_digest, "close_digest"))
        object.__setattr__(self, "ledger_root", _hex64(self.ledger_root, "ledger_root"))
        object.__setattr__(self, "event_digest", _hex64(self.event_digest, "event_digest"))
        object.__setattr__(self, "event_id", _text(self.event_id, "event_id"))
        object.__setattr__(self, "event_sequence", _safe_int(self.event_sequence, "event_sequence", minimum=1))
        count = _safe_int(self.event_count, "event_count", minimum=1)
        index = _safe_int(self.leaf_index, "leaf_index")
        if index >= count:
            raise AccountingCloseV1Error("leaf_index must be inside event_count")
        if any(not isinstance(item, LedgerInclusionSiblingV1) for item in self.siblings):
            raise AccountingCloseV1Error("siblings must contain LedgerInclusionSiblingV1")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": PROOF_SCHEMA,
            "close_digest": self.close_digest,
            "ledger_root": self.ledger_root,
            "event_digest": self.event_digest,
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "leaf_index": self.leaf_index,
            "event_count": self.event_count,
            "siblings": [item.to_dict() for item in self.siblings],
            "authority": self.authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict(include_digest=False))


def build_accounting_close_v1(
    events: Sequence[Mapping[str, Any]],
    *,
    close_id: str,
    financial_snapshot_digest: str,
    closed_at: datetime,
    valuation_policy_digest: str,
    requirement_registry_digest: str,
) -> AccountingCloseV1:
    normalized = _validate_ledger_events(events)
    return AccountingCloseV1(
        close_id=close_id,
        financial_snapshot_digest=financial_snapshot_digest,
        ledger_root=merkle_root_v1(normalized),
        event_count=len(normalized),
        first_sequence=int(normalized[0]["sequence"]),
        last_sequence=int(normalized[-1]["sequence"]),
        closed_at=closed_at,
        valuation_policy_digest=valuation_policy_digest,
        requirement_registry_digest=requirement_registry_digest,
    )


def build_ledger_inclusion_proof_v1(
    events: Sequence[Mapping[str, Any]],
    *,
    event_index: int,
    close: AccountingCloseV1,
) -> LedgerInclusionProofV1:
    normalized = _validate_ledger_events(events)
    index = _safe_int(event_index, "event_index")
    if index >= len(normalized):
        raise AccountingCloseV1Error("event_index outside ledger event list")
    expected_root = merkle_root_v1(normalized)
    if close.ledger_root != expected_root or close.event_count != len(normalized):
        raise AccountingCloseV1Error("AccountingClose does not seal supplied ledger events")

    level = [_leaf_hash(event) for event in normalized]
    cursor = index
    siblings: list[LedgerInclusionSiblingV1] = []
    while len(level) > 1:
        original_len = len(level)
        if original_len % 2:
            level.append(level[-1])
        if cursor % 2 == 0:
            sibling_index = cursor + 1
            siblings.append(LedgerInclusionSiblingV1("RIGHT", level[sibling_index].hex()))
        else:
            sibling_index = cursor - 1
            siblings.append(LedgerInclusionSiblingV1("LEFT", level[sibling_index].hex()))
        level = [_parent_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        cursor //= 2

    event = normalized[index]
    return LedgerInclusionProofV1(
        close_digest=close.digest,
        ledger_root=close.ledger_root,
        event_digest=ledger_event_digest(event),
        event_id=str(event["event_id"]),
        event_sequence=int(event["sequence"]),
        leaf_index=index,
        event_count=len(normalized),
        siblings=tuple(siblings),
    )


def verify_ledger_inclusion_proof_v1(
    event: Mapping[str, Any],
    proof: LedgerInclusionProofV1,
    close: AccountingCloseV1,
) -> bool:
    if proof.close_digest != close.digest:
        raise AccountingCloseV1Error("proof close digest mismatch")
    if proof.ledger_root != close.ledger_root:
        raise AccountingCloseV1Error("proof ledger root mismatch")
    if proof.event_count != close.event_count:
        raise AccountingCloseV1Error("proof event count mismatch")
    digest = ledger_event_digest(event)
    if digest != proof.event_digest:
        raise AccountingCloseV1Error("proof event digest mismatch")
    if str(event.get("event_id")) != proof.event_id or int(event.get("sequence")) != proof.event_sequence:
        raise AccountingCloseV1Error("proof event identity/sequence mismatch")

    current = _leaf_hash(event)
    for sibling in proof.siblings:
        sibling_bytes = bytes.fromhex(sibling.digest)
        current = _parent_hash(sibling_bytes, current) if sibling.side == "LEFT" else _parent_hash(current, sibling_bytes)
    if current.hex() != close.ledger_root:
        raise AccountingCloseV1Error("Merkle inclusion proof does not reconstruct close ledger root")
    return True
