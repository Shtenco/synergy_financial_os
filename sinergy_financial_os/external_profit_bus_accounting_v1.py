from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any

D = Decimal


class ExternalProfitClassification(StrEnum):
    REALIZED_EXTERNAL_PNL = "REALIZED_EXTERNAL_PNL"
    EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION = (
        "EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION"
    )
    CAPITAL_REALLOCATION_PNL_ZERO = "CAPITAL_REALLOCATION_PNL_ZERO"
    INTERNAL_MARK_NOT_EXTERNAL_VALUE = "INTERNAL_MARK_NOT_EXTERNAL_VALUE"
    NOT_REALIZED = "NOT_REALIZED"
    NON_POSITIVE_EXTERNAL_PNL = "NON_POSITIVE_EXTERNAL_PNL"
    INADMISSIBLE = "INADMISSIBLE"


class AccountingAction(StrEnum):
    POST_REALIZED_EXTERNAL_PNL = "POST_REALIZED_EXTERNAL_PNL"
    REQUIRE_HUMAN_ACCOUNTING_CLASSIFICATION = "REQUIRE_HUMAN_ACCOUNTING_CLASSIFICATION"
    NO_PNL_POSTING = "NO_PNL_POSTING"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class ExternalProfitBusPayload:
    """Cross-repo payload consumed from MetaPay/DEX evidence classification.

    Financial OS never trusts an internal mark as P&L. The producer must present a
    classification plus the exact canonical external P&L admitted by the upstream
    External Profit Bus. This consumer independently rechecks the economic invariants
    before preparing accounting instructions.
    """

    evidence_id: str
    source: str
    settlement_asset: str
    classification: ExternalProfitClassification
    canonical_external_pnl: Decimal
    external_cash_delta: Decimal
    settlement_realized: bool
    independent_external_counterparty: bool
    flash_principal_repaid: bool
    provider_references: tuple[str, ...] = ()
    route_digest: str | None = None
    internal_mint_quantity: Decimal = D("0")
    internal_mark_delta: Decimal = D("0")


@dataclass(frozen=True, slots=True)
class AccountingInstruction:
    debit_account_class: str
    credit_account_class: str
    amount: Decimal
    currency: str
    economic_class: str
    flow_type: str
    pnl_treatment: str


@dataclass(frozen=True, slots=True)
class ExternalProfitAccountingDecision:
    schema: str
    decision_id: str
    evidence_id: str
    source: str
    settlement_asset: str
    action: AccountingAction
    recognized_external_pnl: Decimal
    external_cash_delta: Decimal
    instructions: tuple[AccountingInstruction, ...]
    reasons: tuple[str, ...]
    input_digest: str
    digest: str


