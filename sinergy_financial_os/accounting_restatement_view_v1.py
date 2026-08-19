from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import (
    AccountingCloseV2,
    LedgerInclusionProofV2,
    verify_ledger_inclusion_proof_v2,
)
from .accounting_period_chain_v1 import AccountingPeriodChainProofV1
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .ledger_event_v2 import ledger_event_v2_digest, verify_ledger_event_v2
from .prior_period_correction_v1 import (
    PriorPeriodCorrectionAuthorizationV1,
    verify_prior_period_correction_context_v1,
)


OVERLAY_SCHEMA = "accounting.restatement-overlay/v1"
VIEW_SCHEMA = "accounting.restated-period-view/v1"
PRESENTATION_ACTION = "EXCLUDE_ORIGINAL_ENTRY"
HEX = frozenset("0123456789abcdef")
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991


class AccountingRestatementViewV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingRestatementViewV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise AccountingRestatementViewV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingRestatementViewV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _safe_int(value: Any, field_name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccountingRestatementViewV1Error(f"{field_name} must be integer")
    if value < minimum or value > MAX_SAFE_JSON_INTEGER:
        raise AccountingRestatementViewV1Error(
            f"{field_name} must be between {minimum} and {MAX_SAFE_JSON_INTEGER}"
        )
    return value


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _line_multiset(event: Mapping[str, Any], *, opposite: bool) -> tuple[tuple[str, str, str, str], ...]:
    result: list[tuple[str, str, str, str]] = []
    currency = _text(event.get("reporting_currency"), "reporting_currency")
    for index, line in enumerate(event.get("lines", [])):
        if not isinstance(line, Mapping):
            raise AccountingRestatementViewV1Error(f"line {index} must be object")
        account = _text(line.get("account"), f"line {index}.account")
        line_currency = _text(line.get("currency"), f"line {index}.currency")
        if line_currency != currency:
            raise AccountingRestatementViewV1Error("line currency mismatch")
        debit = _text(line.get("debit"), f"line {index}.debit")
        credit = _text(line.get("credit"), f"line {index}.credit")
        result.append(
            (account, line_currency, credit if opposite else debit, debit if opposite else credit)
        )
    return tuple(sorted(result))


@dataclass(frozen=True)
class AccountingRestatementOverlayV1:
    overlay_id: str
    affected_period_id: str
    correction_target_period_id: str
    original_period_close_digest: str
    original_accounting_close_digest: str
    original_ledger_event_digest: str
    original_reporting_entry_digest: str
    correction_authorization_digest: str
    period_chain_proof_digest: str
    correction_period_close_digest: str
    correction_accounting_close_digest: str
    correction_ledger_event_digest: str
    correction_reporting_entry_digest: str
    generated_at: datetime
    presentation_action: str = PRESENTATION_ACTION
    authority: str = "FINANCIAL_OS_PRESENTATION_ONLY"
    original_history_mutation: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.presentation_action != PRESENTATION_ACTION:
            raise AccountingRestatementViewV1Error("v1 overlay supports EXCLUDE_ORIGINAL_ENTRY only")
        if self.authority != "FINANCIAL_OS_PRESENTATION_ONLY":
            raise AccountingRestatementViewV1Error("restatement overlay is presentation-only")
        if self.original_history_mutation != "NONE" or self.execution_authority != "NONE":
            raise AccountingRestatementViewV1Error("restatement overlay cannot mutate history or execute")
        for field_name in ("overlay_id", "affected_period_id", "correction_target_period_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        for field_name in (
            "original_period_close_digest",
            "original_accounting_close_digest",
            "original_ledger_event_digest",
            "original_reporting_entry_digest",
            "correction_authorization_digest",
            "period_chain_proof_digest",
            "correction_period_close_digest",
            "correction_accounting_close_digest",
            "correction_ledger_event_digest",
            "correction_reporting_entry_digest",
        ):
            object.__setattr__(self, field_name, _hex64(getattr(self, field_name), field_name))
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": OVERLAY_SCHEMA,
            "overlay_id": self.overlay_id,
            "affected_period_id": self.affected_period_id,
            "correction_target_period_id": self.correction_target_period_id,
            "original_period_close_digest": self.original_period_close_digest,
            "original_accounting_close_digest": self.original_accounting_close_digest,
            "original_ledger_event_digest": self.original_ledger_event_digest,
            "original_reporting_entry_digest": self.original_reporting_entry_digest,
            "correction_authorization_digest": self.correction_authorization_digest,
            "period_chain_proof_digest": self.period_chain_proof_digest,
            "correction_period_close_digest": self.correction_period_close_digest,
            "correction_accounting_close_digest": self.correction_accounting_close_digest,
            "correction_ledger_event_digest": self.correction_ledger_event_digest,
            "correction_reporting_entry_digest": self.correction_reporting_entry_digest,
            "presentation_action": self.presentation_action,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "original_history_mutation": self.original_history_mutation,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


@dataclass(frozen=True)
class RestatedPeriodViewV1:
    view_id: str
    affected_period_id: str
    original_period_close_digest: str
    overlay_digests: tuple[str, ...]
    excluded_reporting_entry_digests: tuple[str, ...]
    view_version: int
    generated_at: datetime
    previous_restated_view_digest: str | None = None
    status: str = "RESTATED_PRESENTATION"
    recalculated_financial_metrics: str = "NOT_PERFORMED"
    authority: str = "FINANCIAL_OS_PRESENTATION_ONLY"
    ledger_mutation_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.status != "RESTATED_PRESENTATION":
            raise AccountingRestatementViewV1Error("invalid restated view status")
        if self.recalculated_financial_metrics != "NOT_PERFORMED":
            raise AccountingRestatementViewV1Error(
                "v1 restated view is a treatment manifest and does not invent financial metrics"
            )
        if self.authority != "FINANCIAL_OS_PRESENTATION_ONLY":
            raise AccountingRestatementViewV1Error("restated view is presentation-only")
        if self.ledger_mutation_authority != "NONE" or self.execution_authority != "NONE":
            raise AccountingRestatementViewV1Error("restated view cannot mutate ledger or execute")
        object.__setattr__(self, "view_id", _text(self.view_id, "view_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(
            self,
            "original_period_close_digest",
            _hex64(self.original_period_close_digest, "original_period_close_digest"),
        )
        overlays = tuple(_hex64(item, "overlay_digest") for item in self.overlay_digests)
        excluded = tuple(
            _hex64(item, "excluded_reporting_entry_digest")
            for item in self.excluded_reporting_entry_digests
        )
        if not overlays or len(set(overlays)) != len(overlays):
            raise AccountingRestatementViewV1Error("restated view requires unique overlays")
        if not excluded or len(set(excluded)) != len(excluded):
            raise AccountingRestatementViewV1Error("restated view requires unique excluded entries")
        object.__setattr__(self, "overlay_digests", tuple(sorted(overlays)))
        object.__setattr__(self, "excluded_reporting_entry_digests", tuple(sorted(excluded)))
        object.__setattr__(self, "view_version", _safe_int(self.view_version, "view_version"))
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))
        if self.previous_restated_view_digest is not None:
            object.__setattr__(
                self,
                "previous_restated_view_digest",
                _hex64(
                    self.previous_restated_view_digest,
                    "previous_restated_view_digest",
                    nullable=True,
                ),
            )
        if self.view_version == 1 and self.previous_restated_view_digest is not None:
            raise AccountingRestatementViewV1Error("version 1 cannot have previous restated view")
        if self.view_version > 1 and self.previous_restated_view_digest is None:
            raise AccountingRestatementViewV1Error("version >1 requires previous restated view")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": VIEW_SCHEMA,
            "view_id": self.view_id,
            "affected_period_id": self.affected_period_id,
            "original_period_close_digest": self.original_period_close_digest,
            "overlay_digests": list(self.overlay_digests),
            "excluded_reporting_entry_digests": list(self.excluded_reporting_entry_digests),
            "view_version": self.view_version,
            "previous_restated_view_digest": self.previous_restated_view_digest,
            "status": self.status,
            "recalculated_financial_metrics": self.recalculated_financial_metrics,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "ledger_mutation_authority": self.ledger_mutation_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def build_accounting_restatement_overlay_v1(
    *,
    overlay_id: str,
    authorization: PriorPeriodCorrectionAuthorizationV1,
    target_period: AccountingPeriodV1,
    period_chain_proof: AccountingPeriodChainProofV1,
    period_close_chain: Sequence[AccountingPeriodCloseV1],
    original_accounting_close: AccountingCloseV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
    correction_period_close: AccountingPeriodCloseV1,
    correction_accounting_close: AccountingCloseV2,
    correction_ledger_event: Mapping[str, Any],
    correction_inclusion_proof: LedgerInclusionProofV2,
    generated_at: datetime,
) -> AccountingRestatementOverlayV1:
    verify_prior_period_correction_context_v1(
        authorization,
        target_period,
        period_chain_proof,
        period_close_chain,
        original_accounting_close,
        original_ledger_event,
        original_inclusion_proof,
    )
    if correction_period_close.period_id != target_period.period_id:
        raise AccountingRestatementViewV1Error("correction PeriodClose target period mismatch")
    if correction_period_close.accounting_close_digest != correction_accounting_close.digest:
        raise AccountingRestatementViewV1Error("correction PeriodClose/AccountingClose mismatch")
    if authorization.digest not in correction_period_close.adjustment_authorization_digests:
        raise AccountingRestatementViewV1Error(
            "correction PeriodClose does not declare correction authorization"
        )

    original_event = verify_ledger_event_v2(original_ledger_event)
    correction_event = verify_ledger_event_v2(correction_ledger_event)
    if correction_event.get("event_type") != "INTERNAL":
        raise AccountingRestatementViewV1Error("correction LedgerEvent must be INTERNAL")
    if correction_event.get("evidence_digest") != authorization.digest:
        raise AccountingRestatementViewV1Error("correction LedgerEvent evidence mismatch")
    metadata = correction_event.get("metadata", {})
    if metadata.get("economic_class") != "PRIOR_PERIOD_ENTRY_VOID":
        raise AccountingRestatementViewV1Error("correction LedgerEvent is not PRIOR_PERIOD_ENTRY_VOID")
    if metadata.get("original_reporting_entry_digest") != authorization.original_reporting_entry_digest:
        raise AccountingRestatementViewV1Error("correction metadata original ReportingEntry mismatch")
    if metadata.get("restatement_required") != "YES":
        raise AccountingRestatementViewV1Error("correction must explicitly require restatement presentation")
    if _line_multiset(original_event, opposite=True) != _line_multiset(correction_event, opposite=False):
        raise AccountingRestatementViewV1Error("correction LedgerEvent is not exact opposite of original")
    verify_ledger_inclusion_proof_v2(
        correction_event,
        correction_inclusion_proof,
        correction_accounting_close,
    )
    generated = _utc(generated_at, "generated_at")
    if generated < correction_period_close.closed_at:
        raise AccountingRestatementViewV1Error(
            "restatement overlay cannot be generated before correction PeriodClose"
        )

    return AccountingRestatementOverlayV1(
        overlay_id=overlay_id,
        affected_period_id=authorization.affected_period_id,
        correction_target_period_id=authorization.target_period_id,
        original_period_close_digest=authorization.original_period_close_digest,
        original_accounting_close_digest=authorization.original_accounting_close_digest,
        original_ledger_event_digest=authorization.original_ledger_event_digest,
        original_reporting_entry_digest=authorization.original_reporting_entry_digest,
        correction_authorization_digest=authorization.digest,
        period_chain_proof_digest=authorization.period_chain_proof_digest,
        correction_period_close_digest=correction_period_close.digest,
        correction_accounting_close_digest=correction_accounting_close.digest,
        correction_ledger_event_digest=ledger_event_v2_digest(correction_event),
        correction_reporting_entry_digest=correction_event["reporting_entry_digest"],
        generated_at=generated,
    )


