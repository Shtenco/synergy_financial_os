from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .core import AccountingInvariantError
from .ledger_event_v2 import ledger_event_v2_digest, verify_ledger_event_v2


CLOSE_SCHEMA = "accounting.close/v2"
PROOF_SCHEMA = "ledger.inclusion-proof/v2"
LEDGER_EVENT_SCHEMA = "ledger.event/v2"
SNAPSHOT_SCHEMA = "financial.snapshot/v2"
GENESIS_DIGEST = "0" * 64
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
HEX = frozenset("0123456789abcdef")
LEAF_DOMAIN = b"SINERGY_LEDGER_EVENT_V2_LEAF\x00"
NODE_DOMAIN = b"SINERGY_LEDGER_EVENT_V2_NODE\x00"


class AccountingCloseV2Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingCloseV2Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise AccountingCloseV2Error(f"{field_name} must be a 64-character hex digest")
    return result


def _safe_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccountingCloseV2Error(f"{field_name} must be an integer")
    if value < minimum or value > MAX_SAFE_JSON_INTEGER:
        raise AccountingCloseV2Error(
            f"{field_name} must be between {minimum} and {MAX_SAFE_JSON_INTEGER}"
        )
    return value


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingCloseV2Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _utc_text(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith(("Z", "+00:00")):
        raise AccountingCloseV2Error(f"{field_name} must be UTC")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise AccountingCloseV2Error(f"{field_name} is invalid") from exc


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
        raise AccountingCloseV2Error("payload must be canonical-JSON compatible") from exc


def canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def verify_financial_snapshot_v2_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise AccountingCloseV2Error("financial snapshot must be an object")
    payload = dict(snapshot)
    if payload.get("schema") != SNAPSHOT_SCHEMA:
        raise AccountingCloseV2Error("snapshot must use financial.snapshot/v2")
    supplied = _hex64(payload.get("digest"), "snapshot.digest")
    body = dict(payload)
    body.pop("digest", None)
    expected = canonical_digest(body)
    if supplied != expected:
        raise AccountingCloseV2Error(
            f"financial snapshot digest mismatch: expected={expected} got={supplied}"
        )
    _safe_int(payload.get("sequence"), "snapshot.sequence", minimum=1)
    _hex64(payload.get("ledger_digest"), "snapshot.ledger_digest")
    _hex64(payload.get("ledger_last_entry_digest"), "snapshot.ledger_last_entry_digest")
    _hex64(payload.get("account_registry_digest"), "snapshot.account_registry_digest")
    _hex64(payload.get("valuation_policy_digest"), "snapshot.valuation_policy_digest")
    _utc_text(payload.get("as_of"), "snapshot.as_of")
    return payload


def _validate_prefix(
    events: Sequence[Mapping[str, Any]], snapshot: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    snap = verify_financial_snapshot_v2_payload(snapshot)
    if not events:
        raise AccountingCloseV2Error("accounting close requires a non-empty ledger prefix")
    normalized: list[dict[str, Any]] = []
    expected_previous = GENESIS_DIGEST
    reporting_currency = _text(snap.get("reporting_currency"), "snapshot.reporting_currency").upper()
    snapshot_as_of = _utc_text(snap.get("as_of"), "snapshot.as_of")
    for index, raw in enumerate(events):
        event = verify_ledger_event_v2(raw)
        expected_sequence = index + 1
        if event.get("sequence") != expected_sequence:
            raise AccountingCloseV2Error(
                f"ledger prefix must start at sequence 1 without gaps; expected={expected_sequence} got={event.get('sequence')}"
            )
        if event.get("previous_reporting_entry_digest") != expected_previous:
            raise AccountingCloseV2Error("ReportingEntry digest chain is broken")
        if event.get("reporting_currency") != reporting_currency:
            raise AccountingCloseV2Error("ledger event reporting currency differs from snapshot")
        if _utc_text(event.get("effective_at"), f"events[{index}].effective_at") > snapshot_as_of:
            raise AccountingCloseV2Error("snapshot cannot precede a sealed ledger event")
        expected_previous = _hex64(
            event.get("reporting_entry_digest"), "event.reporting_entry_digest"
        )
        normalized.append(event)
    if len(normalized) != snap["sequence"]:
        raise AccountingCloseV2Error("event_count must equal FinancialSnapshot sequence")
    if normalized[-1]["reporting_entry_digest"] != snap["ledger_last_entry_digest"]:
        raise AccountingCloseV2Error(
            "last LedgerEvent reporting-entry digest must equal snapshot ledger_last_entry_digest"
        )
    return tuple(normalized)


def _leaf_hash(event: Mapping[str, Any]) -> bytes:
    return hashlib.sha256(LEAF_DOMAIN + _canonical_bytes(event)).digest()


def _parent_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(NODE_DOMAIN + left + right).digest()


def merkle_root_v2(events: Sequence[Mapping[str, Any]], snapshot: Mapping[str, Any]) -> str:
    normalized = _validate_prefix(events, snapshot)
    level = [_leaf_hash(event) for event in normalized]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [_parent_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0].hex()


@dataclass(frozen=True)
class AccountingCloseV2:
    close_id: str
    financial_snapshot_digest: str
    snapshot_sequence: int
    snapshot_ledger_digest: str
    snapshot_ledger_last_entry_digest: str
    account_registry_digest: str
    ledger_root: str
    event_count: int
    closed_at: datetime
    valuation_policy_digest: str
    requirement_registry_digest: str
    snapshot_schema: str = SNAPSHOT_SCHEMA
    ledger_event_schema: str = LEDGER_EVENT_SCHEMA
    authority: str = "FINANCIAL_OS_ACCOUNTING_CLOSE"
    profit_recognition: str = "REFERENCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.snapshot_schema != SNAPSHOT_SCHEMA or self.ledger_event_schema != LEDGER_EVENT_SCHEMA:
            raise AccountingCloseV2Error("unsupported snapshot/ledger schema")
        if self.authority != "FINANCIAL_OS_ACCOUNTING_CLOSE":
            raise AccountingCloseV2Error("AccountingClose authority must remain Financial OS")
        if self.profit_recognition != "REFERENCE_ONLY" or self.execution_authority != "NONE":
            raise AccountingCloseV2Error("AccountingClose is a non-executing sealing fact")
        sequence = _safe_int(self.snapshot_sequence, "snapshot_sequence", minimum=1)
        count = _safe_int(self.event_count, "event_count", minimum=1)
        if sequence != count:
            raise AccountingCloseV2Error("snapshot_sequence must equal event_count")
        object.__setattr__(self, "close_id", _text(self.close_id, "close_id"))
        for name in (
            "financial_snapshot_digest",
            "snapshot_ledger_digest",
            "snapshot_ledger_last_entry_digest",
            "account_registry_digest",
            "ledger_root",
            "valuation_policy_digest",
            "requirement_registry_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        object.__setattr__(self, "closed_at", _utc(self.closed_at, "closed_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": CLOSE_SCHEMA,
            "close_id": self.close_id,
            "snapshot_schema": self.snapshot_schema,
            "financial_snapshot_digest": self.financial_snapshot_digest,
            "snapshot_sequence": self.snapshot_sequence,
            "snapshot_ledger_digest": self.snapshot_ledger_digest,
            "snapshot_ledger_last_entry_digest": self.snapshot_ledger_last_entry_digest,
            "account_registry_digest": self.account_registry_digest,
            "ledger_event_schema": self.ledger_event_schema,
            "ledger_root": self.ledger_root,
            "event_count": self.event_count,
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
class LedgerInclusionSiblingV2:
    side: str
    digest: str

    def __post_init__(self) -> None:
        side = _text(self.side, "side").upper()
        if side not in {"LEFT", "RIGHT"}:
            raise AccountingCloseV2Error("sibling side must be LEFT or RIGHT")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "digest", _hex64(self.digest, "digest"))

    def to_dict(self) -> dict[str, str]:
        return {"side": self.side, "digest": self.digest}


@dataclass(frozen=True)
class LedgerInclusionProofV2:
    close_digest: str
    ledger_root: str
    event_digest: str
    reporting_entry_digest: str
    event_id: str
    event_sequence: int
    leaf_index: int
    event_count: int
    siblings: tuple[LedgerInclusionSiblingV2, ...]
    authority: str = "PROVENANCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "PROVENANCE_ONLY" or self.execution_authority != "NONE":
            raise AccountingCloseV2Error("inclusion proof is provenance-only")
        for name in ("close_digest", "ledger_root", "event_digest", "reporting_entry_digest"):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        object.__setattr__(self, "event_id", _text(self.event_id, "event_id"))
        sequence = _safe_int(self.event_sequence, "event_sequence", minimum=1)
        count = _safe_int(self.event_count, "event_count", minimum=1)
        index = _safe_int(self.leaf_index, "leaf_index")
        if index >= count or sequence != index + 1:
            raise AccountingCloseV2Error("proof index/sequence must match genesis-based prefix position")
        if any(not isinstance(item, LedgerInclusionSiblingV2) for item in self.siblings):
            raise AccountingCloseV2Error("invalid inclusion sibling")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": PROOF_SCHEMA,
            "close_digest": self.close_digest,
            "ledger_root": self.ledger_root,
            "event_digest": self.event_digest,
            "reporting_entry_digest": self.reporting_entry_digest,
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


def build_accounting_close_v2(
    events: Sequence[Mapping[str, Any]],
    financial_snapshot: Mapping[str, Any],
    *,
    close_id: str,
    closed_at: datetime,
    requirement_registry_digest: str,
) -> AccountingCloseV2:
    snapshot = verify_financial_snapshot_v2_payload(financial_snapshot)
    normalized = _validate_prefix(events, snapshot)
    close_time = _utc(closed_at, "closed_at")
    snapshot_time = _utc_text(snapshot["as_of"], "snapshot.as_of")
    if close_time < snapshot_time:
        raise AccountingCloseV2Error("accounting close cannot precede snapshot")
    return AccountingCloseV2(
        close_id=close_id,
        financial_snapshot_digest=snapshot["digest"],
        snapshot_sequence=snapshot["sequence"],
        snapshot_ledger_digest=snapshot["ledger_digest"],
        snapshot_ledger_last_entry_digest=snapshot["ledger_last_entry_digest"],
        account_registry_digest=snapshot["account_registry_digest"],
        ledger_root=merkle_root_v2(normalized, snapshot),
        event_count=len(normalized),
        closed_at=close_time,
        valuation_policy_digest=snapshot["valuation_policy_digest"],
        requirement_registry_digest=requirement_registry_digest,
    )


def verify_accounting_close_v2(
    events: Sequence[Mapping[str, Any]],
    financial_snapshot: Mapping[str, Any],
    close: AccountingCloseV2,
) -> bool:
    snapshot = verify_financial_snapshot_v2_payload(financial_snapshot)
    normalized = _validate_prefix(events, snapshot)
    if close.financial_snapshot_digest != snapshot["digest"]:
        raise AccountingCloseV2Error("close snapshot digest mismatch")
    if close.snapshot_sequence != snapshot["sequence"]:
        raise AccountingCloseV2Error("close snapshot sequence mismatch")
    if close.snapshot_ledger_digest != snapshot["ledger_digest"]:
        raise AccountingCloseV2Error("close ledger digest mismatch")
    if close.snapshot_ledger_last_entry_digest != snapshot["ledger_last_entry_digest"]:
        raise AccountingCloseV2Error("close last reporting-entry digest mismatch")
    if close.account_registry_digest != snapshot["account_registry_digest"]:
        raise AccountingCloseV2Error("close account-registry digest mismatch")
    if close.valuation_policy_digest != snapshot["valuation_policy_digest"]:
        raise AccountingCloseV2Error("close valuation-policy digest mismatch")
    if close.ledger_root != merkle_root_v2(normalized, snapshot):
        raise AccountingCloseV2Error("close ledger Merkle root mismatch")
    return True


def build_ledger_inclusion_proof_v2(
    events: Sequence[Mapping[str, Any]],
    financial_snapshot: Mapping[str, Any],
    *,
    event_index: int,
    close: AccountingCloseV2,
) -> LedgerInclusionProofV2:
    snapshot = verify_financial_snapshot_v2_payload(financial_snapshot)
    normalized = _validate_prefix(events, snapshot)
    verify_accounting_close_v2(normalized, snapshot, close)
    index = _safe_int(event_index, "event_index")
    if index >= len(normalized):
        raise AccountingCloseV2Error("event_index outside ledger prefix")
    level = [_leaf_hash(event) for event in normalized]
    cursor = index
    siblings: list[LedgerInclusionSiblingV2] = []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        if cursor % 2 == 0:
            siblings.append(LedgerInclusionSiblingV2("RIGHT", level[cursor + 1].hex()))
        else:
            siblings.append(LedgerInclusionSiblingV2("LEFT", level[cursor - 1].hex()))
        level = [_parent_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        cursor //= 2
    event = normalized[index]
    return LedgerInclusionProofV2(
        close_digest=close.digest,
        ledger_root=close.ledger_root,
        event_digest=ledger_event_v2_digest(event),
        reporting_entry_digest=event["reporting_entry_digest"],
        event_id=event["event_id"],
        event_sequence=event["sequence"],
        leaf_index=index,
        event_count=len(normalized),
        siblings=tuple(siblings),
    )


def verify_ledger_inclusion_proof_v2(
    event: Mapping[str, Any],
    proof: LedgerInclusionProofV2,
    close: AccountingCloseV2,
) -> bool:
    verified = verify_ledger_event_v2(event)
    if proof.close_digest != close.digest or proof.ledger_root != close.ledger_root:
        raise AccountingCloseV2Error("proof is not bound to this AccountingClose")
    if proof.event_count != close.event_count:
        raise AccountingCloseV2Error("proof event_count mismatch")
    if proof.event_digest != ledger_event_v2_digest(verified):
        raise AccountingCloseV2Error("proof ledger-event digest mismatch")
    if proof.reporting_entry_digest != verified["reporting_entry_digest"]:
        raise AccountingCloseV2Error("proof reporting-entry digest mismatch")
    if proof.event_id != verified["event_id"] or proof.event_sequence != verified["sequence"]:
        raise AccountingCloseV2Error("proof event identity mismatch")
    current = _leaf_hash(verified)
    for sibling in proof.siblings:
        other = bytes.fromhex(sibling.digest)
        current = _parent_hash(other, current) if sibling.side == "LEFT" else _parent_hash(current, other)
    if current.hex() != close.ledger_root:
        raise AccountingCloseV2Error("Merkle proof does not reconstruct close root")
    return True
