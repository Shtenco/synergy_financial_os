from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .account_registry_v1 import (
    AccountRegistryV1,
    verify_account_registry_against_snapshot_v1,
)
from .accounting_close_v2 import (
    AccountingCloseV2,
    verify_accounting_close_v2,
    verify_financial_snapshot_v2_payload,
)
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .accounting_restatement_view_v1 import (
    AccountingRestatementOverlayV1,
    RestatedPeriodViewV1,
)
from .core import AccountingInvariantError
from .ledger_event_v2 import verify_ledger_event_v2
from .numeric import canonical_decimal_text
from .reporting import FlowType, ReportingLine
from .reporting_metrics import (
    REALIZED_PNL_FLOWS,
    entry_pnl_effect,
)
from .valuation_policy_artifact_v1 import (
    ValuationPolicyArtifactV1,
    verify_valuation_policy_against_snapshot_v1,
)


SCHEMA = "accounting.statement-replay/v1"
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
HEX = frozenset("0123456789abcdef")
ZERO = Decimal("0")


class StatementReplayV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StatementReplayV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise StatementReplayV1Error(f"{field_name} must be hex64")
    return result


def _safe_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StatementReplayV1Error(f"{field_name} must be integer")
    if value < minimum or value > MAX_SAFE_JSON_INTEGER:
        raise StatementReplayV1Error(
            f"{field_name} must be between {minimum} and {MAX_SAFE_JSON_INTEGER}"
        )
    return value


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StatementReplayV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _parse_utc(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith("Z"):
        raise StatementReplayV1Error(f"{field_name} must use canonical UTC Z time")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StatementReplayV1Error(f"{field_name} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StatementReplayV1Error(f"{field_name} must be timezone-aware")
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise StatementReplayV1Error(f"{field_name} is not canonical UTC text")
    return parsed.astimezone(UTC)


def _digest(payload: Any) -> str:
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
class StatementReplayV1:
    replay_id: str
    affected_period_id: str
    original_period_close_digest: str
    original_accounting_close_digest: str
    original_financial_snapshot_digest: str
    opening_period_close_digest: str | None
    opening_accounting_close_digest: str | None
    account_registry_artifact_digest: str
    account_registry_digest: str
    valuation_policy_artifact_digest: str
    valuation_policy_digest: str
    restated_period_view_digest: str
    overlay_digests: tuple[str, ...]
    excluded_reporting_entry_digests: tuple[str, ...]
    opening_sequence: int
    closing_sequence: int
    original_event_count: int
    retained_event_count: int
    excluded_event_count: int
    replayed_ledger_digest: str
    replayed_last_entry_digest: str
    hard_external_assets: Decimal
    liquid_haircut_assets: Decimal
    economic_haircut_assets: Decimal
    external_liabilities: Decimal
    hard_nav: Decimal
    liquid_nav: Decimal
    economic_nav: Decimal
    realized_external_revenue: Decimal
    realized_external_pnl: Decimal
    generated_at: datetime
    liquidity_metrics: str = "NOT_PERFORMED"
    distribution_metrics: str = "NOT_PERFORMED"
    authority: str = "FINANCIAL_OS_REPLAY_DERIVATION"
    ledger_mutation_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.liquidity_metrics != "NOT_PERFORMED" or self.distribution_metrics != "NOT_PERFORMED":
            raise StatementReplayV1Error("v1 does not calculate liquidity/distribution metrics")
        if self.authority != "FINANCIAL_OS_REPLAY_DERIVATION":
            raise StatementReplayV1Error("statement replay authority must remain Financial OS")
        if self.ledger_mutation_authority != "NONE" or self.execution_authority != "NONE":
            raise StatementReplayV1Error("statement replay cannot mutate canonical ledger or execute")
        object.__setattr__(self, "replay_id", _text(self.replay_id, "replay_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        for field_name in (
            "original_period_close_digest",
            "original_accounting_close_digest",
            "original_financial_snapshot_digest",
            "account_registry_artifact_digest",
            "account_registry_digest",
            "valuation_policy_artifact_digest",
            "valuation_policy_digest",
            "restated_period_view_digest",
            "replayed_ledger_digest",
            "replayed_last_entry_digest",
        ):
            object.__setattr__(self, field_name, _hex64(getattr(self, field_name), field_name))
        for field_name in ("opening_period_close_digest", "opening_accounting_close_digest"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _hex64(value, field_name))
        overlays = tuple(sorted(_hex64(item, "overlay_digest") for item in self.overlay_digests))
        excluded = tuple(
            sorted(_hex64(item, "excluded_reporting_entry_digest") for item in self.excluded_reporting_entry_digests)
        )
        if not overlays or len(overlays) != len(set(overlays)):
            raise StatementReplayV1Error("replay requires unique restatement overlays")
        if not excluded or len(excluded) != len(set(excluded)):
            raise StatementReplayV1Error("replay requires unique excluded ReportingEntry digests")
        object.__setattr__(self, "overlay_digests", overlays)
        object.__setattr__(self, "excluded_reporting_entry_digests", excluded)
        opening = _safe_int(self.opening_sequence, "opening_sequence")
        closing = _safe_int(self.closing_sequence, "closing_sequence", minimum=1)
        original_count = _safe_int(self.original_event_count, "original_event_count", minimum=1)
        retained = _safe_int(self.retained_event_count, "retained_event_count")
        excluded_count = _safe_int(self.excluded_event_count, "excluded_event_count", minimum=1)
        if opening >= closing or closing != original_count:
            raise StatementReplayV1Error("invalid opening/closing sequence boundary")
        if retained + excluded_count != original_count:
            raise StatementReplayV1Error("retained + excluded event counts must equal original prefix size")
        if excluded_count != len(excluded):
            raise StatementReplayV1Error("excluded_event_count must equal excluded digest count")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))
        for field_name in (
            "hard_external_assets",
            "liquid_haircut_assets",
            "economic_haircut_assets",
            "external_liabilities",
        ):
            value = Decimal(getattr(self, field_name))
            if not value.is_finite() or value < ZERO:
                raise StatementReplayV1Error(f"{field_name} must be finite non-negative Decimal")
            object.__setattr__(self, field_name, value)
        for field_name in (
            "hard_nav",
            "liquid_nav",
            "economic_nav",
            "realized_external_revenue",
            "realized_external_pnl",
        ):
            value = Decimal(getattr(self, field_name))
            if not value.is_finite():
                raise StatementReplayV1Error(f"{field_name} must be finite Decimal")
            object.__setattr__(self, field_name, value)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "replay_id": self.replay_id,
            "affected_period_id": self.affected_period_id,
            "original_period_close_digest": self.original_period_close_digest,
            "original_accounting_close_digest": self.original_accounting_close_digest,
            "original_financial_snapshot_digest": self.original_financial_snapshot_digest,
            "opening_period_close_digest": self.opening_period_close_digest,
            "opening_accounting_close_digest": self.opening_accounting_close_digest,
            "account_registry_artifact_digest": self.account_registry_artifact_digest,
            "account_registry_digest": self.account_registry_digest,
            "valuation_policy_artifact_digest": self.valuation_policy_artifact_digest,
            "valuation_policy_digest": self.valuation_policy_digest,
            "restated_period_view_digest": self.restated_period_view_digest,
            "overlay_digests": list(self.overlay_digests),
            "excluded_reporting_entry_digests": list(self.excluded_reporting_entry_digests),
            "opening_sequence": self.opening_sequence,
            "closing_sequence": self.closing_sequence,
            "original_event_count": self.original_event_count,
            "retained_event_count": self.retained_event_count,
            "excluded_event_count": self.excluded_event_count,
            "replayed_ledger_digest": self.replayed_ledger_digest,
            "replayed_last_entry_digest": self.replayed_last_entry_digest,
            "hard_external_assets": canonical_decimal_text(self.hard_external_assets),
            "liquid_haircut_assets": canonical_decimal_text(self.liquid_haircut_assets),
            "economic_haircut_assets": canonical_decimal_text(self.economic_haircut_assets),
            "external_liabilities": canonical_decimal_text(self.external_liabilities),
            "hard_nav": canonical_decimal_text(self.hard_nav),
            "liquid_nav": canonical_decimal_text(self.liquid_nav),
            "economic_nav": canonical_decimal_text(self.economic_nav),
            "realized_external_revenue": canonical_decimal_text(self.realized_external_revenue),
            "realized_external_pnl": canonical_decimal_text(self.realized_external_pnl),
            "liquidity_metrics": self.liquidity_metrics,
            "distribution_metrics": self.distribution_metrics,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "ledger_mutation_authority": self.ledger_mutation_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def _validate_period_boundary(
    period: AccountingPeriodV1,
    period_close: AccountingPeriodCloseV1,
    accounting_close: AccountingCloseV2,
    opening_period_close: AccountingPeriodCloseV1 | None,
    opening_accounting_close: AccountingCloseV2 | None,
) -> int:
    if period_close.period_id != period.period_id:
        raise StatementReplayV1Error("PeriodClose period_id mismatch")
    if period_close.accounting_period_digest != period.digest:
        raise StatementReplayV1Error("PeriodClose accounting-period digest mismatch")
    if period_close.accounting_close_digest != accounting_close.digest:
        raise StatementReplayV1Error("PeriodClose AccountingClose digest mismatch")
    if period_close.previous_period_close_digest != period.opening_period_close_digest:
        raise StatementReplayV1Error("PeriodClose opening chain mismatch")
    if period.opening_period_close_digest is None:
        if opening_period_close is not None or opening_accounting_close is not None:
            raise StatementReplayV1Error("genesis period cannot supply opening close context")
        return 0
    if opening_period_close is None or opening_accounting_close is None:
        raise StatementReplayV1Error("non-genesis period requires opening PeriodClose and AccountingClose")
    if opening_period_close.digest != period.opening_period_close_digest:
        raise StatementReplayV1Error("opening PeriodClose digest mismatch")
    if opening_period_close.accounting_close_digest != opening_accounting_close.digest:
        raise StatementReplayV1Error("opening PeriodClose/AccountingClose mismatch")
    if opening_accounting_close.event_count >= accounting_close.event_count:
        raise StatementReplayV1Error("opening AccountingClose must precede closing AccountingClose")
    return opening_accounting_close.event_count


def build_statement_replay_v1(
    *,
    replay_id: str,
    period: AccountingPeriodV1,
    period_close: AccountingPeriodCloseV1,
    accounting_close: AccountingCloseV2,
    financial_snapshot: Mapping[str, Any],
    ledger_events: Sequence[Mapping[str, Any]],
    account_registry: AccountRegistryV1,
    valuation_policy_artifact: ValuationPolicyArtifactV1,
    restated_view: RestatedPeriodViewV1,
    restatement_overlays: Sequence[AccountingRestatementOverlayV1],
    generated_at: datetime,
    opening_period_close: AccountingPeriodCloseV1 | None = None,
    opening_accounting_close: AccountingCloseV2 | None = None,
) -> StatementReplayV1:
    snapshot = verify_financial_snapshot_v2_payload(financial_snapshot)
    verify_accounting_close_v2(ledger_events, snapshot, accounting_close)
    if period_close.financial_snapshot_digest != snapshot["digest"]:
        raise StatementReplayV1Error("PeriodClose FinancialSnapshot digest mismatch")
    if snapshot.get("as_of") != period.ends_at.isoformat().replace("+00:00", "Z"):
        raise StatementReplayV1Error("FinancialSnapshot as_of must equal period end")
    if snapshot.get("accounting_perimeter") != period.accounting_perimeter:
        raise StatementReplayV1Error("FinancialSnapshot accounting perimeter mismatch")
    if snapshot.get("reporting_currency") != period.reporting_currency:
        raise StatementReplayV1Error("FinancialSnapshot reporting currency mismatch")
    if accounting_close.requirement_registry_digest != period.requirement_registry_digest:
        raise StatementReplayV1Error("AccountingClose requirement registry mismatch")

    opening_sequence = _validate_period_boundary(
        period,
        period_close,
        accounting_close,
        opening_period_close,
        opening_accounting_close,
    )
    closing_sequence = accounting_close.event_count

    verify_account_registry_against_snapshot_v1(account_registry, snapshot)
    verify_valuation_policy_against_snapshot_v1(valuation_policy_artifact, snapshot)
    if account_registry.reporting_currency != valuation_policy_artifact.policy.reporting_currency:
        raise StatementReplayV1Error("account registry / valuation policy currency mismatch")

    overlays = tuple(restatement_overlays)
    if not overlays or any(not isinstance(item, AccountingRestatementOverlayV1) for item in overlays):
        raise StatementReplayV1Error("restatement_overlays must contain AccountingRestatementOverlayV1")
    if restated_view.affected_period_id != period.period_id:
        raise StatementReplayV1Error("RestatedPeriodView affected period mismatch")
    if restated_view.original_period_close_digest != period_close.digest:
        raise StatementReplayV1Error("RestatedPeriodView original PeriodClose mismatch")
    overlay_digests = tuple(sorted(item.digest for item in overlays))
    excluded_digests = tuple(sorted(item.original_reporting_entry_digest for item in overlays))
    if overlay_digests != restated_view.overlay_digests:
        raise StatementReplayV1Error("RestatedPeriodView overlay digest set mismatch")
    if excluded_digests != restated_view.excluded_reporting_entry_digests:
        raise StatementReplayV1Error("RestatedPeriodView excluded ReportingEntry set mismatch")
    for overlay in overlays:
        if overlay.affected_period_id != period.period_id:
            raise StatementReplayV1Error("overlay affected period mismatch")
        if overlay.original_period_close_digest != period_close.digest:
            raise StatementReplayV1Error("overlay original PeriodClose mismatch")

    verified_events = tuple(verify_ledger_event_v2(item) for item in ledger_events)
    by_entry_digest = {item["reporting_entry_digest"]: item for item in verified_events}
    if len(by_entry_digest) != len(verified_events):
        raise StatementReplayV1Error("ledger prefix contains duplicate ReportingEntry digest")
    period_entry_digests = {
        item["reporting_entry_digest"]
        for item in verified_events[opening_sequence:closing_sequence]
    }
    missing = sorted(set(excluded_digests) - set(by_entry_digest))
    if missing:
        raise StatementReplayV1Error("restatement excludes ReportingEntry not present in sealed prefix")
    outside_period = sorted(set(excluded_digests) - period_entry_digests)
    if outside_period:
        raise StatementReplayV1Error("v1 replay may exclude only ReportingEntries in the affected period")

    for index, event in enumerate(verified_events[opening_sequence:closing_sequence], start=opening_sequence):
        when = _parse_utc(event.get("effective_at"), f"ledger_events[{index}].effective_at")
        if not period.contains(when):
            raise StatementReplayV1Error("period ledger event effective_at lies outside accounting period")

    replay_ledger = account_registry.instantiate_empty_reporting_ledger()
    retained_entries: list[tuple[int, Any]] = []
    excluded_set = set(excluded_digests)
    for event in verified_events:
        if event["reporting_entry_digest"] in excluded_set:
            continue
        lines = tuple(
            ReportingLine(
                account_id=line["account"],
                debit=Decimal(line["debit"]),
                credit=Decimal(line["credit"]),
            )
            for line in event["lines"]
        )
        entry = replay_ledger.post(
            event_id=event["event_id"],
            reference=event["external_reference"],
            flow_type=FlowType(event["event_type"]),
            lines=lines,
            evidence_digest=event["evidence_digest"],
            metadata=event["metadata"],
        )
        retained_entries.append((event["sequence"], entry))

    replay_ledger.assert_balanced()
    state = replay_ledger.financial_state(valuation_policy_artifact.policy.rule_map)
    realized_revenue = ZERO
    realized_pnl = ZERO
    for original_sequence, entry in retained_entries:
        if not (opening_sequence < original_sequence <= closing_sequence):
            continue
        if entry.flow_type == FlowType.EXTERNAL_REVENUE:
            realized_revenue += entry_pnl_effect(replay_ledger, entry)
        if entry.flow_type in REALIZED_PNL_FLOWS:
            realized_pnl += entry_pnl_effect(replay_ledger, entry)

    return StatementReplayV1(
        replay_id=replay_id,
        affected_period_id=period.period_id,
        original_period_close_digest=period_close.digest,
        original_accounting_close_digest=accounting_close.digest,
        original_financial_snapshot_digest=snapshot["digest"],
        opening_period_close_digest=period.opening_period_close_digest,
        opening_accounting_close_digest=(
            opening_accounting_close.digest if opening_accounting_close is not None else None
        ),
        account_registry_artifact_digest=account_registry.digest,
        account_registry_digest=account_registry.account_registry_digest,
        valuation_policy_artifact_digest=valuation_policy_artifact.digest,
        valuation_policy_digest=valuation_policy_artifact.policy.digest,
        restated_period_view_digest=restated_view.digest,
        overlay_digests=overlay_digests,
        excluded_reporting_entry_digests=excluded_digests,
        opening_sequence=opening_sequence,
        closing_sequence=closing_sequence,
        original_event_count=len(verified_events),
        retained_event_count=len(retained_entries),
        excluded_event_count=len(excluded_digests),
        replayed_ledger_digest=replay_ledger.digest,
        replayed_last_entry_digest=replay_ledger.last_entry_digest,
        hard_external_assets=state.hard_external_assets,
        liquid_haircut_assets=state.liquid_haircut_assets,
        economic_haircut_assets=state.economic_haircut_assets,
        external_liabilities=state.external_liabilities,
        hard_nav=state.hard_nav,
        liquid_nav=state.liquid_nav,
        economic_nav=state.economic_nav,
        realized_external_revenue=realized_revenue,
        realized_external_pnl=realized_pnl,
        generated_at=generated_at,
    )
