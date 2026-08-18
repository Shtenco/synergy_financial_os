from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .capital_authorization_v2 import CapitalAuthorizationV2
from .core import AccountingInvariantError


SCHEMA = "settlement.receipt/v2"
HEX64 = re.compile(r"^[a-f0-9]{64}$")
DECIMAL = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
TOP_FIELDS = frozenset(
    {
        "schema", "settlement_id", "intent_id", "payer_id", "payee_id", "providers",
        "source_asset", "source_amount", "target_asset", "target_amount", "fees", "status",
        "finality_time", "external_evidence_classes", "external_references",
        "settlement_evidence_digest", "reconciled", "route_id", "causal_binding", "authority",
        "settlement_authority", "accounting_authority", "profit_recognition",
        "execution_authority", "receipt_digest",
    }
)
CAUSAL_FIELDS = frozenset(
    {
        "flow_kind", "project_id", "payment_purpose", "intent_idempotency_key",
        "intent_binding_digest", "capital_authorization_schema", "capital_authorization_digest",
        "project_evidence_schema", "project_evidence_digest",
    }
)
FEE_FIELDS = frozenset({"asset", "amount", "kind", "economic_role", "provider_ref"})
FEE_ROLES = frozenset({"PROTOCOL_REVENUE", "PROVIDER_COST", "NETWORK_COST", "TAX", "OTHER"})
FLOW_PURPOSES = {
    "PRODUCTIVE_CAPITAL_FUNDING": "productive_capital_funding",
    "PROJECT_REVENUE": "productive_project_revenue",
}


class SettlementReceiptV2ConsumerError(AccountingInvariantError):
    """Raised when external settlement evidence is ambiguous or internally inconsistent."""


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise SettlementReceiptV2ConsumerError(f"{field_name} must be a hexadecimal digest")
    result = value.lower().strip()
    if not HEX64.fullmatch(result):
        raise SettlementReceiptV2ConsumerError(f"{field_name} must be a 64-character hex digest")
    return result


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettlementReceiptV2ConsumerError(f"{field_name} is required")
    return value.strip()


