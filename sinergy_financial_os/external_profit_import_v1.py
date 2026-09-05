from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence

from .core import AccountingInvariantError
from .reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingEntry,
    ReportingLedger,
    ReportingLine,
)

ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
SCHEMA = "external-profit.import-envelope/v1"


class ExternalProfitImportError(AccountingInvariantError):
    pass


class ImportDisposition(str, Enum):
    POSTABLE_REALIZED_EXTERNAL_PNL = "POSTABLE_REALIZED_EXTERNAL_PNL"
    CLASSIFICATION_REQUIRED = "CLASSIFICATION_REQUIRED"
    NO_PNL = "NO_PNL"
    REJECTED = "REJECTED"


POSTABLE_CLASSIFICATION = "REALIZED_EXTERNAL_PNL"
CLASSIFICATION_REQUIRED_CLASSIFICATION = (
    "EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION"
)
NO_PNL_CLASSIFICATIONS = frozenset(
    {
        "CAPITAL_REALLOCATION_PNL_ZERO",
        "INTERNAL_MARK_NOT_EXTERNAL_VALUE",
        "NOT_REALIZED",
        "NON_POSITIVE_EXTERNAL_PNL",
    }
)
REJECTED_CLASSIFICATIONS = frozenset({"INADMISSIBLE"})


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalProfitImportError(f"{field_name} is required")
    return value.strip()


def _hex64(value: object, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(char not in HEX for char in result):
        raise ExternalProfitImportError(f"{field_name} must be hex64")
    return result


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal normalizes the message poorly
        raise ExternalProfitImportError(f"{field_name} must be Decimal-compatible") from exc
    if not result.is_finite():
        raise ExternalProfitImportError(f"{field_name} must be finite")
    return result


@dataclass(frozen=True)
class ExternalProfitImportEnvelopeV1:
    evidence_id: str
    source: str
    classification: str
    settlement_asset: str
    canonical_external_pnl: Decimal
    external_cash_delta: Decimal
    admissible_for_financial_os_pnl: bool
    evidence_digest: str
    route_digest: str
    provider_references: tuple[str, ...]
    source_repository: str
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ExternalProfitImportError("unsupported external-profit import schema")
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "classification", _text(self.classification, "classification"))
        object.__setattr__(
            self,
            "settlement_asset",
            _text(self.settlement_asset, "settlement_asset").upper(),
        )
        pnl = _decimal(self.canonical_external_pnl, "canonical_external_pnl")
        cash_delta = _decimal(self.external_cash_delta, "external_cash_delta")
        if pnl < ZERO:
            raise ExternalProfitImportError("canonical_external_pnl cannot be negative")
        object.__setattr__(self, "canonical_external_pnl", pnl)
        object.__setattr__(self, "external_cash_delta", cash_delta)
        if not isinstance(self.admissible_for_financial_os_pnl, bool):
            raise ExternalProfitImportError(
                "admissible_for_financial_os_pnl must be JSON boolean"
            )
        object.__setattr__(
            self, "evidence_digest", _hex64(self.evidence_digest, "evidence_digest")
        )
        object.__setattr__(self, "route_digest", _hex64(self.route_digest, "route_digest"))
        refs = tuple(_text(item, "provider_references[]") for item in self.provider_references)
        if not refs:
            raise ExternalProfitImportError("provider_references must be non-empty")
        object.__setattr__(self, "provider_references", refs)
        object.__setattr__(
            self, "source_repository", _text(self.source_repository, "source_repository")
        )
        clean_metadata: dict[str, str] = {}
        for key, value in dict(self.metadata).items():
            clean_metadata[_text(key, "metadata key")] = _text(value, f"metadata[{key}]")
        object.__setattr__(self, "metadata", clean_metadata)


@dataclass(frozen=True)
class ExternalProfitImportDecisionV1:
    evidence_id: str
    disposition: ImportDisposition
    postable_amount: Decimal
    settlement_asset: str
    reasons: tuple[str, ...]


