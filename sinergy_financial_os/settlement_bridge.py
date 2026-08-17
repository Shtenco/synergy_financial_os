from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .core import AccountingInvariantError


ZERO = Decimal("0")
FEE_ROLES = frozenset(
    {"PROTOCOL_REVENUE", "PROVIDER_COST", "NETWORK_COST", "TAX", "OTHER"}
)
AUTO_PNL_SIGNS = {
    "PROTOCOL_REVENUE": Decimal("1"),
    "PROVIDER_COST": Decimal("-1"),
    "NETWORK_COST": Decimal("-1"),
    "TAX": ZERO,
    "OTHER": ZERO,
}


def _d(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_settlement_receipt_for_accounting(receipt: Mapping[str, Any]) -> str:
    """Verify minimum finality/evidence conditions for accounting consumption.

    MetaPay may export pending or merely terminal receipts for operational use.
    Financial OS is stricter: automatic accounting preparation accepts only a
    finalized, reconciled, externally evidence-bound `SETTLED` receipt.
    """

    if receipt.get("schema") != "settlement.receipt/v1":
        raise AccountingInvariantError("unsupported settlement receipt schema")
    if receipt.get("status") != "SETTLED":
        raise AccountingInvariantError("accounting bridge accepts only SETTLED receipts")
    if receipt.get("reconciled") is not True:
        raise AccountingInvariantError("settlement must be reconciled before accounting use")
    if not receipt.get("finality_time"):
        raise AccountingInvariantError("settled receipt requires finality_time")
    if receipt.get("target_amount") is None:
        raise AccountingInvariantError("settled receipt requires a final target_amount")

    evidence_digest = receipt.get("evidence_digest")
    if not isinstance(evidence_digest, str):
        raise AccountingInvariantError("accounting settlement requires evidence_digest")
    _hex64(evidence_digest, "settlement evidence_digest")

    evidence_classes = receipt.get("external_evidence_classes")
    if not isinstance(evidence_classes, list) or not evidence_classes:
        raise AccountingInvariantError(
            "accounting settlement requires at least one external evidence class"
        )

    fees = receipt.get("fees")
    if not isinstance(fees, list):
        raise AccountingInvariantError("settlement fees must be a list")
    for fee in fees:
        if not isinstance(fee, Mapping):
            raise AccountingInvariantError("settlement fee must be an object")
        role = str(fee.get("economic_role", "")).upper().strip()
        if role not in FEE_ROLES:
            raise AccountingInvariantError(f"unsupported settlement fee economic_role: {role}")
        amount = _d(fee.get("amount", "-1"))
        if amount < ZERO:
            raise AccountingInvariantError("settlement fee amount must be non-negative")
        asset = str(fee.get("asset", "")).upper().strip()
        if not asset:
            raise AccountingInvariantError("settlement fee asset is required")

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
        rate = _d(self.reporting_units_per_source_unit)
        if not source or not reporting:
            raise AccountingInvariantError("source_asset and reporting_currency are required")
        if rate <= ZERO:
            raise AccountingInvariantError(
                "reporting_units_per_source_unit must be strictly positive"
            )
        evidence = self.translation_evidence_digest
        if source == reporting:
            if rate != Decimal("1"):
                raise AccountingInvariantError("same-currency fee translation rate must be 1")
        else:
            if evidence is None:
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
        amount = _d(fee["amount"])
        role = str(fee["economic_role"]).upper().strip()

        if asset == reporting:
            translation = FeeTranslation(asset, reporting, Decimal("1"))
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

        result.append(
            TranslatedSettlementFee(
                receipt_digest=receipt_digest,
                settlement_evidence_digest=settlement_evidence,
                asset=asset,
                source_amount=amount,
                reporting_currency=reporting,
                reporting_amount=amount * translation.reporting_units_per_source_unit,
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