def build_restated_period_view_v1(
    overlays: Sequence[AccountingRestatementOverlayV1],
    *,
    view_id: str,
    generated_at: datetime,
    previous_view: RestatedPeriodViewV1 | None = None,
) -> RestatedPeriodViewV1:
    values = tuple(overlays)
    if not values:
        raise AccountingRestatementViewV1Error("restated period view requires at least one overlay")
    if any(not isinstance(item, AccountingRestatementOverlayV1) for item in values):
        raise AccountingRestatementViewV1Error("overlays must be AccountingRestatementOverlayV1")
    affected = {item.affected_period_id for item in values}
    original_closes = {item.original_period_close_digest for item in values}
    original_entries = {item.original_reporting_entry_digest for item in values}
    if len(affected) != 1 or len(original_closes) != 1:
        raise AccountingRestatementViewV1Error(
            "all overlays in one restated view must target the same original period/close"
        )
    if len(original_entries) != len(values):
        raise AccountingRestatementViewV1Error("same original ReportingEntry cannot be excluded twice")
    generated = _utc(generated_at, "generated_at")
    if generated < max(item.generated_at for item in values):
        raise AccountingRestatementViewV1Error("view cannot predate its overlays")

    overlay_digests = tuple(sorted(item.digest for item in values))
    excluded = tuple(sorted(item.original_reporting_entry_digest for item in values))
    if previous_view is None:
        version = 1
        previous_digest = None
    else:
        if previous_view.affected_period_id != next(iter(affected)):
            raise AccountingRestatementViewV1Error("previous view affected period mismatch")
        if previous_view.original_period_close_digest != next(iter(original_closes)):
            raise AccountingRestatementViewV1Error("previous view original PeriodClose mismatch")
        if generated <= previous_view.generated_at:
            raise AccountingRestatementViewV1Error("new restated view must be generated after previous view")
        previous_set = set(previous_view.overlay_digests)
        current_set = set(overlay_digests)
        if not previous_set < current_set:
            raise AccountingRestatementViewV1Error(
                "new restated view must be a strict superset of previous overlays"
            )
        version = previous_view.view_version + 1
        previous_digest = previous_view.digest

    return RestatedPeriodViewV1(
        view_id=view_id,
        affected_period_id=next(iter(affected)),
        original_period_close_digest=next(iter(original_closes)),
        overlay_digests=overlay_digests,
        excluded_reporting_entry_digests=excluded,
        view_version=version,
        previous_restated_view_digest=previous_digest,
        generated_at=generated,
    )
