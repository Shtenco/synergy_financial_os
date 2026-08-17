from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .canonical_json import MAX_SAFE_JSON_INTEGER
from .core import AccountingInvariantError
from .governance import requirement_ids_from_registry, requirement_registry_digest
from .numeric import canonical_decimal_text, finite_decimal
from .snapshot import FinancialSnapshotV2


ZERO = Decimal("0")
AI_DECISIONS = frozenset({"PROPOSE", "NO_ACTION"})
AI_REVIEW_STATUSES = frozenset({"REVIEWABLE", "NO_ACTION", "STALE", "BLOCKED"})
POLICY_MODES = frozenset({"GROWTH", "NORMAL", "DEFENSE", "EMERGENCY"})
ALLOWED_ACTION_TYPES = frozenset(
    {
        "CREDIT_CAP",
        "PRODUCTIVE_QE_CAP",
        "QT_SHARE",
        "RESERVE_TARGET",
        "INSURANCE_TARGET",
        "MIDAS_RISK_CAP",
        "BUYBACK_PROFIT_SHARE",
        "DEMURRAGE_CORRIDOR",
        "TERM_SAVINGS_TARGET",
        "OTHER_REVIEW_ONLY",
    }
)


def _d(value: Decimal | int | str, field_name: str) -> Decimal:
    return finite_decimal(value, field_name)


