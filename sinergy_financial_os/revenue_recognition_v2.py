from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .capital_authorization_v2 import CapitalAuthorizationV2
from .core import AccountingInvariantError
from .settlement_receipt_v2 import (
    SettlementReceiptV2ConsumerError,
    verify_revenue_receipt_lineage_v2,
    verify_settlement_receipt_v2_integrity,
)

SCHEMA = "revenue.recognition/v2"
ZERO = Decimal("0")
ONE = Decimal("1")
HEX = frozenset("0123456789abcdef")
COUNTERPARTY_RELATIONS = frozenset({"EXTERNAL_NON_RELATED", "EXTERNAL_RELATED", "INTRA_GROUP", "UNKNOWN"})
PERFORMANCE_STATES = frozenset({"SATISFIED", "PARTIAL", "UNSATISFIED"})
DISPUTE_STATES = frozenset({"CLEAR", "OPEN", "CHARGEBACK_PENDING", "REFUNDED"})
DECISIONS = frozenset({"RECOGNIZED", "DEFERRED", "REJECTED"})

class RevenueRecognitionV2Error(AccountingInvariantError):
    pass

def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RevenueRecognitionV2Error(f"{field_name} is required")
    return value.strip()

def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise RevenueRecognitionV2Error(f"{field_name} must be a 64-character hex digest")
    return result

