from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from .accounting_close_v2 import AccountingCloseV2
from .core import AccountingInvariantError


PERIOD_SCHEMA = "accounting.period/v1"
PERIOD_CLOSE_SCHEMA = "accounting.period-close/v1"
HEX = frozenset("0123456789abcdef")


class AccountingPeriodV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingPeriodV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise AccountingPeriodV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingPeriodV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


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


@dataclass(frozen=True)
class AccountingPeriodV1:
    period_id: str
    starts_at: datetime
    ends_at: datetime
    accounting_perimeter: str
    reporting_currency: str
    accounting_policy_digest: str
    requirement_registry_digest: str
    opening_period_close_digest: str | None = None
    authority: str = "PERIOD_DEFINITION_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        starts = _utc(self.starts_at, "starts_at")
        ends = _utc(self.ends_at, "ends_at")
        if ends <= starts:
            raise AccountingPeriodV1Error("period ends_at must be later than starts_at")
        if self.authority != "PERIOD_DEFINITION_ONLY" or self.execution_authority != "NONE":
            raise AccountingPeriodV1Error("period definition is non-executing")
        object.__setattr__(self, "period_id", _text(self.period_id, "period_id"))
        object.__setattr__(self, "starts_at", starts)
        object.__setattr__(self, "ends_at", ends)
        object.__setattr__(
            self,
            "accounting_perimeter",
            _text(self.accounting_perimeter, "accounting_perimeter"),
        )
        object.__setattr__(
            self,
            "reporting_currency",
            _text(self.reporting_currency, "reporting_currency").upper(),
        )
        object.__setattr__(
            self,
            "accounting_policy_digest",
            _hex64(self.accounting_policy_digest, "accounting_policy_digest"),
        )
        object.__setattr__(
            self,
            "requirement_registry_digest",
            _hex64(self.requirement_registry_digest, "requirement_registry_digest"),
        )
        if self.opening_period_close_digest is not None:
            object.__setattr__(
                self,
                "opening_period_close_digest",
                _hex64(
                    self.opening_period_close_digest,
                    "opening_period_close_digest",
                    nullable=True,
                ),
            )

    def contains(self, when: datetime) -> bool:
        current = _utc(when, "when")
        return self.starts_at <= current < self.ends_at

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": PERIOD_SCHEMA,
            "period_id": self.period_id,
            "starts_at": self.starts_at.isoformat().replace("+00:00", "Z"),
            "ends_at": self.ends_at.isoformat().replace("+00:00", "Z"),
            "accounting_perimeter": self.accounting_perimeter,
            "reporting_currency": self.reporting_currency,
            "accounting_policy_digest": self.accounting_policy_digest,
            "requirement_registry_digest": self.requirement_registry_digest,
            "opening_period_close_digest": self.opening_period_close_digest,
            "authority": self.authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


@dataclass(frozen=True)
class AccountingPeriodCloseV1:
    period_id: str
    accounting_period_digest: str
    accounting_close_digest: str
    financial_snapshot_digest: str
    previous_period_close_digest: str | None
    adjustment_authorization_digests: tuple[str, ...]
    closed_at: datetime
    authority: str = "FINANCIAL_OS_PERIOD_CLOSE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_PERIOD_CLOSE" or self.execution_authority != "NONE":
            raise AccountingPeriodV1Error("period close is a Financial OS sealing fact")
        object.__setattr__(self, "period_id", _text(self.period_id, "period_id"))
        for name in (
            "accounting_period_digest",
            "accounting_close_digest",
            "financial_snapshot_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        if self.previous_period_close_digest is not None:
            object.__setattr__(
                self,
                "previous_period_close_digest",
                _hex64(
                    self.previous_period_close_digest,
                    "previous_period_close_digest",
                    nullable=True,
                ),
            )
        adjustments = tuple(sorted({_hex64(item, "adjustment_authorization_digest") for item in self.adjustment_authorization_digests}))
        object.__setattr__(self, "adjustment_authorization_digests", adjustments)
        object.__setattr__(self, "closed_at", _utc(self.closed_at, "closed_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": PERIOD_CLOSE_SCHEMA,
            "period_id": self.period_id,
            "accounting_period_digest": self.accounting_period_digest,
            "accounting_close_digest": self.accounting_close_digest,
            "financial_snapshot_digest": self.financial_snapshot_digest,
            "previous_period_close_digest": self.previous_period_close_digest,
            "adjustment_authorization_digests": list(self.adjustment_authorization_digests),
            "closed_at": self.closed_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def build_period_close_v1(
    period: AccountingPeriodV1,
    accounting_close: AccountingCloseV2,
    *,
    adjustment_authorization_digests: Iterable[str] = (),
    closed_at: datetime,
) -> AccountingPeriodCloseV1:
    close_time = _utc(closed_at, "closed_at")
    if close_time < period.ends_at:
        raise AccountingPeriodV1Error("period cannot close before its end")
    if accounting_close.closed_at > close_time:
        raise AccountingPeriodV1Error("period close cannot precede AccountingClose")
    if accounting_close.requirement_registry_digest != period.requirement_registry_digest:
        raise AccountingPeriodV1Error("period/AccountingClose requirement registry mismatch")
    return AccountingPeriodCloseV1(
        period_id=period.period_id,
        accounting_period_digest=period.digest,
        accounting_close_digest=accounting_close.digest,
        financial_snapshot_digest=accounting_close.financial_snapshot_digest,
        previous_period_close_digest=period.opening_period_close_digest,
        adjustment_authorization_digests=tuple(adjustment_authorization_digests),
        closed_at=close_time,
    )