def _require_canonical_decimal_string(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise AccountingInvariantError(f"{field_name} must be a canonical decimal string")
    number = _d(value, field_name)
    expected = canonical_decimal_text(number, field_name)
    if value != expected:
        raise AccountingInvariantError(
            f"{field_name} is not canonical decimal text: expected {expected!r}, got {value!r}"
        )
    return number


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AccountingInvariantError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AccountingInvariantError(f"{field_name} must be ISO-8601 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AccountingInvariantError(f"{field_name} must be timezone-aware")
    return parsed


def _validate_digest_refs(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AccountingInvariantError(f"{field_name} must be an array")
    normalized = tuple(_hex64(str(item), f"{field_name} item") for item in value)
    if len(normalized) != len(set(normalized)):
        raise AccountingInvariantError(f"{field_name} must contain unique digests")
    return normalized


@dataclass(frozen=True)
class AIPolicyProposalReview:
    proposal_id: str
    decision: str
    status: str
    snapshot_digest: str
    requirement_registry_digest: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        proposal_id = self.proposal_id.strip()
        decision = self.decision.upper().strip()
        status = self.status.upper().strip()
        if not proposal_id:
            raise AccountingInvariantError("proposal_id is required")
        if decision not in AI_DECISIONS:
            raise AccountingInvariantError(f"unsupported AI decision: {decision}")
        if status not in AI_REVIEW_STATUSES:
            raise AccountingInvariantError(f"unsupported AI review status: {status}")
        object.__setattr__(self, "proposal_id", proposal_id)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "snapshot_digest",
            _hex64(self.snapshot_digest, "snapshot_digest"),
        )
        object.__setattr__(
            self,
            "requirement_registry_digest",
            _hex64(self.requirement_registry_digest, "requirement_registry_digest"),
        )
        blockers = tuple(sorted(set(item.strip() for item in self.blockers if item.strip())))
        object.__setattr__(self, "blockers", blockers)
        if status == "REVIEWABLE" and blockers:
            raise AccountingInvariantError("REVIEWABLE AI proposal cannot contain blockers")
        if status in {"STALE", "BLOCKED"} and not blockers:
            raise AccountingInvariantError(f"{status} AI review requires blockers")

    @property
    def reviewable(self) -> bool:
        return self.status == "REVIEWABLE"


def review_ai_policy_proposal(
    proposal: Mapping[str, Any],
    current_snapshot: FinancialSnapshotV2,
    *,
    now: datetime,
    requirement_registry: Mapping[str, Any],
) -> AIPolicyProposalReview:
    """Review an AI proposal against exact financial state and constitution.

    The function never mutates the ledger and never authorizes execution. Its
    strongest positive result is ``REVIEWABLE``. A proposal is optimistic-
    concurrency-bound to the exact FinancialSnapshot, ledger sequence,
    valuation policy, requirement-registry content and TTL used to create it.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise AccountingInvariantError("AI review `now` must be timezone-aware")
    if proposal.get("schema") != "ai.policy-proposal/v2":
        raise AccountingInvariantError("unsupported AI policy proposal schema")

    known_requirements = requirement_ids_from_registry(requirement_registry)
    current_registry_digest = requirement_registry_digest(requirement_registry)

    proposal_id = str(proposal.get("proposal_id", "")).strip()
    model_id = str(proposal.get("model_id", "")).strip()
    if not proposal_id:
        raise AccountingInvariantError("proposal_id is required")
    if not model_id:
        raise AccountingInvariantError("model_id is required")
    decision = str(proposal.get("decision", "")).upper().strip()
    if decision not in AI_DECISIONS:
        raise AccountingInvariantError(f"unsupported AI decision: {decision}")
    if proposal.get("authorization") != "NONE":
        raise AccountingInvariantError("AI policy proposal authorization must be NONE")
    if proposal.get("input_snapshot_schema") != "financial.snapshot/v2":
        raise AccountingInvariantError("AI proposal must target financial.snapshot/v2")

    generated_at = _parse_datetime(proposal.get("generated_at"), "generated_at")
    expires_at = _parse_datetime(proposal.get("expires_at"), "expires_at")
    if expires_at <= generated_at:
        raise AccountingInvariantError("expires_at must be after generated_at")
    if generated_at > now:
        raise AccountingInvariantError("AI proposal cannot be generated in the future")

    model_artifact_digest = proposal.get("model_artifact_digest")
    if model_artifact_digest is not None:
        _hex64(str(model_artifact_digest), "model_artifact_digest")

    input_snapshot_digest = _hex64(
        str(proposal.get("input_snapshot_digest", "")),
        "input_snapshot_digest",
    )
    input_valuation_policy_digest = _hex64(
        str(proposal.get("input_valuation_policy_digest", "")),
        "input_valuation_policy_digest",
    )
    input_requirement_registry_digest = _hex64(
        str(proposal.get("input_requirement_registry_digest", "")),
        "input_requirement_registry_digest",
    )
    input_ledger_sequence = proposal.get("input_ledger_sequence")
    if (
        not isinstance(input_ledger_sequence, int)
        or isinstance(input_ledger_sequence, bool)
        or input_ledger_sequence < 0
        or input_ledger_sequence > MAX_SAFE_JSON_INTEGER
    ):
        raise AccountingInvariantError(
            "input_ledger_sequence must be a non-negative cross-language safe integer"
        )

    actions = proposal.get("actions")
    if not isinstance(actions, list):
        raise AccountingInvariantError("actions must be an array")
    proposed_policy_mode = proposal.get("proposed_policy_mode")
    if proposed_policy_mode is not None:
        proposed_policy_mode = str(proposed_policy_mode).upper().strip()
        if proposed_policy_mode not in POLICY_MODES:
            raise AccountingInvariantError("unsupported proposed_policy_mode")

    if decision == "NO_ACTION":
        if actions:
            raise AccountingInvariantError("NO_ACTION proposal cannot contain actions")
        if proposed_policy_mode is not None:
            raise AccountingInvariantError(
                "NO_ACTION proposal cannot contain proposed_policy_mode"
            )
    else:
        if not actions:
            raise AccountingInvariantError("PROPOSE decision requires at least one action")

    hard_invariant_refs = proposal.get("hard_invariant_refs")
    if not isinstance(hard_invariant_refs, list):
        raise AccountingInvariantError("hard_invariant_refs must be an array")
    if len(hard_invariant_refs) != len(set(hard_invariant_refs)):
        raise AccountingInvariantError("hard_invariant_refs must be unique")
    if decision == "PROPOSE" and not hard_invariant_refs:
        raise AccountingInvariantError(
            "PROPOSE decision must declare at least one hard invariant reference"
        )
    for ref in hard_invariant_refs:
        if not isinstance(ref, str) or not ref.startswith("REQ-"):
            raise AccountingInvariantError("hard invariant references must use REQ-* ids")
        if ref not in known_requirements:
            raise AccountingInvariantError(f"unknown hard invariant reference: {ref}")

    _validate_digest_refs(proposal.get("evidence_refs"), "evidence_refs")
    _validate_digest_refs(
        proposal.get("project_screening_refs", []),
        "project_screening_refs",
    )

    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise AccountingInvariantError("AI action must be an object")
        action_type = str(action.get("action_type", "")).upper().strip()
        if action_type not in ALLOWED_ACTION_TYPES:
            raise AccountingInvariantError(f"unsupported AI action_type: {action_type}")
        value = _require_canonical_decimal_string(
            action.get("value"),
            f"actions[{index}].value",
        )
        lower = _require_canonical_decimal_string(
            action.get("lower_bound"),
            f"actions[{index}].lower_bound",
        )
        upper = _require_canonical_decimal_string(
            action.get("upper_bound"),
            f"actions[{index}].upper_bound",
        )
        if lower > upper:
            raise AccountingInvariantError("AI action lower_bound cannot exceed upper_bound")
        if not lower <= value <= upper:
            raise AccountingInvariantError(
                f"AI action {action_type} value is outside declared hard bounds"
            )
        if not str(action.get("target", "")).strip():
            raise AccountingInvariantError("AI action target is required")
        if not str(action.get("unit", "")).strip():
            raise AccountingInvariantError("AI action unit is required")
        if not str(action.get("reason_code", "")).strip():
            raise AccountingInvariantError("AI action reason_code is required")

    current_digest = current_snapshot.digest
    blockers: list[str] = []
    if now >= expires_at:
        blockers.append("PROPOSAL_EXPIRED")
    if input_snapshot_digest != current_digest:
        blockers.append("STALE_INPUT_SNAPSHOT")
    if input_ledger_sequence != current_snapshot.sequence:
        blockers.append("STALE_LEDGER_SEQUENCE")
    if input_valuation_policy_digest != current_snapshot.valuation_policy_digest:
        blockers.append("STALE_VALUATION_POLICY")
    if input_requirement_registry_digest != current_registry_digest:
        blockers.append("STALE_REQUIREMENT_REGISTRY")

    if blockers:
        return AIPolicyProposalReview(
            proposal_id=proposal_id,
            decision=decision,
            status="STALE",
            snapshot_digest=current_digest,
            requirement_registry_digest=current_registry_digest,
            blockers=tuple(blockers),
        )

    if current_snapshot.invariant_failures:
        return AIPolicyProposalReview(
            proposal_id=proposal_id,
            decision=decision,
            status="BLOCKED",
            snapshot_digest=current_digest,
            requirement_registry_digest=current_registry_digest,
            blockers=tuple(
                f"CURRENT_SNAPSHOT_INVARIANT:{failure}"
                for failure in current_snapshot.invariant_failures
            ),
        )

    if decision == "NO_ACTION":
        return AIPolicyProposalReview(
            proposal_id=proposal_id,
            decision=decision,
            status="NO_ACTION",
            snapshot_digest=current_digest,
            requirement_registry_digest=current_registry_digest,
            blockers=(),
        )

    return AIPolicyProposalReview(
        proposal_id=proposal_id,
        decision=decision,
        status="REVIEWABLE",
        snapshot_digest=current_digest,
        requirement_registry_digest=current_registry_digest,
        blockers=(),
    )