def _decimal(value: Decimal | int | str, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise RevenueRecognitionV2Error(f"{field_name} must be a finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RevenueRecognitionV2Error(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite() or result < ZERO:
        raise RevenueRecognitionV2Error(f"{field_name} must be finite and non-negative")
    return result

def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text

def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RevenueRecognitionV2Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)

def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class RevenueRecognitionRequestV2:
    recognition_id: str
    project_id: str
    project_evidence_digest: str
    counterparty_id: str
    counterparty_relation: str
    counterparty_evidence_digest: str
    revenue_destination_id: str
    contract_digest: str
    invoice_digest: str
    invoice_reporting_amount: Decimal
    delivery_evidence_digest: str
    performance_state: str
    dispute_state: str
    reporting_currency: str
    fx_rate_to_reporting: Decimal
    tax_reporting_amount: Decimal
    refund_reserve_reporting_amount: Decimal
    accounting_policy_digest: str
    recognized_at: datetime
    fx_evidence_digest: str | None = None
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        relation = _text(self.counterparty_relation, "counterparty_relation").upper()
        performance = _text(self.performance_state, "performance_state").upper()
        dispute = _text(self.dispute_state, "dispute_state").upper()
        if relation not in COUNTERPARTY_RELATIONS:
            raise RevenueRecognitionV2Error(f"unsupported counterparty_relation: {relation}")
        if performance not in PERFORMANCE_STATES:
            raise RevenueRecognitionV2Error(f"unsupported performance_state: {performance}")
        if dispute not in DISPUTE_STATES:
            raise RevenueRecognitionV2Error(f"unsupported dispute_state: {dispute}")
        if self.ai_authority != "NONE":
            raise RevenueRecognitionV2Error("AI cannot be revenue recognition authority")
        fx_rate = _decimal(self.fx_rate_to_reporting, "fx_rate_to_reporting")
        invoice_amount = _decimal(self.invoice_reporting_amount, "invoice_reporting_amount")
        if fx_rate <= ZERO or invoice_amount <= ZERO:
            raise RevenueRecognitionV2Error("fx rate and invoice amount must be positive")
        object.__setattr__(self, "recognition_id", _text(self.recognition_id, "recognition_id"))
        object.__setattr__(self, "project_id", _text(self.project_id, "project_id"))
        object.__setattr__(self, "counterparty_id", _text(self.counterparty_id, "counterparty_id"))
        object.__setattr__(self, "revenue_destination_id", _text(self.revenue_destination_id, "revenue_destination_id"))
        object.__setattr__(self, "counterparty_relation", relation)
        object.__setattr__(self, "performance_state", performance)
        object.__setattr__(self, "dispute_state", dispute)
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        object.__setattr__(self, "invoice_reporting_amount", invoice_amount)
        object.__setattr__(self, "fx_rate_to_reporting", fx_rate)
        object.__setattr__(self, "tax_reporting_amount", _decimal(self.tax_reporting_amount, "tax_reporting_amount"))
        object.__setattr__(self, "refund_reserve_reporting_amount", _decimal(self.refund_reserve_reporting_amount, "refund_reserve_reporting_amount"))
        object.__setattr__(self, "recognized_at", _utc(self.recognized_at, "recognized_at"))
        for field_name in ("project_evidence_digest", "counterparty_evidence_digest", "contract_digest", "invoice_digest", "delivery_evidence_digest", "accounting_policy_digest"):
            object.__setattr__(self, field_name, _hex64(getattr(self, field_name), field_name))
        if self.fx_evidence_digest is not None:
            object.__setattr__(self, "fx_evidence_digest", _hex64(self.fx_evidence_digest, "fx_evidence_digest", nullable=True))

@dataclass(frozen=True)
class RevenueRecognitionDecisionV2:
    recognition_id: str
    project_id: str
    decision: str
    settlement_receipt_digest: str
    capital_authorization_digest: str
    project_evidence_digest: str
    counterparty_id: str
    counterparty_relation: str
    counterparty_evidence_digest: str
    revenue_destination_id: str
    contract_digest: str
    invoice_digest: str
    invoice_reporting_amount: Decimal
    delivery_evidence_digest: str
    accounting_policy_digest: str
    settlement_asset: str
    settlement_amount: Decimal
    reporting_currency: str
    fx_rate_to_reporting: Decimal
    gross_reporting_amount: Decimal
    tax_reporting_amount: Decimal
    refund_reserve_reporting_amount: Decimal
    recognized_reporting_amount: Decimal
    performance_state: str
    dispute_state: str
    recognized_at: datetime
    blockers: tuple[str, ...]
    fx_evidence_digest: str | None = None
    accounting_authority: str = "Shtenco/synergy_financial_os"
    ledger_posting_authority: str = "SEPARATE_REPORTING_LEDGER_POST"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise RevenueRecognitionV2Error("unsupported recognition decision")
        if self.accounting_authority != "Shtenco/synergy_financial_os":
            raise RevenueRecognitionV2Error("Financial OS must remain accounting authority")
        if self.ledger_posting_authority != "SEPARATE_REPORTING_LEDGER_POST":
            raise RevenueRecognitionV2Error("recognition decision cannot post ledger itself")
        if self.ai_authority != "NONE":
            raise RevenueRecognitionV2Error("AI cannot recognize revenue")
        if self.decision == "RECOGNIZED" and self.blockers:
            raise RevenueRecognitionV2Error("RECOGNIZED cannot contain blockers")
        if self.decision != "RECOGNIZED" and (not self.blockers or self.recognized_reporting_amount != ZERO):
            raise RevenueRecognitionV2Error("deferred/rejected decision requires blockers and zero recognized amount")

    @property
    def ledger_posting_allowed(self) -> bool:
        return self.decision == "RECOGNIZED"

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA,
            "recognition_id": self.recognition_id,
            "project_id": self.project_id,
            "decision": self.decision,
            "settlement_receipt_digest": self.settlement_receipt_digest,
            "capital_authorization_digest": self.capital_authorization_digest,
            "project_evidence_digest": self.project_evidence_digest,
            "counterparty_id": self.counterparty_id,
            "counterparty_relation": self.counterparty_relation,
            "counterparty_evidence_digest": self.counterparty_evidence_digest,
            "revenue_destination_id": self.revenue_destination_id,
            "contract_digest": self.contract_digest,
            "invoice_digest": self.invoice_digest,
            "invoice_reporting_amount": _decimal_text(self.invoice_reporting_amount),
            "delivery_evidence_digest": self.delivery_evidence_digest,
            "accounting_policy_digest": self.accounting_policy_digest,
            "settlement_asset": self.settlement_asset,
            "settlement_amount": _decimal_text(self.settlement_amount),
            "reporting_currency": self.reporting_currency,
            "fx_rate_to_reporting": _decimal_text(self.fx_rate_to_reporting),
            "gross_reporting_amount": _decimal_text(self.gross_reporting_amount),
            "tax_reporting_amount": _decimal_text(self.tax_reporting_amount),
            "refund_reserve_reporting_amount": _decimal_text(self.refund_reserve_reporting_amount),
            "recognized_reporting_amount": _decimal_text(self.recognized_reporting_amount),
            "performance_state": self.performance_state,
            "dispute_state": self.dispute_state,
            "fx_evidence_digest": self.fx_evidence_digest,
            "recognized_at": self.recognized_at.isoformat().replace("+00:00", "Z"),
            "blockers": list(self.blockers),
            "ledger_posting_allowed": self.ledger_posting_allowed,
            "accounting_authority": self.accounting_authority,
            "ledger_posting_authority": self.ledger_posting_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

def evaluate_revenue_recognition_v2(receipt_payload: Mapping[str, Any], authorization: CapitalAuthorizationV2, request: RevenueRecognitionRequestV2) -> RevenueRecognitionDecisionV2:
    hard: set[str] = set()
    defer: set[str] = set()
    try:
        receipt = verify_settlement_receipt_v2_integrity(receipt_payload)
    except SettlementReceiptV2ConsumerError as exc:
        raise RevenueRecognitionV2Error(f"invalid settlement receipt: {exc}") from exc
    lineage = verify_revenue_receipt_lineage_v2(receipt, authorization, expected_project_evidence_digest=request.project_evidence_digest)
    if not lineage.accepted_as_causal_evidence:
        hard.update(lineage.blockers)
    causal = receipt["causal_binding"]
    if causal["flow_kind"] != "PROJECT_REVENUE": hard.add("NOT_PROJECT_REVENUE_RECEIPT")
    if request.project_id != authorization.project_id or request.project_id != causal["project_id"]: hard.add("PROJECT_ID_MISMATCH")
    if causal["capital_authorization_digest"] != authorization.digest: hard.add("AUTHORIZATION_DIGEST_MISMATCH")
    if causal["project_evidence_digest"] != request.project_evidence_digest: hard.add("PROJECT_EVIDENCE_DIGEST_MISMATCH")
    if receipt["payer_id"] != request.counterparty_id: hard.add("COUNTERPARTY_PAYER_MISMATCH")
    if receipt["payee_id"] != request.revenue_destination_id: hard.add("REVENUE_DESTINATION_MISMATCH")
    if request.counterparty_relation == "INTRA_GROUP": hard.add("INTRA_GROUP_NOT_EXTERNAL_REVENUE")
    elif request.counterparty_relation in {"UNKNOWN", "EXTERNAL_RELATED"}: defer.add("COUNTERPARTY_EXTERNALITY_REQUIRES_REVIEW")
    if request.performance_state != "SATISFIED": defer.add("PERFORMANCE_OBLIGATION_NOT_SATISFIED")
    if request.dispute_state in {"OPEN", "CHARGEBACK_PENDING"}: defer.add("PAYMENT_DISPUTE_OR_CHARGEBACK_OPEN")
    elif request.dispute_state == "REFUNDED": hard.add("PAYMENT_ALREADY_REFUNDED")
    target_raw = receipt.get("target_amount")
    if target_raw is None:
        hard.add("MISSING_FINAL_SETTLED_AMOUNT"); settlement_amount = ZERO
    else:
        settlement_amount = _decimal(target_raw, "receipt.target_amount")
    settlement_asset = _text(receipt["target_asset"], "receipt.target_asset").upper()
    if settlement_asset == request.reporting_currency:
        if request.fx_rate_to_reporting != ONE: hard.add("SAME_CURRENCY_FX_RATE_MUST_EQUAL_ONE")
        if request.fx_evidence_digest is not None: defer.add("UNNECESSARY_FX_EVIDENCE_REQUIRES_REVIEW")
    elif request.fx_evidence_digest is None:
        defer.add("MISSING_EXTERNAL_FX_EVIDENCE")
    gross = settlement_amount * request.fx_rate_to_reporting
    if gross > request.invoice_reporting_amount: hard.add("SETTLEMENT_EXCEEDS_INVOICE_AMOUNT")
    deductions = request.tax_reporting_amount + request.refund_reserve_reporting_amount
    if deductions > gross: hard.add("DEDUCTIONS_EXCEED_GROSS_SETTLEMENT")
    if hard:
        decision, blockers, recognized = "REJECTED", tuple(sorted(hard | defer)), ZERO
    elif defer:
        decision, blockers, recognized = "DEFERRED", tuple(sorted(defer)), ZERO
    else:
        recognized = gross - deductions
        if recognized <= ZERO:
            decision, blockers, recognized = "DEFERRED", ("NO_POSITIVE_RECOGNIZABLE_AMOUNT",), ZERO
        else:
            decision, blockers = "RECOGNIZED", ()
    return RevenueRecognitionDecisionV2(
        recognition_id=request.recognition_id, project_id=request.project_id, decision=decision,
        settlement_receipt_digest=receipt["receipt_digest"], capital_authorization_digest=authorization.digest,
        project_evidence_digest=request.project_evidence_digest, counterparty_id=request.counterparty_id,
        counterparty_relation=request.counterparty_relation, counterparty_evidence_digest=request.counterparty_evidence_digest,
        revenue_destination_id=request.revenue_destination_id, contract_digest=request.contract_digest,
        invoice_digest=request.invoice_digest, invoice_reporting_amount=request.invoice_reporting_amount,
        delivery_evidence_digest=request.delivery_evidence_digest, accounting_policy_digest=request.accounting_policy_digest,
        settlement_asset=settlement_asset, settlement_amount=settlement_amount, reporting_currency=request.reporting_currency,
        fx_rate_to_reporting=request.fx_rate_to_reporting, gross_reporting_amount=gross,
        tax_reporting_amount=request.tax_reporting_amount, refund_reserve_reporting_amount=request.refund_reserve_reporting_amount,
        recognized_reporting_amount=recognized, performance_state=request.performance_state, dispute_state=request.dispute_state,
        fx_evidence_digest=request.fx_evidence_digest, recognized_at=request.recognized_at, blockers=blockers,
    )
