from __future__ import annotations

from typing import Any, Mapping

from .capital_authorization_v2 import CapitalAuthorizationV2
from .reporting import ReportingEntry, ReportingLedger
from .revenue_posting_v2 import (
    RevenuePostingAccountsV2,
    RevenuePostingV2Error,
    post_recognized_external_revenue_v2,
)
from .revenue_recognition_v2 import (
    RevenueRecognitionDecisionV2,
    RevenueRecognitionRequestV2,
    evaluate_revenue_recognition_v2,
)


def post_external_revenue_from_evidence_v2(
    ledger: ReportingLedger,
    *,
    receipt_payload: Mapping[str, Any],
    authorization: CapitalAuthorizationV2,
    recognition_request: RevenueRecognitionRequestV2,
    accounts: RevenuePostingAccountsV2,
    event_id: str,
) -> tuple[RevenueRecognitionDecisionV2, ReportingEntry]:
    """Canonical posting path: re-evaluate raw evidence immediately before ledger post.

    No preconstructed recognition decision is accepted by this wrapper. The same
    receipt/auth/request evidence is evaluated at posting time, closing a decision
    object injection/bypass path. The underlying ReportingLedger remains unchanged.
    """

    decision = evaluate_revenue_recognition_v2(
        receipt_payload,
        authorization,
        recognition_request,
    )
    if decision.decision != "RECOGNIZED" or not decision.ledger_posting_allowed:
        raise RevenuePostingV2Error(
            "raw evidence does not currently permit EXTERNAL_REVENUE posting: "
            + ",".join(decision.blockers)
        )
    entry = post_recognized_external_revenue_v2(
        ledger,
        decision,
        accounts,
        event_id=event_id,
    )
    if entry.evidence_digest != decision.digest:
        raise RevenuePostingV2Error(
            "ReportingLedger entry did not preserve revenue-recognition evidence digest"
        )
    return decision, entry