class ExternalProfitImporterV1:
    """Financial OS boundary for MetaPay/DEX realized external-profit evidence.

    The importer never values internal mint, internal marks or TVL. It accepts only
    MetaPay's already fail-closed `REALIZED_EXTERNAL_PNL` classification and still
    independently re-checks amount, evidence binding, account semantics and currency.

    V1 deliberately posts only when the externally settled asset equals the reporting
    currency. Cross-currency settlement requires a later explicit valuation/FX evidence
    generation; USD and USDT are never treated as interchangeable.
    """

    def classify(
        self, envelope: ExternalProfitImportEnvelopeV1
    ) -> ExternalProfitImportDecisionV1:
        classification = envelope.classification

        if classification == POSTABLE_CLASSIFICATION:
            reasons: list[str] = []
            if not envelope.admissible_for_financial_os_pnl:
                reasons.append("source decision does not admit the item for Financial OS P&L")
            if envelope.canonical_external_pnl <= ZERO:
                reasons.append("realized external P&L must be strictly positive")
            if envelope.external_cash_delta < envelope.canonical_external_pnl:
                reasons.append("canonical P&L cannot exceed the externally settled cash delta")
            if reasons:
                return ExternalProfitImportDecisionV1(
                    evidence_id=envelope.evidence_id,
                    disposition=ImportDisposition.REJECTED,
                    postable_amount=ZERO,
                    settlement_asset=envelope.settlement_asset,
                    reasons=tuple(reasons),
                )
            return ExternalProfitImportDecisionV1(
                evidence_id=envelope.evidence_id,
                disposition=ImportDisposition.POSTABLE_REALIZED_EXTERNAL_PNL,
                postable_amount=envelope.canonical_external_pnl,
                settlement_asset=envelope.settlement_asset,
                reasons=("positive realized external P&L remains evidence-bound",),
            )

        if classification == CLASSIFICATION_REQUIRED_CLASSIFICATION:
            return ExternalProfitImportDecisionV1(
                evidence_id=envelope.evidence_id,
                disposition=ImportDisposition.CLASSIFICATION_REQUIRED,
                postable_amount=ZERO,
                settlement_asset=envelope.settlement_asset,
                reasons=(
                    "external cash may exist but revenue/equity/liability classification is unresolved",
                ),
            )

        if classification in NO_PNL_CLASSIFICATIONS:
            return ExternalProfitImportDecisionV1(
                evidence_id=envelope.evidence_id,
                disposition=ImportDisposition.NO_PNL,
                postable_amount=ZERO,
                settlement_asset=envelope.settlement_asset,
                reasons=(f"{classification} is not canonical realized P&L",),
            )

        if classification in REJECTED_CLASSIFICATIONS:
            return ExternalProfitImportDecisionV1(
                evidence_id=envelope.evidence_id,
                disposition=ImportDisposition.REJECTED,
                postable_amount=ZERO,
                settlement_asset=envelope.settlement_asset,
                reasons=("source evidence is inadmissible",),
            )

        raise ExternalProfitImportError(
            f"unsupported external-profit classification: {classification}"
        )

    def post_realized_pnl(
        self,
        ledger: ReportingLedger,
        envelope: ExternalProfitImportEnvelopeV1,
        *,
        event_id: str,
        reference: str,
        external_cash_account_id: str,
        external_profit_revenue_account_id: str,
    ) -> ReportingEntry:
        decision = self.classify(envelope)
        if decision.disposition != ImportDisposition.POSTABLE_REALIZED_EXTERNAL_PNL:
            raise ExternalProfitImportError(
                f"external-profit item is not postable: {decision.disposition.value}"
            )
        if ledger.reporting_currency != envelope.settlement_asset:
            raise ExternalProfitImportError(
                "settlement asset differs from reporting currency; explicit FX/valuation "
                "evidence is required and USD/USDT cannot be conflated"
            )

        cash_account = ledger.account(external_cash_account_id)
        revenue_account = ledger.account(external_profit_revenue_account_id)
        if (
            cash_account.account_class != AccountClass.ASSET
            or cash_account.consolidation_class != ConsolidationClass.EXTERNAL
        ):
            raise ExternalProfitImportError(
                "external cash target must be an EXTERNAL ASSET account"
            )
        if (
            revenue_account.account_class != AccountClass.REVENUE
            or revenue_account.consolidation_class != ConsolidationClass.EXTERNAL
        ):
            raise ExternalProfitImportError(
                "external profit target must be an EXTERNAL REVENUE account"
            )

        amount = decision.postable_amount
        metadata = {
            "economic_class": "REALIZED_EXTERNAL_ARBITRAGE_PNL",
            "source": envelope.source,
            "source_repository": envelope.source_repository,
            "settlement_asset": envelope.settlement_asset,
            "route_digest": envelope.route_digest,
            "provider_references": "|".join(envelope.provider_references),
            **dict(envelope.metadata),
        }
        return ledger.post(
            event_id=_text(event_id, "event_id"),
            reference=_text(reference, "reference"),
            flow_type=FlowType.EXTERNAL_REVENUE,
            lines=(
                ReportingLine(account_id=external_cash_account_id, debit=amount),
                ReportingLine(account_id=external_profit_revenue_account_id, credit=amount),
            ),
            evidence_digest=envelope.evidence_digest,
            metadata=metadata,
        )


def envelope_from_mapping_v1(payload: Mapping[str, object]) -> ExternalProfitImportEnvelopeV1:
    refs = payload.get("provider_references")
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
        raise ExternalProfitImportError("provider_references must be an array")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ExternalProfitImportError("metadata must be an object")
    return ExternalProfitImportEnvelopeV1(
        schema=_text(payload.get("schema", SCHEMA), "schema"),
        evidence_id=_text(payload.get("evidence_id"), "evidence_id"),
        source=_text(payload.get("source"), "source"),
        classification=_text(payload.get("classification"), "classification"),
        settlement_asset=_text(payload.get("settlement_asset"), "settlement_asset"),
        canonical_external_pnl=_decimal(
            payload.get("canonical_external_pnl"), "canonical_external_pnl"
        ),
        external_cash_delta=_decimal(payload.get("external_cash_delta"), "external_cash_delta"),
        admissible_for_financial_os_pnl=payload.get("admissible_for_financial_os_pnl"),
        evidence_digest=_hex64(payload.get("evidence_digest"), "evidence_digest"),
        route_digest=_hex64(payload.get("route_digest"), "route_digest"),
        provider_references=tuple(str(item) for item in refs),
        source_repository=_text(payload.get("source_repository"), "source_repository"),
        metadata={str(key): str(value) for key, value in metadata.items()},
    )