class ExternalProfitBusAccountingV1:
    """Fail-closed Financial OS consumer for MetaPay/DEX External Profit Bus.

    Only `REALIZED_EXTERNAL_PNL` can create a realized-P&L accounting instruction.
    Capital movement, internal marks, quote-only opportunities and non-positive routes
    create no P&L posting. Issuance/proceeds without a completed accounting class stay
    pending for human/accounting policy classification.
    """

    SCHEMA = "financial-os.external-profit-accounting-decision/v1"
    REALIZED_SOURCES = {
        "METAPAY_CLASSIC_ARBITRAGE",
        "PAYMENT_ROUTING_SAVINGS",
        "TREASURY_FX",
        "DEX_ARBITRAGE",
        "HYBRID_CLASSIC_DEX_ARBITRAGE",
    }

    def decide(self, payload: ExternalProfitBusPayload) -> ExternalProfitAccountingDecision:
        self._validate_common(payload)
        input_digest = self.payload_digest(payload)
        reasons: list[str] = []

        if payload.internal_mint_quantity:
            reasons.append("internal mint quantity ignored for canonical accounting")
        if payload.internal_mark_delta:
            reasons.append("internal mark delta ignored for canonical accounting")

        if payload.classification == ExternalProfitClassification.REALIZED_EXTERNAL_PNL:
            self._validate_realized(payload)
            instruction = AccountingInstruction(
                debit_account_class="EXTERNAL_ASSET_CASH_OR_SETTLEMENT",
                credit_account_class="REALIZED_EXTERNAL_TRADING_OR_ROUTING_INCOME",
                amount=D(payload.canonical_external_pnl),
                currency=payload.settlement_asset,
                economic_class="REALIZED_EXTERNAL_ARBITRAGE_OR_ROUTING_PNL",
                flow_type="EXTERNAL_REVENUE",
                pnl_treatment="REALIZED_EXTERNAL_PNL",
            )
            reasons.append(
                "upstream external settlement P&L passed independent Financial OS guards"
            )
            return self._decision(
                payload,
                AccountingAction.POST_REALIZED_EXTERNAL_PNL,
                payload.canonical_external_pnl,
                (instruction,),
                reasons,
                input_digest,
            )

        if (
            payload.classification
            == ExternalProfitClassification.EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION
        ):
            if payload.canonical_external_pnl != 0:
                raise ValueError("unclassified external inflow cannot carry canonical P&L")
            reasons.append(
                "external cash may be real but revenue/equity/liability classification is unresolved"
            )
            return self._decision(
                payload,
                AccountingAction.REQUIRE_HUMAN_ACCOUNTING_CLASSIFICATION,
                D("0"),
                (),
                reasons,
                input_digest,
            )

        if payload.classification in {
            ExternalProfitClassification.CAPITAL_REALLOCATION_PNL_ZERO,
            ExternalProfitClassification.INTERNAL_MARK_NOT_EXTERNAL_VALUE,
            ExternalProfitClassification.NOT_REALIZED,
            ExternalProfitClassification.NON_POSITIVE_EXTERNAL_PNL,
        }:
            if payload.canonical_external_pnl != 0:
                raise ValueError("non-P&L classification cannot carry canonical P&L")
            reasons.append("classification explicitly forbids realized P&L recognition")
            return self._decision(
                payload,
                AccountingAction.NO_PNL_POSTING,
                D("0"),
                (),
                reasons,
                input_digest,
            )

        reasons.append("inadmissible upstream evidence")
        return self._decision(
            payload,
            AccountingAction.REJECT,
            D("0"),
            (),
            reasons,
            input_digest,
        )

    def _validate_common(self, payload: ExternalProfitBusPayload) -> None:
        if not payload.evidence_id.strip():
            raise ValueError("evidence id is required")
        if not payload.source.strip():
            raise ValueError("source is required")
        if not payload.settlement_asset.strip():
            raise ValueError("settlement asset is required")
        if payload.canonical_external_pnl < 0:
            raise ValueError("canonical external P&L cannot be negative in this admission path")
        if payload.internal_mint_quantity < 0:
            raise ValueError("internal mint quantity cannot be negative")

    def _validate_realized(self, payload: ExternalProfitBusPayload) -> None:
        if payload.source not in self.REALIZED_SOURCES:
            raise ValueError("source is not eligible for realized external P&L")
        if payload.canonical_external_pnl <= 0:
            raise ValueError("realized external P&L must be positive")
        if not payload.settlement_realized:
            raise ValueError("realized P&L requires external settlement")
        if not payload.independent_external_counterparty:
            raise ValueError("independent external counterparty evidence required")
        if not payload.flash_principal_repaid:
            raise ValueError("flash principal must be repaid")
        if not payload.provider_references:
            raise ValueError("provider/venue references are required")
        if not payload.route_digest:
            raise ValueError("route/evidence digest is required")
        if payload.external_cash_delta < payload.canonical_external_pnl:
            raise ValueError("recognized P&L cannot exceed external cash delta")

    def _decision(
        self,
        payload: ExternalProfitBusPayload,
        action: AccountingAction,
        recognized_pnl: Decimal,
        instructions: tuple[AccountingInstruction, ...],
        reasons: list[str],
        input_digest: str,
    ) -> ExternalProfitAccountingDecision:
        body: dict[str, Any] = {
            "schema": self.SCHEMA,
            "decision_id": f"external-profit:{payload.evidence_id}",
            "evidence_id": payload.evidence_id,
            "source": payload.source,
            "settlement_asset": payload.settlement_asset,
            "action": action.value,
            "recognized_external_pnl": str(recognized_pnl),
            "external_cash_delta": str(payload.external_cash_delta),
            "instructions": [self._instruction_json(item) for item in instructions],
            "reasons": reasons,
            "input_digest": input_digest,
        }
        digest = sha256(self._canonical_json(body)).hexdigest()
        return ExternalProfitAccountingDecision(
            schema=self.SCHEMA,
            decision_id=body["decision_id"],
            evidence_id=payload.evidence_id,
            source=payload.source,
            settlement_asset=payload.settlement_asset,
            action=action,
            recognized_external_pnl=D(recognized_pnl),
            external_cash_delta=D(payload.external_cash_delta),
            instructions=instructions,
            reasons=tuple(reasons),
            input_digest=input_digest,
            digest=digest,
        )

    @classmethod
    def payload_digest(cls, payload: ExternalProfitBusPayload) -> str:
        raw = asdict(payload)
        normalized = {key: cls._normalize(value) for key, value in raw.items()}
        return sha256(cls._canonical_json(normalized)).hexdigest()

    @staticmethod
    def _instruction_json(item: AccountingInstruction) -> dict[str, str]:
        return {
            "debit_account_class": item.debit_account_class,
            "credit_account_class": item.credit_account_class,
            "amount": str(item.amount),
            "currency": item.currency,
            "economic_class": item.economic_class,
            "flow_type": item.flow_type,
            "pnl_treatment": item.pnl_treatment,
        }

    @classmethod
    def _normalize(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, StrEnum):
            return value.value
        if isinstance(value, tuple):
            return [cls._normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._normalize(item) for key, item in value.items()}
        return value

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