def _decimal(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        raise SettlementReceiptV2ConsumerError(
            f"{field_name} must be a canonical non-negative decimal string"
        )
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SettlementReceiptV2ConsumerError(f"{field_name} is invalid") from exc
    if not result.is_finite() or result < 0:
        raise SettlementReceiptV2ConsumerError(f"{field_name} must be finite and non-negative")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify_settlement_receipt_v2_integrity(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SettlementReceiptV2ConsumerError("settlement receipt must be an object")
    receipt = dict(payload)
    if set(receipt) != TOP_FIELDS:
        missing = sorted(TOP_FIELDS - set(receipt))
        unknown = sorted(set(receipt) - TOP_FIELDS)
        raise SettlementReceiptV2ConsumerError(
            f"settlement receipt shape mismatch: missing={missing} unknown={unknown}"
        )
    if receipt["schema"] != SCHEMA:
        raise SettlementReceiptV2ConsumerError("unsupported settlement receipt schema")

    supplied_digest = _hex64(receipt["receipt_digest"], "receipt_digest")
    digest_payload = dict(receipt)
    digest_payload.pop("receipt_digest")
    expected_digest = _canonical_digest(digest_payload)
    if supplied_digest != expected_digest:
        raise SettlementReceiptV2ConsumerError(
            f"receipt digest mismatch: expected={expected_digest} got={supplied_digest}"
        )

    for field_name in ("settlement_id", "intent_id", "payer_id", "payee_id"):
        _text(receipt[field_name], field_name)
    source_asset = _text(receipt["source_asset"], "source_asset")
    target_asset = _text(receipt["target_asset"], "target_asset")
    if source_asset != source_asset.upper() or target_asset != target_asset.upper():
        raise SettlementReceiptV2ConsumerError("asset symbols must be canonical uppercase")
    _decimal(receipt["source_amount"], "source_amount")
    if receipt["target_amount"] is not None:
        _decimal(receipt["target_amount"], "target_amount")

    if not isinstance(receipt["providers"], list) or len(receipt["providers"]) != len(set(receipt["providers"])):
        raise SettlementReceiptV2ConsumerError("providers must be a unique array")
    if not isinstance(receipt["external_references"], list) or len(receipt["external_references"]) != len(set(receipt["external_references"])):
        raise SettlementReceiptV2ConsumerError("external_references must be a unique array")
    _hex64(receipt["settlement_evidence_digest"], "settlement_evidence_digest")

    if receipt["authority"] != "SETTLEMENT_EVIDENCE_ONLY":
        raise SettlementReceiptV2ConsumerError("receipt cannot claim accounting authority")
    if receipt["settlement_authority"] != "Shtenco/synergy_pay_system":
        raise SettlementReceiptV2ConsumerError("unexpected settlement authority")
    if receipt["accounting_authority"] != "Shtenco/synergy_financial_os":
        raise SettlementReceiptV2ConsumerError("unexpected accounting authority")
    if receipt["profit_recognition"] != "NOT_PERFORMED":
        raise SettlementReceiptV2ConsumerError("settlement receipt cannot recognize profit")
    if receipt["execution_authority"] != "NONE":
        raise SettlementReceiptV2ConsumerError("observed receipt cannot embed execution authority")

    if receipt["status"] != "SETTLED" or receipt["reconciled"] is not True:
        raise SettlementReceiptV2ConsumerError(
            "canonical economic-cycle receipt must be SETTLED and reconciled"
        )
    finality = receipt["finality_time"]
    if not isinstance(finality, str) or not finality.endswith("Z"):
        raise SettlementReceiptV2ConsumerError("SETTLED receipt requires canonical UTC finality_time")

    fees = receipt["fees"]
    if not isinstance(fees, list):
        raise SettlementReceiptV2ConsumerError("fees must be an array")
    for fee in fees:
        if not isinstance(fee, Mapping) or set(fee) != FEE_FIELDS:
            raise SettlementReceiptV2ConsumerError("fee component shape mismatch")
        asset = _text(fee["asset"], "fee.asset")
        if asset != asset.upper():
            raise SettlementReceiptV2ConsumerError("fee asset must be uppercase")
        _decimal(fee["amount"], "fee.amount")
        _text(fee["kind"], "fee.kind")
        if fee["economic_role"] not in FEE_ROLES:
            raise SettlementReceiptV2ConsumerError("unsupported fee economic role")
        if fee["provider_ref"] is not None:
            _text(fee["provider_ref"], "fee.provider_ref")

    causal = receipt["causal_binding"]
    if not isinstance(causal, Mapping) or set(causal) != CAUSAL_FIELDS:
        raise SettlementReceiptV2ConsumerError("causal_binding shape mismatch")
    flow_kind = causal["flow_kind"]
    if flow_kind not in FLOW_PURPOSES:
        raise SettlementReceiptV2ConsumerError("unsupported causal flow kind")
    if causal["payment_purpose"] != FLOW_PURPOSES[flow_kind]:
        raise SettlementReceiptV2ConsumerError("causal payment purpose mismatch")
    _text(causal["project_id"], "causal.project_id")
    _text(causal["intent_idempotency_key"], "causal.intent_idempotency_key")
    _hex64(causal["intent_binding_digest"], "causal.intent_binding_digest")
    if causal["capital_authorization_schema"] != "capital.authorization/v2":
        raise SettlementReceiptV2ConsumerError("receipt must bind CapitalAuthorization v2")
    _hex64(causal["capital_authorization_digest"], "causal.capital_authorization_digest")
    if flow_kind == "PRODUCTIVE_CAPITAL_FUNDING":
        if causal["project_evidence_schema"] is not None or causal["project_evidence_digest"] is not None:
            raise SettlementReceiptV2ConsumerError("funding receipt cannot bind future project evidence")
    else:
        if causal["project_evidence_schema"] != "project.evidence/v1":
            raise SettlementReceiptV2ConsumerError("revenue receipt requires ProjectEvidence v1")
        _hex64(causal["project_evidence_digest"], "causal.project_evidence_digest")
        if _decimal(receipt["source_amount"], "source_amount") <= 0:
            raise SettlementReceiptV2ConsumerError("project revenue settlement must have positive amount")
    return receipt


@dataclass(frozen=True)
class SettlementCausalReview:
    status: str
    blockers: tuple[str, ...]
    receipt_digest: str | None
    profit_recognition: str = "NOT_PERFORMED"
    accounting_entry_allowed: bool = False

    @property
    def accepted_as_causal_evidence(self) -> bool:
        return self.status == "CAUSAL_EVIDENCE_ACCEPTED"


def verify_funding_receipt_against_authorization_v2(
    receipt_payload: Mapping[str, Any],
    authorization: CapitalAuthorizationV2,
) -> SettlementCausalReview:
    try:
        receipt = verify_settlement_receipt_v2_integrity(receipt_payload)
    except SettlementReceiptV2ConsumerError as exc:
        return SettlementCausalReview(
            status="CAUSAL_EVIDENCE_BLOCKED",
            blockers=(f"RECEIPT_INVALID:{exc}",),
            receipt_digest=None,
        )

    blockers: set[str] = set()
    causal = receipt["causal_binding"]
    if causal["flow_kind"] != "PRODUCTIVE_CAPITAL_FUNDING":
        blockers.add("NOT_FUNDING_RECEIPT")
    if authorization.decision != "APPROVED":
        blockers.add("AUTHORIZATION_NOT_APPROVED")
    if causal["project_id"] != authorization.project_id:
        blockers.add("PROJECT_ID_MISMATCH")
    if causal["capital_authorization_digest"] != authorization.digest:
        blockers.add("AUTHORIZATION_DIGEST_MISMATCH")
    if receipt["payer_id"] != authorization.funding_source_id:
        blockers.add("FUNDING_SOURCE_MISMATCH")
    if receipt["payee_id"] != authorization.funding_destination_id:
        blockers.add("FUNDING_DESTINATION_MISMATCH")
    if receipt["source_asset"] != authorization.funding_asset:
        blockers.add("FUNDING_ASSET_MISMATCH")
    if receipt["source_amount"] != _decimal_text(authorization.approved_amount):
        blockers.add("FUNDING_AMOUNT_MISMATCH")
    if causal["intent_idempotency_key"] != authorization.payment_idempotency_key:
        blockers.add("PAYMENT_IDEMPOTENCY_KEY_MISMATCH")
    if causal["payment_purpose"] != authorization.payment_purpose:
        blockers.add("PAYMENT_PURPOSE_MISMATCH")

    return SettlementCausalReview(
        status="CAUSAL_EVIDENCE_BLOCKED" if blockers else "CAUSAL_EVIDENCE_ACCEPTED",
        blockers=tuple(sorted(blockers)),
        receipt_digest=receipt["receipt_digest"],
        profit_recognition="NOT_PERFORMED",
        accounting_entry_allowed=False,
    )


def verify_revenue_receipt_lineage_v2(
    receipt_payload: Mapping[str, Any],
    authorization: CapitalAuthorizationV2,
    *,
    expected_project_evidence_digest: str,
) -> SettlementCausalReview:
    """Verify project/funding lineage only; external revenue recognition is a later gate."""

    try:
        receipt = verify_settlement_receipt_v2_integrity(receipt_payload)
        expected_evidence = _hex64(
            expected_project_evidence_digest, "expected_project_evidence_digest"
        )
    except SettlementReceiptV2ConsumerError as exc:
        return SettlementCausalReview(
            status="CAUSAL_EVIDENCE_BLOCKED",
            blockers=(f"RECEIPT_INVALID:{exc}",),
            receipt_digest=None,
        )

    blockers: set[str] = set()
    causal = receipt["causal_binding"]
    if causal["flow_kind"] != "PROJECT_REVENUE":
        blockers.add("NOT_PROJECT_REVENUE_RECEIPT")
    if causal["project_id"] != authorization.project_id:
        blockers.add("PROJECT_ID_MISMATCH")
    if causal["capital_authorization_digest"] != authorization.digest:
        blockers.add("AUTHORIZATION_DIGEST_MISMATCH")
    if causal["project_evidence_digest"] != expected_evidence:
        blockers.add("PROJECT_EVIDENCE_DIGEST_MISMATCH")

    return SettlementCausalReview(
        status="CAUSAL_EVIDENCE_BLOCKED" if blockers else "CAUSAL_EVIDENCE_ACCEPTED",
        blockers=tuple(sorted(blockers)),
        receipt_digest=receipt["receipt_digest"],
        profit_recognition="NOT_PERFORMED",
        accounting_entry_allowed=False,
    )
