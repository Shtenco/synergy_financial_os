from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .core import AccountingInvariantError
from .reporting import (
    AccountClass,
    ConsolidationClass,
    ReportingAccountSpec,
    ReportingLedger,
)


SCHEMA = "account.registry/v1"
HEX = frozenset("0123456789abcdef")


class AccountRegistryV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountRegistryV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise AccountRegistryV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountRegistryV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def account_registry_digest_v1(accounts: Iterable[ReportingAccountSpec]) -> str:
    values = tuple(accounts)
    if not values:
        raise AccountRegistryV1Error("account registry requires at least one account")
    if any(not isinstance(item, ReportingAccountSpec) for item in values):
        raise AccountRegistryV1Error("account registry accepts ReportingAccountSpec only")
    ordered = tuple(sorted(values, key=lambda item: item.account_id))
    ids = [item.account_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise AccountRegistryV1Error("account registry contains duplicate account_id")
    return _digest([item.canonical_dict() for item in ordered])


@dataclass(frozen=True)
class AccountRegistryV1:
    reporting_currency: str
    accounts: tuple[ReportingAccountSpec, ...]
    generated_at: datetime
    authority: str = "FINANCIAL_OS_ACCOUNT_REGISTRY"
    ledger_mutation_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        currency = _text(self.reporting_currency, "reporting_currency").upper()
        accounts = tuple(sorted(self.accounts, key=lambda item: item.account_id))
        if not accounts or any(not isinstance(item, ReportingAccountSpec) for item in accounts):
            raise AccountRegistryV1Error("accounts must contain ReportingAccountSpec values")
        ids = [item.account_id for item in accounts]
        if len(ids) != len(set(ids)):
            raise AccountRegistryV1Error("account registry contains duplicate account_id")
        if self.authority != "FINANCIAL_OS_ACCOUNT_REGISTRY":
            raise AccountRegistryV1Error("account-registry authority must remain Financial OS")
        if self.ledger_mutation_authority != "NONE" or self.execution_authority != "NONE":
            raise AccountRegistryV1Error("account registry cannot mutate ledger or execute actions")
        object.__setattr__(self, "reporting_currency", currency)
        object.__setattr__(self, "accounts", accounts)
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    @property
    def account_registry_digest(self) -> str:
        return account_registry_digest_v1(self.accounts)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "reporting_currency": self.reporting_currency,
            "accounts": [item.canonical_dict() for item in self.accounts],
            "account_registry_digest": self.account_registry_digest,
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

    def instantiate_empty_reporting_ledger(self) -> ReportingLedger:
        ledger = ReportingLedger(self.reporting_currency)
        for spec in self.accounts:
            ledger.register_account(spec)
        if ledger.account_registry_digest != self.account_registry_digest:
            raise AccountRegistryV1Error("reconstructed ReportingLedger account registry digest mismatch")
        return ledger


def build_account_registry_v1(
    accounts: Iterable[ReportingAccountSpec],
    *,
    reporting_currency: str,
    generated_at: datetime,
    expected_ledger: ReportingLedger | None = None,
) -> AccountRegistryV1:
    registry = AccountRegistryV1(
        reporting_currency=reporting_currency,
        accounts=tuple(accounts),
        generated_at=generated_at,
    )
    if expected_ledger is not None:
        if expected_ledger.reporting_currency != registry.reporting_currency:
            raise AccountRegistryV1Error("expected ledger reporting currency mismatch")
        if expected_ledger.account_registry_digest != registry.account_registry_digest:
            raise AccountRegistryV1Error("account registry does not match expected ReportingLedger")
    return registry


def verify_account_registry_payload_v1(payload: Mapping[str, Any]) -> AccountRegistryV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != SCHEMA:
        raise AccountRegistryV1Error("unsupported account registry schema")
    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        raise AccountRegistryV1Error("account registry accounts must be non-empty array")
    accounts: list[ReportingAccountSpec] = []
    for index, raw in enumerate(raw_accounts):
        if not isinstance(raw, Mapping):
            raise AccountRegistryV1Error(f"accounts[{index}] must be object")
        try:
            account_class = AccountClass(_text(raw.get("account_class"), f"accounts[{index}].account_class"))
            consolidation_class = ConsolidationClass(
                _text(raw.get("consolidation_class"), f"accounts[{index}].consolidation_class")
            )
        except ValueError as exc:
            raise AccountRegistryV1Error(f"accounts[{index}] has unsupported enum value") from exc
        spec = ReportingAccountSpec(
            account_id=_text(raw.get("account_id"), f"accounts[{index}].account_id"),
            name=_text(raw.get("name"), f"accounts[{index}].name"),
            account_class=account_class,
            consolidation_class=consolidation_class,
            valuation_class=_text(raw.get("valuation_class"), f"accounts[{index}].valuation_class"),
            immediate_liability=raw.get("immediate_liability", False),
        )
        if raw.get("normal_side") != spec.normal_side:
            raise AccountRegistryV1Error(f"accounts[{index}].normal_side mismatch")
        if dict(raw) != spec.canonical_dict():
            raise AccountRegistryV1Error(f"accounts[{index}] is not canonical ReportingAccountSpec payload")
        accounts.append(spec)
    generated_text = _text(payload.get("generated_at"), "generated_at")
    if not generated_text.endswith("Z"):
        raise AccountRegistryV1Error("generated_at must use canonical UTC Z time")
    try:
        generated = datetime.fromisoformat(generated_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AccountRegistryV1Error("generated_at is invalid") from exc
    registry = AccountRegistryV1(
        reporting_currency=_text(payload.get("reporting_currency"), "reporting_currency"),
        accounts=tuple(accounts),
        generated_at=generated,
        authority=_text(payload.get("authority"), "authority"),
        ledger_mutation_authority=_text(payload.get("ledger_mutation_authority"), "ledger_mutation_authority"),
        execution_authority=_text(payload.get("execution_authority"), "execution_authority"),
    )
    if _hex64(payload.get("account_registry_digest"), "account_registry_digest") != registry.account_registry_digest:
        raise AccountRegistryV1Error("account_registry_digest mismatch")
    if _hex64(payload.get("digest"), "digest") != registry.digest:
        raise AccountRegistryV1Error("account registry artifact digest mismatch")
    if registry.to_dict() != dict(payload):
        raise AccountRegistryV1Error("account registry payload is not canonical")
    return registry


def verify_account_registry_against_snapshot_v1(
    registry: AccountRegistryV1,
    financial_snapshot: Mapping[str, Any],
) -> bool:
    if financial_snapshot.get("schema") != "financial.snapshot/v2":
        raise AccountRegistryV1Error("financial snapshot must use financial.snapshot/v2")
    if financial_snapshot.get("reporting_currency") != registry.reporting_currency:
        raise AccountRegistryV1Error("snapshot/account-registry reporting currency mismatch")
    if _hex64(financial_snapshot.get("account_registry_digest"), "snapshot.account_registry_digest") != registry.account_registry_digest:
        raise AccountRegistryV1Error("snapshot account_registry_digest mismatch")
    return True
