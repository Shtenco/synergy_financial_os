from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .distribution_available_capacity_v2 import DistributionAvailableCapacityV2
from .distribution_capacity_reservation_v1 import (
    DistributionCapacityReservationV1,
    DistributionCapacityReservationV1Error,
    DistributionCommitmentBookV1,
    DistributionCommitmentStateV1,
)
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingLedger


ZERO = Decimal("0")
_ALLOWED_TRANSITIONS = {
    "ACTIVE": {"ATTEMPTED", "RELEASED_EXPIRED"},
    "ATTEMPTED": {"SETTLED_PENDING_ACCOUNTING", "RELEASED_TERMINAL_FAILED"},
    "SETTLED_PENDING_ACCOUNTING": {"ACCOUNTED"},
}


def _decimal(value: Any, field_name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionCapacityReservationV1Error(f"{field_name} must be canonical decimal text")
    result = finite_decimal(value, field_name)
    if canonical_decimal_text(result) != value:
        raise DistributionCapacityReservationV1Error(f"{field_name} is not canonical decimal text")
    if result < ZERO or (positive and result <= ZERO):
        raise DistributionCapacityReservationV1Error(f"{field_name} has invalid sign")
    return result


def _time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DistributionCapacityReservationV1Error(f"{field_name} must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise DistributionCapacityReservationV1Error(f"{field_name} is not canonical UTC text")
    return parsed


def verify_distribution_capacity_reservation_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionCapacityReservationV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.capacity-reservation/v1":
        raise DistributionCapacityReservationV1Error("unsupported distribution capacity reservation schema")
    reservation = DistributionCapacityReservationV1(
        reservation_id=payload.get("reservation_id"),
        plan_digest=payload.get("plan_digest"),
        affected_period_id=payload.get("affected_period_id"),
        distribution_currency=payload.get("distribution_currency"),
        capacity_basis_digest=payload.get("capacity_basis_digest"),
        capacity_basis_snapshot_digest=payload.get("capacity_basis_snapshot_digest"),
        capacity_basis_ledger_digest=payload.get("capacity_basis_ledger_digest"),
        capacity_basis_ledger_sequence=payload.get("capacity_basis_ledger_sequence"),
        reserved_amount=_decimal(payload.get("reserved_amount"), "reserved_amount", positive=True),
        settled_amount=_decimal(payload.get("settled_amount"), "settled_amount"),
        outstanding_amount=_decimal(payload.get("outstanding_amount"), "outstanding_amount"),
        status=payload.get("status"),
        version=payload.get("version"),
        created_at=_time(payload.get("created_at"), "created_at"),
        updated_at=_time(payload.get("updated_at"), "updated_at"),
        expires_at=_time(payload.get("expires_at"), "expires_at"),
        previous_reservation_digest=payload.get("previous_reservation_digest"),
        attempt_digest=payload.get("attempt_digest"),
        utilization_digest=payload.get("utilization_digest"),
        accounting_entry_digest=payload.get("accounting_entry_digest"),
        authority=payload.get("authority"),
        accounting_authority=payload.get("accounting_authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
        ai_authority=payload.get("ai_authority"),
    )
    if reservation.to_dict() != dict(payload):
        raise DistributionCapacityReservationV1Error("reservation payload is not canonical or digest mismatch")
    return reservation


def verify_distribution_commitment_state_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionCommitmentStateV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.commitment-state/v1":
        raise DistributionCapacityReservationV1Error("unsupported distribution commitment state schema")
    state = DistributionCommitmentStateV1(
        state_id=payload.get("state_id"),
        state_version=payload.get("state_version"),
        previous_state_digest=payload.get("previous_state_digest"),
        reporting_currency=payload.get("reporting_currency"),
        current_available_capacity_digest=payload.get("current_available_capacity_digest"),
        current_snapshot_digest=payload.get("current_snapshot_digest"),
        current_snapshot_ledger_digest=payload.get("current_snapshot_ledger_digest"),
        current_snapshot_ledger_sequence=payload.get("current_snapshot_ledger_sequence"),
        current_available_capacity=_decimal(payload.get("current_available_capacity"), "current_available_capacity"),
        outstanding_commitments=_decimal(payload.get("outstanding_commitments"), "outstanding_commitments"),
        remaining_authorizable_capacity=_decimal(payload.get("remaining_authorizable_capacity"), "remaining_authorizable_capacity"),
        reservation_latest_digests=tuple(payload.get("reservation_latest_digests") or ()),
        blockers=tuple(payload.get("blockers") or ()),
        status=payload.get("status"),
        generated_at=_time(payload.get("generated_at"), "generated_at"),
        authority=payload.get("authority"),
        accounting_authority=payload.get("accounting_authority"),
        authorization_authority=payload.get("authorization_authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
    )
    if state.to_dict() != dict(payload):
        raise DistributionCapacityReservationV1Error("commitment state payload is not canonical or digest mismatch")
    return state


def verify_reservation_chain_v1(chain: Sequence[DistributionCapacityReservationV1]) -> bool:
    values = tuple(chain)
    if not values:
        raise DistributionCapacityReservationV1Error("reservation chain cannot be empty")
    first = values[0]
    fixed = (
        first.reservation_id,
        first.plan_digest,
        first.affected_period_id,
        first.distribution_currency,
        first.capacity_basis_digest,
        first.capacity_basis_snapshot_digest,
        first.capacity_basis_ledger_digest,
        first.capacity_basis_ledger_sequence,
        first.reserved_amount,
        first.created_at,
        first.expires_at,
    )
    for index, item in enumerate(values):
        if item.version != index + 1:
            raise DistributionCapacityReservationV1Error("reservation chain version gap")
        if (
            item.reservation_id,
            item.plan_digest,
            item.affected_period_id,
            item.distribution_currency,
            item.capacity_basis_digest,
            item.capacity_basis_snapshot_digest,
            item.capacity_basis_ledger_digest,
            item.capacity_basis_ledger_sequence,
            item.reserved_amount,
            item.created_at,
            item.expires_at,
        ) != fixed:
            raise DistributionCapacityReservationV1Error("reservation immutable identity/basis changed across versions")
        if index == 0:
            if item.status != "ACTIVE" or item.previous_reservation_digest is not None:
                raise DistributionCapacityReservationV1Error("reservation chain must start ACTIVE")
            continue
        previous = values[index - 1]
        if item.previous_reservation_digest != previous.digest:
            raise DistributionCapacityReservationV1Error("reservation previous digest chain mismatch")
        if item.updated_at < previous.updated_at:
            raise DistributionCapacityReservationV1Error("reservation update time moved backwards")
        if item.status not in _ALLOWED_TRANSITIONS.get(previous.status, set()):
            raise DistributionCapacityReservationV1Error(
                f"invalid reservation transition {previous.status}->{item.status}"
            )
    return True


def verify_commitment_state_transition_v1(
    previous: DistributionCommitmentStateV1,
    current: DistributionCommitmentStateV1,
) -> bool:
    if current.state_version != previous.state_version + 1:
        raise DistributionCapacityReservationV1Error("commitment state version must increment by one")
    if current.previous_state_digest != previous.digest:
        raise DistributionCapacityReservationV1Error("commitment state previous digest mismatch")
    if current.generated_at < previous.generated_at:
        raise DistributionCapacityReservationV1Error("commitment state time moved backwards")
    return True


def verify_commitment_state_context_v1(
    state: DistributionCommitmentStateV1,
    *,
    capacity: DistributionAvailableCapacityV2,
    latest_reservations: Sequence[DistributionCapacityReservationV1],
) -> bool:
    values = tuple(latest_reservations)
    ids = [item.reservation_id for item in values]
    if len(ids) != len(set(ids)):
        raise DistributionCapacityReservationV1Error("latest reservation set contains duplicate reservation_id")
    if state.current_available_capacity_digest != capacity.digest:
        raise DistributionCapacityReservationV1Error("commitment state / current capacity digest mismatch")
    if state.current_snapshot_digest != capacity.current_financial_snapshot_digest:
        raise DistributionCapacityReservationV1Error("commitment state / current snapshot mismatch")
    if state.current_snapshot_ledger_digest != capacity.current_snapshot_ledger_digest:
        raise DistributionCapacityReservationV1Error("commitment state / current ledger digest mismatch")
    if state.current_snapshot_ledger_sequence != capacity.current_snapshot_sequence:
        raise DistributionCapacityReservationV1Error("commitment state / current ledger sequence mismatch")
    if state.reporting_currency != capacity.reporting_currency:
        raise DistributionCapacityReservationV1Error("commitment state / current capacity currency mismatch")
    active_currencies = {item.distribution_currency for item in values if item.outstanding_amount > ZERO}
    if active_currencies and active_currencies != {capacity.reporting_currency}:
        raise DistributionCapacityReservationV1Error("outstanding reservation currency mismatch")
    outstanding = sum((item.outstanding_amount for item in values), ZERO)
    expected_blockers = set()
    if capacity.status != "CAPACITY_AVAILABLE" or capacity.final_available_capacity <= ZERO:
        expected_blockers.add("CURRENT_AVAILABLE_CAPACITY_NO_ACTION")
    if outstanding > capacity.final_available_capacity:
        expected_blockers.add("OUTSTANDING_COMMITMENTS_EXCEED_CURRENT_CAPACITY")
    expected_remaining = max(ZERO, capacity.final_available_capacity - outstanding)
    if state.current_available_capacity != capacity.final_available_capacity:
        raise DistributionCapacityReservationV1Error("commitment state current capacity amount mismatch")
    if state.outstanding_commitments != outstanding:
        raise DistributionCapacityReservationV1Error("commitment state outstanding amount mismatch")
    if state.remaining_authorizable_capacity != expected_remaining:
        raise DistributionCapacityReservationV1Error("commitment state remaining capacity mismatch")
    if set(state.blockers) != expected_blockers:
        raise DistributionCapacityReservationV1Error("commitment state blocker set mismatch")
    if set(state.reservation_latest_digests) != {item.digest for item in values}:
        raise DistributionCapacityReservationV1Error("commitment state latest reservation digest set mismatch")
    return True


def _canonical_distribution_entry_amount(
    ledger: ReportingLedger,
    *,
    entry_digest: str,
    reservation: DistributionCapacityReservationV1,
) -> Decimal:
    matches = [entry for entry in ledger.entries_since(0) if entry.digest == entry_digest]
    if len(matches) != 1:
        raise DistributionCapacityReservationV1Error("accounting entry is missing or non-unique in current ReportingLedger")
    entry = matches[0]
    if entry.flow_type != FlowType.EXTERNAL_CAPITAL:
        raise DistributionCapacityReservationV1Error("reservation accounting entry must be EXTERNAL_CAPITAL")
    if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION":
        raise DistributionCapacityReservationV1Error("reservation accounting entry is not OWNER_DISTRIBUTION")
    if entry.metadata.get("affected_period_id") != reservation.affected_period_id:
        raise DistributionCapacityReservationV1Error("reservation accounting affected period mismatch")
    if entry.metadata.get("distribution_plan_digest") != reservation.plan_digest:
        raise DistributionCapacityReservationV1Error("reservation accounting plan digest mismatch")
    if entry.metadata.get("distribution_utilization_digest") != reservation.utilization_digest:
        raise DistributionCapacityReservationV1Error("reservation accounting utilization digest mismatch")
    asset_lines = []
    equity_lines = []
    for line in entry.lines:
        spec = ledger.account(line.account_id)
        if spec.consolidation_class != ConsolidationClass.EXTERNAL:
            continue
        if spec.account_class == AccountClass.ASSET:
            asset_lines.append(line)
        elif spec.account_class == AccountClass.EQUITY:
            equity_lines.append(line)
    if len(entry.lines) != 2 or len(asset_lines) != 1 or len(equity_lines) != 1:
        raise DistributionCapacityReservationV1Error("reservation accounting entry must be canonical two-line asset/equity posting")
    asset = asset_lines[0]
    equity = equity_lines[0]
    if asset.debit != ZERO or equity.credit != ZERO or asset.credit <= ZERO or equity.debit != asset.credit:
        raise DistributionCapacityReservationV1Error("reservation accounting entry amount/direction mismatch")
    return asset.credit


def mark_distribution_reservation_accounted_canonical_v1(
    book: DistributionCommitmentBookV1,
    reservation_id: str,
    *,
    accounting_entry_digest: str,
    refreshed_capacity: DistributionAvailableCapacityV2,
    current_reporting_ledger: ReportingLedger,
    accounted_at: datetime,
):
    reservation = book.reservation(reservation_id)
    if reservation.status != "SETTLED_PENDING_ACCOUNTING":
        raise DistributionCapacityReservationV1Error("canonical accounting reconciliation requires SETTLED_PENDING_ACCOUNTING")
    if current_reporting_ledger.reporting_currency != refreshed_capacity.reporting_currency:
        raise DistributionCapacityReservationV1Error("current ReportingLedger / refreshed capacity currency mismatch")
    if current_reporting_ledger.sequence != refreshed_capacity.current_snapshot_sequence:
        raise DistributionCapacityReservationV1Error("current ReportingLedger / refreshed capacity sequence mismatch")
    if current_reporting_ledger.digest != refreshed_capacity.current_snapshot_ledger_digest:
        raise DistributionCapacityReservationV1Error("current ReportingLedger is not the ledger bound by refreshed capacity")
    amount = _canonical_distribution_entry_amount(
        current_reporting_ledger,
        entry_digest=accounting_entry_digest,
        reservation=reservation,
    )
    if amount != reservation.settled_amount:
        raise DistributionCapacityReservationV1Error("canonical accounting entry amount differs from settled reservation")
    return book.mark_accounted(
        reservation_id,
        accounting_entry_digest=accounting_entry_digest,
        accounted_amount=amount,
        refreshed_capacity=refreshed_capacity,
        accounted_at=accounted_at,
    )
