from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2, LedgerInclusionProofV2
from .accounting_period_chain_v1 import AccountingPeriodChainProofV1
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal
from .prior_period_correction_v1 import (
    PriorPeriodCorrectionAuthorizationV1,
    verify_prior_period_correction_context_v1,
)
from .reporting import FlowType, ReportingLedger, ReportingLine


ZERO = Decimal("0")
BLOCKING_DOWNSTREAM_CLASSES = frozenset(
    {"REVENUE_REVERSAL", "REVENUE_POST_CLOSE_ADJUSTMENT", "PRIOR_PERIOD_ENTRY_VOID"}
)


class AuthorizedPriorPeriodCorrectionV1Error(AccountingInvariantError):
    pass


def _assert_no_downstream_consumption(
    ledger: ReportingLedger,
    original_reporting_entry_digest: str,
) -> None:
    for entry in ledger.entries_since(0):
        if entry.metadata.get("original_reporting_entry_digest") != original_reporting_entry_digest:
            continue
        economic_class = entry.metadata.get("economic_class")
        if economic_class in BLOCKING_DOWNSTREAM_CLASSES:
            raise AuthorizedPriorPeriodCorrectionV1Error(
                f"exact-entry void unavailable after downstream {economic_class}"
            )


def _opposite_lines_and_preflight(
    ledger: ReportingLedger,
    original_ledger_event: Mapping[str, Any],
) -> tuple[ReportingLine, ...]:
    if original_ledger_event.get("reporting_currency") != ledger.reporting_currency:
        raise AuthorizedPriorPeriodCorrectionV1Error("original event reporting currency mismatch")
    result: list[ReportingLine] = []
    for index, raw in enumerate(original_ledger_event["lines"]):
        account_id = raw.get("account")
        if not isinstance(account_id, str) or not account_id.strip():
            raise AuthorizedPriorPeriodCorrectionV1Error(f"original line {index} account is invalid")
        account_id = account_id.strip()
        spec = ledger.account(account_id)
        debit = finite_decimal(raw.get("debit"), f"original line {index}.debit")
        credit = finite_decimal(raw.get("credit"), f"original line {index}.credit")
        if debit > ZERO and credit == ZERO:
            # Original debit becomes correction credit. For debit-normal accounts
            # this reduces the current balance and therefore must be available.
            if spec.normal_side == "DEBIT" and ledger.balance(account_id) < debit:
                raise AuthorizedPriorPeriodCorrectionV1Error(
                    f"cannot void original debit: current {account_id} balance is below {debit}"
                )
            result.append(ReportingLine(account_id, credit=debit))
        elif credit > ZERO and debit == ZERO:
            # Original credit becomes correction debit. For credit-normal accounts
            # this reduces the current balance and therefore must be available.
            if spec.normal_side == "CREDIT" and ledger.balance(account_id) < credit:
                raise AuthorizedPriorPeriodCorrectionV1Error(
                    f"cannot void original credit: current {account_id} balance is below {credit}"
                )
            result.append(ReportingLine(account_id, debit=credit))
        else:
            raise AuthorizedPriorPeriodCorrectionV1Error(
                "original ledger event line is not a canonical one-sided posting"
            )
    return tuple(result)


def post_authorized_prior_period_entry_void_v1(
    ledger: ReportingLedger,
    authorization: PriorPeriodCorrectionAuthorizationV1,
    target_period: AccountingPeriodV1,
    period_chain_proof: AccountingPeriodChainProofV1,
    period_close_chain: Sequence[AccountingPeriodCloseV1],
    original_accounting_close: AccountingCloseV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
    *,
    event_id: str,
):
    """Post one exact opposite entry for a proven prior-period accounting error.

    This is not an external refund and therefore uses FlowType.INTERNAL. The
    correction changes current ledger balances/NAV but is deliberately excluded
    from current-period realized P&L. Historical presentation is handled by a
    separate restatement-view layer; no old PeriodClose or original entry is
    mutated.
    """

    verify_prior_period_correction_context_v1(
        authorization,
        target_period,
        period_chain_proof,
        period_close_chain,
        original_accounting_close,
        original_ledger_event,
        original_inclusion_proof,
    )
    _assert_no_downstream_consumption(
        ledger,
        authorization.original_reporting_entry_digest,
    )
    lines = _opposite_lines_and_preflight(ledger, original_ledger_event)
    if sum((line.debit for line in lines), ZERO) != sum(
        (line.credit for line in lines), ZERO
    ):
        raise AuthorizedPriorPeriodCorrectionV1Error(
            "exact-entry void must remain balanced"
        )

    metadata = {
        "economic_class": "PRIOR_PERIOD_ENTRY_VOID",
        "correction_scope": authorization.correction_scope,
        "correction_reason": authorization.reason,
        "current_period_pnl_treatment": authorization.current_period_pnl_treatment,
        "restatement_required": "YES",
        "correction_authorization_digest": authorization.digest,
        "affected_period_id": authorization.affected_period_id,
        "target_period_id": authorization.target_period_id,
        "original_period_close_digest": authorization.original_period_close_digest,
        "original_accounting_close_digest": authorization.original_accounting_close_digest,
        "original_ledger_event_digest": authorization.original_ledger_event_digest,
        "original_reporting_entry_digest": authorization.original_reporting_entry_digest,
        "period_chain_proof_digest": authorization.period_chain_proof_digest,
        "correction_evidence_digest": authorization.correction_evidence_digest,
        "decision_evidence_digest": authorization.decision_evidence_digest,
        "accounting_policy_digest": authorization.accounting_policy_digest,
        "requirement_registry_digest": authorization.requirement_registry_digest,
        "original_event_type": str(original_ledger_event.get("event_type")),
        "original_total": canonical_decimal_text(
            sum((line.debit for line in lines), ZERO)
        ),
    }
    return ledger.post(
        event_id=event_id,
        reference=authorization.authorization_id,
        flow_type=FlowType.INTERNAL,
        lines=lines,
        evidence_digest=authorization.digest,
        metadata=metadata,
    )
