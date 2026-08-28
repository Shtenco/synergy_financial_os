from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .maturity_bridge import MaturityTranslation, verify_maturity_snapshot_digest
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "maturity.translation/v1"
ZERO = Decimal("0")
ONE = Decimal("1")
HEX = frozenset("0123456789abcdef")


class MaturityTranslationV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaturityTranslationV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise MaturityTranslationV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MaturityTranslationV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class MaturityTranslationArtifactV1:
    maturity_snapshot_digest: str
    source_currency: str
    reporting_currency: str
    reporting_units_per_source_unit: Decimal
    as_of: datetime
    translation_evidence_digest: str | None
    generated_at: datetime
    authority: str = "FINANCIAL_OS_MATURITY_TRANSLATION"
    accounting_authority: str = "REFERENCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_MATURITY_TRANSLATION":
            raise MaturityTranslationV1Error("maturity translation authority must remain Financial OS")
        if self.accounting_authority != "REFERENCE_ONLY" or self.execution_authority != "NONE":
            raise MaturityTranslationV1Error("maturity translation cannot mutate accounting or execute")
        source = _text(self.source_currency, "source_currency").upper()
        reporting = _text(self.reporting_currency, "reporting_currency").upper()
        rate = finite_decimal(self.reporting_units_per_source_unit, "reporting_units_per_source_unit")
        if rate <= ZERO:
            raise MaturityTranslationV1Error("translation rate must be strictly positive")
        evidence = self.translation_evidence_digest
        if source == reporting:
            if rate != ONE:
                raise MaturityTranslationV1Error("same-currency translation rate must equal 1")
            if evidence is not None:
                evidence = _hex64(evidence, "translation_evidence_digest", nullable=True)
        else:
            if evidence is None:
                raise MaturityTranslationV1Error("cross-currency translation requires evidence digest")
            evidence = _hex64(evidence, "translation_evidence_digest", nullable=True)
        as_of = _utc(self.as_of, "as_of")
        generated = _utc(self.generated_at, "generated_at")
        if generated < as_of:
            raise MaturityTranslationV1Error("translation cannot be generated before as_of")
        object.__setattr__(self, "maturity_snapshot_digest", _hex64(self.maturity_snapshot_digest, "maturity_snapshot_digest"))
        object.__setattr__(self, "source_currency", source)
        object.__setattr__(self, "reporting_currency", reporting)
        object.__setattr__(self, "reporting_units_per_source_unit", rate)
        object.__setattr__(self, "translation_evidence_digest", evidence)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "generated_at", generated)

    def to_translation(self) -> MaturityTranslation:
        return MaturityTranslation(
            self.source_currency,
            self.reporting_currency,
            self.reporting_units_per_source_unit,
            translation_evidence_digest=self.translation_evidence_digest,
        )

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "maturity_snapshot_digest": self.maturity_snapshot_digest,
            "source_currency": self.source_currency,
            "reporting_currency": self.reporting_currency,
            "reporting_units_per_source_unit": canonical_decimal_text(self.reporting_units_per_source_unit),
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "translation_evidence_digest": self.translation_evidence_digest,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "accounting_authority": self.accounting_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_maturity_translation_artifact_v1(
    maturity_snapshot: Mapping[str, Any],
    *,
    reporting_currency: str,
    reporting_units_per_source_unit: Decimal | int | str,
    translation_evidence_digest: str | None,
    generated_at: datetime,
) -> MaturityTranslationArtifactV1:
    digest = verify_maturity_snapshot_digest(maturity_snapshot)
    source = _text(maturity_snapshot.get("currency"), "maturity snapshot currency").upper()
    as_of_raw = _text(maturity_snapshot.get("as_of"), "maturity snapshot as_of")
    try:
        as_of = datetime.fromisoformat(as_of_raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise MaturityTranslationV1Error("maturity snapshot as_of is invalid") from exc
    return MaturityTranslationArtifactV1(
        maturity_snapshot_digest=digest,
        source_currency=source,
        reporting_currency=reporting_currency,
        reporting_units_per_source_unit=reporting_units_per_source_unit,
        as_of=as_of,
        translation_evidence_digest=translation_evidence_digest,
        generated_at=generated_at,
    )
