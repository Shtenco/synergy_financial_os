from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal


ZERO = Decimal("0")
ONE = Decimal("1")
FEE_ROLES = frozenset(
    {"PROTOCOL_REVENUE", "PROVIDER_COST", "NETWORK_COST", "TAX", "OTHER"}
)
AUTO_PNL_SIGNS = {
    "PROTOCOL_REVENUE": ONE,
    "PROVIDER_COST": Decimal("-1"),
    "NETWORK_COST": Decimal("-1"),
    "TAX": ZERO,
    "OTHER": ZERO,
}


def _d(value: Decimal | int | str, field_name: str = "value") -> Decimal:
    return finite_decimal(value, field_name)


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def _canonical_digest(payload: Any) -> str:
    return canonical_json_digest(payload)


def _require_canonical_nonnegative_decimal(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise AccountingInvariantError(f"{field_name} must be a canonical decimal string")
    amount = _d(value, field_name)
    if amount < ZERO:
        raise AccountingInvariantError(f"{field_name} must be non-negative")
    expected = canonical_decimal_text(amount, field_name)
    if value != expected:
        raise AccountingInvariantError(
            f"{field_name} is not canonical decimal text: expected {expected!r}, got {value!r}"
        )
    return amount


def _require_timezone_aware_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AccountingInvariantError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AccountingInvariantError(f"{field_name} must be ISO-8601 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AccountingInvariantError(f"{field_name} must be timezone-aware")
    return parsed


def verify_settlement_receipt_for_accounting(receipt: Mapping[str, Any]) -> str:
    """Verify finality/evidence/canonical-byte conditions for accounting use.

    MetaPay may export pending or merely terminal receipts for operational use.
    Financial OS is stricter: automatic accounting preparation accepts only a
    finalized, reconciled, externally evidence-bound `SETTLED` receipt.
    Payment principal/notional is still not classified as P&L here.
    """

    if receipt.get("schema") != "settlement.receipt/v1":
        raise AccountingInvariantError("unsupported settlement receipt schema")
    if receipt.get("status") != "SETTLED":
        raise AccountingInvariantError("accounting bridge accepts only SETTLED receipts")
    if receipt.get("reconciled") is not True:
        raise AccountingInvariantError("settlement must be reconciled before accounting use")

    _require_timezone_aware_datetime(receipt.get("finality_time"), "finality_time")
    _require_canonical_nonnegative_decimal(receipt.get("source_amount"), "source_amount")
    if receipt.get("target_amount") is None:
        raise AccountingInvariantError("settled receipt requires a final target_amount")
    _require_canonical_nonnegative_decimal(receipt.get("target_amount"), "target_amount")

    evidence_digest = receipt.get("evidence_digest")
    if not isinstance(evidence_digest, str):
        raise AccountingInvariantError("accounting settlement requires evidence_digest")
    _hex64(evidence_digest, "settlement evidence_digest")

    evidence_classes = receipt.get("external_evidence_classes")
    if not isinstance(evidence_classes, list) or not evidence_classes:
        raise AccountingInvariantError(
            "accounting settlement requires at least one external evidence class"
        )
    if len(evidence_classes) != len(set(evidence_classes)):
        raise AccountingInvariantError("external evidence classes must be unique")

    providers = receipt.get("providers")
    if not isinstance(providers, list) or any(
        not isinstance(provider, str) or not provider.strip() for provider in providers
    ):
        raise AccountingInvariantError("providers must be an array of non-empty strings")
    if len(providers) != len(set(providers)):
        raise AccountingInvariantError("providers must be unique")

    external_references = receipt.get("external_references")
    if not isinstance(external_references, list) or any(
        not isinstance(reference, str) or not reference.strip()
        for reference in external_references
    ):
        raise AccountingInvariantError(
            "external_references must be an array of non-empty strings"
        )
    if len(external_references) != len(set(external_references)):
        raise AccountingInvariantError("external_references must be unique")

    fees = receipt.get("fees")
    if not isinstance(fees, list):
        raise AccountingInvariantError("settlement fees must be a list")
    for index, fee in enumerate(fees):
        if not isinstance(fee, Mapping):
            raise AccountingInvariantError("settlement fee must be an object")
        role_raw = fee.get("economic_role")
        if not isinstance(role_raw, str):
            raise AccountingInvariantError("settlement fee economic_role is required")
        role = role_raw.strip()
        if role != role.upper() or role not in FEE_ROLES:
            raise AccountingInvariantError(f"unsupported settlement fee economic_role: {role}")
        _require_canonical_nonnegative_decimal(
            fee.get("amount"),
            f"fees[{index}].amount",
        )
        asset = str(fee.get("asset", "")).upper().strip()
        if not asset:
            raise AccountingInvariantError("settlement fee asset is required")
        kind = str(fee.get("kind", "")).strip()
        if not kind:
            raise AccountingInvariantError("settlement fee kind is required")

    return _canonical_digest(dict(receipt))


@dataclass(frozen=True)
class FeeTranslation:
    source_asset: str
    reporting_currency: str
    reporting_units_per_source_unit: Decimal
    translation_evidence_digest: str | None = None

    def __post_init__(self) -> None:
        source = self.source_asset.upper().strip()
        reporting = self.reporting_currency.upper().strip()
        rate = _d(
            self.reporting_units_per_source_unit,
            "reporting_units_per_source_unit",
        )
        if not source or not reporting:
            raise AccountingInvariantError("source_asset and reporting_currency are required")
        if rate <= ZERO:
            raise AccountingInvariantError(
                "reporting_units_per_source_unit must be strictly positive"
            )
        evidence = self.translation_evidence_digest
        if source == reporting:
            if rate != ONE:
                raise AccountingInvariantError("same-currency fee translation rate must be 1")
        elif evidence is None:
            raise AccountingInvariantError(
                "foreign-currency fee translation requires an evidence digest"
            )
        if evidence is not None:
            evidence = _hex64(evidence, "translation_evidence_digest")

        object.__setattr__(self, "source_asset", source)
        object.__setattr__(self, "reporting_currency", reporting)
        object.__setattr__(self, "reporting_units_per_source_unit", rate)
        object.__setattr__(self, "translation_evidence_digest", evidence)


@dataclass(frozen=True)
class TranslatedSettlementFee:
    receipt_digest: str
    settlement_evidence_digest: str
    asset: str
    source_amount: Decimal
    reporting_currency: str
    reporting_amount: Decimal
    kind: str
    economic_role: str
    provider_ref: str | None
    translation_evidence_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipt_digest",
            _hex64(self.receipt_digest, "receipt_digest"),
        )
        object.__setattr__(
            self,
            "settlement_evidence_digest",
            _hex64(self.settlement_evidence_digest, "settlement_evidence_digest"),
        )
        source_amount = _d(self.source_amount, "source_amount")
        reporting_amount = _d(self.reporting_amount, "reporting_amount")
        if source_amount < ZERO or reporting_amount < ZERO:
            raise AccountingInvariantError("translated fee amounts must be non-negative")
        object.__setattr__(self, "source_amount", source_amount)
        object.__setattr__(self, "reporting_amount", reporting_amount)

    @property
    def automatic_pnl_effect(self) -> Decimal:
        """Return only mechanically classifiable P&L.

        TAX and OTHER intentionally return zero because tax can be either an
        expense or a pass-through liability and OTHER requires explicit review.
        """

        return self.reporting_amount * AUTO_PNL_SIGNS[self.economic_role]


def translate_settlement_fees(
    receipt: Mapping[str, Any],
    *,
    reporting_currency: str,
    translations: Mapping[str, FeeTranslation] | None = None,
) -> tuple[TranslatedSettlementFee, ...]:
    """Translate observed fee components without posting the ledger.

    Payment principal/notional is intentionally ignored here. This function only
    prepares fee-level accounting evidence. A later accounting step must map each
    recognized component to balanced reporting-ledger accounts.
    """

    receipt_digest = verify_settlement_receipt_for_accounting(receipt)
    reporting = reporting_currency.upper().strip()
    if not reporting:
        raise AccountingInvariantError("reporting_currency is required")
    translation_map = {
        key.upper().strip(): value for key, value in dict(translations or {}).items()
    }
    settlement_evidence = _hex64(
        str(receipt["evidence_digest"]),
        "settlement evidence_digest",
    )

    result: list[TranslatedSettlementFee] = []
    for fee in receipt["fees"]:
        asset = str(fee["asset"]).upper().strip()
        amount = _require_canonical_nonnegative_decimal(fee["amount"], "fee.amount")
        role = str(fee["economic_role"]).upper().strip()

        if asset == reporting:
            translation = FeeTranslation(asset, reporting, ONE)
        else:
            try:
                translation = translation_map[asset]
            except KeyError as exc:
                raise AccountingInvariantError(
                    f"missing fee translation for {asset}->{reporting}"
                ) from exc
            if translation.source_asset != asset or translation.reporting_currency != reporting:
                raise AccountingInvariantError(
                    f"fee translation does not match {asset}->{reporting}"
                )

        reporting_amount = _d(
            amount * translation.reporting_units_per_source_unit,
            "translated reporting_amount",
        )
        result.append(
            TranslatedSettlementFee(
                receipt_digest=receipt_digest,
                settlement_evidence_digest=settlement_evidence,
                asset=asset,
                source_amount=amount,
                reporting_currency=reporting,
                reporting_amount=reporting_amount,
                kind=str(fee["kind"]),
                economic_role=role,
                provider_ref=fee.get("provider_ref"),
                translation_evidence_digest=translation.translation_evidence_digest,
            )
        )
    return tuple(result)


def automatic_fee_pnl(
    translated_fees: tuple[TranslatedSettlementFee, ...],
) -> Decimal:
    """Sum only explicit protocol revenue and provider/network costs."""

    return sum((fee.automatic_pnl_effect for fee in translated_fees), ZERO)
