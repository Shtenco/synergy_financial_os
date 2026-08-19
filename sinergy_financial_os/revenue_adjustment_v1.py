from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import (
    AccountingCloseV2,
    LedgerInclusionProofV2,
    verify_ledger_inclusion_proof_v2,
)
from .accounting_period_chain_v1 import (
    AccountingPeriodChainProofV1,
    verify_accounting_period_chain_proof_v1,
)
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .ledger_event_v2 import ledger_event_v2_digest, verify_ledger_event_v2
from .numeric import canonical_decimal_text, finite_decimal
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2


SCHEMA = "revenue.adjustment-authorization/v1"
REASONS = frozenset({"REFUND", "CHARGEBACK"})
TAX_TREATMENTS = frozenset(
    {"NONE", "LIABILITY_RELEASE", "RECOVERABLE_RECEIVABLE", "NONRECOVERABLE_EXPENSE"}
)
AUTHORITIES = frozenset({"HUMAN_COMMITTEE", "MULTISIG_GOVERNANCE"})
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class RevenueAdjustmentV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RevenueAdjustmentV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise RevenueAdjustmentV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RevenueAdjustmentV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _amount(value: Any, field_name: str) -> Decimal:
    result = finite_decimal(value, field_name)
    if result < ZERO:
        raise RevenueAdjustmentV1Error(f"{field_name} must be non-negative")
    return result


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
class RevenueAdjustmentAuthorizationV1:
    authorization_id: str
    target_period_id: str
    project_id: str
    reason: str
    original_period_close_digest: str
    original_accounting_close_digest: str
    original_revenue_recognition_digest: str
    original_ledger_event_digest: str
    original_reporting_entry_digest: str
    period_chain_proof_digest: str
    customer_refund_amount: Decimal
    revenue_reduction_amount: Decimal
    refund_reserve_release_amount: Decimal
    tax_adjustment_amount: Decimal
    tax_treatment: str
    external_fee_expense_amount: Decimal
    external_refund_evidence_digest: str
    decision_evidence_digest: str
    accounting_policy_digest: str
    requirement_registry_digest: str
    decision_authority: str
    decided_at: datetime
    effective_at: datetime
    tax_evidence_digest: str | None = None
    fee_evidence_digest: str | None = None
    posting_authority: str = "SEPARATE_ADJUSTMENT_POSTING"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        reason = _text(self.reason, "reason").upper()
        tax_treatment = _text(self.tax_treatment, "tax_treatment").upper()
        authority = _text(self.decision_authority, "decision_authority").upper()
        if reason not in REASONS:
            raise RevenueAdjustmentV1Error(f"unsupported adjustment reason: {reason}")
        if tax_treatment not in TAX_TREATMENTS:
            raise RevenueAdjustmentV1Error(f"unsupported tax_treatment: {tax_treatment}")
        if authority not in AUTHORITIES:
            raise RevenueAdjustmentV1Error(
                "post-close revenue adjustment requires human committee or multisig authority"
            )
        if self.posting_authority != "SEPARATE_ADJUSTMENT_POSTING" or self.ai_authority != "NONE":
            raise RevenueAdjustmentV1Error(
                "adjustment authorization cannot post entries and AI cannot authorize"
            )

        customer = _amount(self.customer_refund_amount, "customer_refund_amount")
        revenue = _amount(self.revenue_reduction_amount, "revenue_reduction_amount")
        reserve = _amount(self.refund_reserve_release_amount, "refund_reserve_release_amount")
        tax = _amount(self.tax_adjustment_amount, "tax_adjustment_amount")
        fee = _amount(self.external_fee_expense_amount, "external_fee_expense_amount")
        if customer <= ZERO:
            raise RevenueAdjustmentV1Error("customer_refund_amount must be positive")
        if customer != revenue + reserve + tax:
            raise RevenueAdjustmentV1Error(
                "customer refund must equal revenue reduction + refund reserve release + tax adjustment"
            )
        if tax_treatment == "NONE":
            if tax != ZERO or self.tax_evidence_digest is not None:
                raise RevenueAdjustmentV1Error(
                    "tax_treatment NONE requires zero tax adjustment and no tax evidence"
                )
        else:
            if tax <= ZERO or self.tax_evidence_digest is None:
                raise RevenueAdjustmentV1Error(
                    "non-NONE tax treatment requires positive tax adjustment and tax evidence"
                )
        if fee > ZERO and self.fee_evidence_digest is None:
            raise RevenueAdjustmentV1Error(
                "external fee expense requires separate fee evidence"
            )
        if fee == ZERO and self.fee_evidence_digest is not None:
            raise RevenueAdjustmentV1Error(
                "fee evidence is not allowed when external_fee_expense_amount is zero"
            )

        decided = _utc(self.decided_at, "decided_at")
        effective = _utc(self.effective_at, "effective_at")
        if effective < decided:
            raise RevenueAdjustmentV1Error("effective_at cannot precede decision")

        for field_name in (
            "authorization_id",
            "target_period_id",
            "project_id",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        for field_name in (
            "original_period_close_digest",
            "original_accounting_close_digest",
            "original_revenue_recognition_digest",
            "original_ledger_event_digest",
            "original_reporting_entry_digest",
            "period_chain_proof_digest",
            "external_refund_evidence_digest",
            "decision_evidence_digest",
            "accounting_policy_digest",
            "requirement_registry_digest",
        ):
            object.__setattr__(self, field_name, _hex64(getattr(self, field_name), field_name))
        if self.tax_evidence_digest is not None:
            object.__setattr__(
                self,
                "tax_evidence_digest",
                _hex64(self.tax_evidence_digest, "tax_evidence_digest", nullable=True),
            )
        if self.fee_evidence_digest is not None:
            object.__setattr__(
                self,
                "fee_evidence_digest",
                _hex64(self.fee_evidence_digest, "fee_evidence_digest", nullable=True),
            )
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "tax_treatment", tax_treatment)
        object.__setattr__(self, "decision_authority", authority)
        object.__setattr__(self, "customer_refund_amount", customer)
        object.__setattr__(self, "revenue_reduction_amount", revenue)
        object.__setattr__(self, "refund_reserve_release_amount", reserve)
        object.__setattr__(self, "tax_adjustment_amount", tax)
        object.__setattr__(self, "external_fee_expense_amount", fee)
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "effective_at", effective)

    @property
    def total_cash_outflow_amount(self) -> Decimal:
        return self.customer_refund_amount + self.external_fee_expense_amount

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "authorization_id": self.authorization_id,
            "target_period_id": self.target_period_id,
            "project_id": self.project_id,
            "reason": self.reason,
            "original_period_close_digest": self.original_period_close_digest,
            "original_accounting_close_digest": self.original_accounting_close_digest,
            "original_revenue_recognition_digest": self.original_revenue_recognition_digest,
            "original_ledger_event_digest": self.original_ledger_event_digest,
            "original_reporting_entry_digest": self.original_reporting_entry_digest,
            "period_chain_proof_digest": self.period_chain_proof_digest,
            "customer_refund_amount": canonical_decimal_text(self.customer_refund_amount),
            "revenue_reduction_amount": canonical_decimal_text(self.revenue_reduction_amount),
            "refund_reserve_release_amount": canonical_decimal_text(self.refund_reserve_release_amount),
            "tax_adjustment_amount": canonical_decimal_text(self.tax_adjustment_amount),
            "tax_treatment": self.tax_treatment,
            "external_fee_expense_amount": canonical_decimal_text(self.external_fee_expense_amount),
            "total_cash_outflow_amount": canonical_decimal_text(self.total_cash_outflow_amount),
            "external_refund_evidence_digest": self.external_refund_evidence_digest,
            "tax_evidence_digest": self.tax_evidence_digest,
            "fee_evidence_digest": self.fee_evidence_digest,
            "decision_evidence_digest": self.decision_evidence_digest,
            "accounting_policy_digest": self.accounting_policy_digest,
            "requirement_registry_digest": self.requirement_registry_digest,
            "decision_authority": self.decision_authority,
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "effective_at": self.effective_at.isoformat().replace("+00:00", "Z"),
            "posting_authority": self.posting_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def verify_revenue_adjustment_context_v1(
    authorization: RevenueAdjustmentAuthorizationV1,
    target_period: AccountingPeriodV1,
    period_chain_proof: AccountingPeriodChainProofV1,
    period_close_chain: Sequence[AccountingPeriodCloseV1],
    original_accounting_close: AccountingCloseV2,
    original_recognition: RevenueRecognitionDecisionV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
) -> bool:
    if authorization.target_period_id != target_period.period_id:
        raise RevenueAdjustmentV1Error("adjustment target period mismatch")
    if authorization.period_chain_proof_digest != period_chain_proof.digest:
        raise RevenueAdjustmentV1Error("period-chain proof digest mismatch")
    verify_accounting_period_chain_proof_v1(
        period_chain_proof,
        period_close_chain,
        target_period,
    )
    if period_chain_proof.generated_at > authorization.decided_at:
        raise RevenueAdjustmentV1Error(
            "authorization cannot rely on a period-chain proof generated after the decision"
        )
    if not period_close_chain:
        raise RevenueAdjustmentV1Error("period close chain cannot be empty")
    original_period_close = period_close_chain[0]
    if authorization.original_period_close_digest != original_period_close.digest:
        raise RevenueAdjustmentV1Error("authorization original PeriodClose mismatch")
    if original_period_close.accounting_close_digest != original_accounting_close.digest:
        raise RevenueAdjustmentV1Error("original PeriodClose/AccountingClose mismatch")
    if authorization.original_accounting_close_digest != original_accounting_close.digest:
        raise RevenueAdjustmentV1Error("authorization original AccountingClose mismatch")
    if authorization.decided_at <= original_period_close.closed_at:
        raise RevenueAdjustmentV1Error(
            "post-close adjustment must be authorized after original period close"
        )
    if not target_period.contains(authorization.effective_at):
        raise RevenueAdjustmentV1Error("adjustment effective_at must lie in target period")
    if authorization.accounting_policy_digest != target_period.accounting_policy_digest:
        raise RevenueAdjustmentV1Error("target-period accounting policy mismatch")
    if authorization.requirement_registry_digest != target_period.requirement_registry_digest:
        raise RevenueAdjustmentV1Error("target-period requirement registry mismatch")

    if original_recognition.decision != "RECOGNIZED" or not original_recognition.ledger_posting_allowed:
        raise RevenueAdjustmentV1Error("only recognized revenue can be adjusted")
    if authorization.project_id != original_recognition.project_id:
        raise RevenueAdjustmentV1Error("project mismatch")
    if authorization.original_revenue_recognition_digest != original_recognition.digest:
        raise RevenueAdjustmentV1Error("recognition digest mismatch")

    event = verify_ledger_event_v2(original_ledger_event)
    if event.get("event_type") != "EXTERNAL_REVENUE":
        raise RevenueAdjustmentV1Error("original event must be EXTERNAL_REVENUE")
    if event.get("evidence_digest") != original_recognition.digest:
        raise RevenueAdjustmentV1Error("original event evidence does not bind recognition")
    if authorization.original_ledger_event_digest != ledger_event_v2_digest(event):
        raise RevenueAdjustmentV1Error("original LedgerEvent digest mismatch")
    if authorization.original_reporting_entry_digest != event.get("reporting_entry_digest"):
        raise RevenueAdjustmentV1Error("original ReportingEntry digest mismatch")
    verify_ledger_inclusion_proof_v2(
        event,
        original_inclusion_proof,
        original_accounting_close,
    )
    return True
