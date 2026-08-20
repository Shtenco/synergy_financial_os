from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_available_capacity_v2 import DistributionAvailableCapacityV2
from .numeric import canonical_decimal_text, finite_decimal


RESERVATION_SCHEMA = "distribution.capacity-reservation/v1"
STATE_SCHEMA = "distribution.commitment-state/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
OPEN_STATUSES = frozenset({"ACTIVE", "ATTEMPTED", "SETTLED_PENDING_ACCOUNTING"})
TERMINAL_STATUSES = frozenset({"ACCOUNTED", "RELEASED_TERMINAL_FAILED", "RELEASED_EXPIRED"})
ALL_STATUSES = OPEN_STATUSES | TERMINAL_STATUSES
UTILIZATION_STATUSES = frozenset({
    "FULLY_SETTLED",
    "PARTIALLY_SETTLED_REQUIRES_NEW_PLAN",
    "FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION",
})


class DistributionCapacityReservationV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionCapacityReservationV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionCapacityReservationV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionCapacityReservationV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _amount(value: Any, field_name: str, *, positive: bool = False) -> Decimal:
    result = finite_decimal(value, field_name)
    if result < ZERO or (positive and result <= ZERO):
        raise DistributionCapacityReservationV1Error(
            f"{field_name} must be {'strictly positive' if positive else 'non-negative'}"
        )
    return result


@dataclass(frozen=True)
class DistributionCapacityReservationV1:
    reservation_id: str
    plan_digest: str
    affected_period_id: str
    distribution_currency: str
    capacity_basis_digest: str
    capacity_basis_snapshot_digest: str
    capacity_basis_ledger_digest: str
    capacity_basis_ledger_sequence: int
    reserved_amount: Decimal
    settled_amount: Decimal
    outstanding_amount: Decimal
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    previous_reservation_digest: str | None = None
    attempt_digest: str | None = None
    utilization_digest: str | None = None
    accounting_entry_digest: str | None = None
    authority: str = "FINANCIAL_OS_DISTRIBUTION_CAPACITY_RESERVATION"
    accounting_authority: str = "COMMITMENT_ONLY"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_CAPACITY_RESERVATION":
            raise DistributionCapacityReservationV1Error("reservation authority mismatch")
        if self.accounting_authority != "COMMITMENT_ONLY":
            raise DistributionCapacityReservationV1Error("reservation is commitment-only, not accounting")
        if any(value != "NONE" for value in (self.payment_authority, self.execution_authority, self.ai_authority)):
            raise DistributionCapacityReservationV1Error("reservation cannot pay, execute or delegate to AI")
        object.__setattr__(self, "reservation_id", _text(self.reservation_id, "reservation_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        for name in ("plan_digest", "capacity_basis_digest", "capacity_basis_snapshot_digest", "capacity_basis_ledger_digest"):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        for name in ("previous_reservation_digest", "attempt_digest", "utilization_digest", "accounting_entry_digest"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _hex64(value, name, nullable=True))
        if isinstance(self.capacity_basis_ledger_sequence, bool) or not isinstance(self.capacity_basis_ledger_sequence, int) or self.capacity_basis_ledger_sequence < 1:
            raise DistributionCapacityReservationV1Error("capacity_basis_ledger_sequence must be positive integer")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DistributionCapacityReservationV1Error("reservation version must be positive integer")
        reserved = _amount(self.reserved_amount, "reserved_amount", positive=True)
        settled = _amount(self.settled_amount, "settled_amount")
        outstanding = _amount(self.outstanding_amount, "outstanding_amount")
        if settled > reserved or outstanding > reserved:
            raise DistributionCapacityReservationV1Error("settled/outstanding amount exceeds reserved amount")
        object.__setattr__(self, "reserved_amount", reserved)
        object.__setattr__(self, "settled_amount", settled)
        object.__setattr__(self, "outstanding_amount", outstanding)
        status = _text(self.status, "status").upper()
        if status not in ALL_STATUSES:
            raise DistributionCapacityReservationV1Error("unsupported reservation status")
        object.__setattr__(self, "status", status)
        created = _utc(self.created_at, "created_at")
        updated = _utc(self.updated_at, "updated_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= created or updated < created:
            raise DistributionCapacityReservationV1Error("invalid reservation time ordering")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "expires_at", expires)
        if self.version == 1 and self.previous_reservation_digest is not None:
            raise DistributionCapacityReservationV1Error("reservation version 1 cannot have previous digest")
        if self.version > 1 and self.previous_reservation_digest is None:
            raise DistributionCapacityReservationV1Error("reservation version >1 requires previous digest")
        if status == "ACTIVE":
            if self.version != 1 or outstanding != reserved or settled != ZERO:
                raise DistributionCapacityReservationV1Error("ACTIVE reservation must start fully outstanding")
            if any(value is not None for value in (self.attempt_digest, self.utilization_digest, self.accounting_entry_digest)):
                raise DistributionCapacityReservationV1Error("ACTIVE reservation cannot claim downstream usage")
        elif status == "ATTEMPTED":
            if self.attempt_digest is None or self.utilization_digest is not None or self.accounting_entry_digest is not None:
                raise DistributionCapacityReservationV1Error("ATTEMPTED reservation requires attempt only")
            if outstanding != reserved or settled != ZERO:
                raise DistributionCapacityReservationV1Error("ATTEMPTED reservation remains fully outstanding")
        elif status == "SETTLED_PENDING_ACCOUNTING":
            if self.attempt_digest is None or self.utilization_digest is None or self.accounting_entry_digest is not None:
                raise DistributionCapacityReservationV1Error("pending-accounting reservation requires attempt+utilization")
            if settled <= ZERO or outstanding != settled:
                raise DistributionCapacityReservationV1Error("pending-accounting outstanding must equal settled amount")
        elif status == "ACCOUNTED":
            if self.attempt_digest is None or self.utilization_digest is None or self.accounting_entry_digest is None:
                raise DistributionCapacityReservationV1Error("ACCOUNTED reservation requires attempt+utilization+entry")
            if settled <= ZERO or outstanding != ZERO:
                raise DistributionCapacityReservationV1Error("ACCOUNTED reservation must have zero outstanding")
        elif status == "RELEASED_TERMINAL_FAILED":
            if self.attempt_digest is None or self.utilization_digest is None or self.accounting_entry_digest is not None:
                raise DistributionCapacityReservationV1Error("terminal-failed release requires attempt+utilization")
            if settled != ZERO or outstanding != ZERO:
                raise DistributionCapacityReservationV1Error("terminal-failed release must settle/outstand zero")
        elif status == "RELEASED_EXPIRED":
            if any(value is not None for value in (self.attempt_digest, self.utilization_digest, self.accounting_entry_digest)):
                raise DistributionCapacityReservationV1Error("expired unattempted reservation cannot claim downstream usage")
            if settled != ZERO or outstanding != ZERO:
                raise DistributionCapacityReservationV1Error("expired reservation must settle/outstand zero")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": RESERVATION_SCHEMA,
            "reservation_id": self.reservation_id,
            "plan_digest": self.plan_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "capacity_basis_digest": self.capacity_basis_digest,
            "capacity_basis_snapshot_digest": self.capacity_basis_snapshot_digest,
            "capacity_basis_ledger_digest": self.capacity_basis_ledger_digest,
            "capacity_basis_ledger_sequence": self.capacity_basis_ledger_sequence,
            "reserved_amount": canonical_decimal_text(self.reserved_amount),
            "settled_amount": canonical_decimal_text(self.settled_amount),
            "outstanding_amount": canonical_decimal_text(self.outstanding_amount),
            "status": self.status,
            "version": self.version,
            "previous_reservation_digest": self.previous_reservation_digest,
            "attempt_digest": self.attempt_digest,
            "utilization_digest": self.utilization_digest,
            "accounting_entry_digest": self.accounting_entry_digest,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "accounting_authority": self.accounting_authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


@dataclass(frozen=True)
class DistributionCommitmentStateV1:
    state_id: str
    state_version: int
    previous_state_digest: str | None
    reporting_currency: str
    current_available_capacity_digest: str
    current_snapshot_digest: str
    current_snapshot_ledger_digest: str
    current_snapshot_ledger_sequence: int
    current_available_capacity: Decimal
    outstanding_commitments: Decimal
    remaining_authorizable_capacity: Decimal
    reservation_latest_digests: tuple[str, ...]
    generated_at: datetime
    blockers: tuple[str, ...] = ()
    status: str = "AUTHORIZATION_CAPACITY_AVAILABLE"
    authority: str = "FINANCIAL_OS_DISTRIBUTION_COMMITMENT_STATE"
    accounting_authority: str = "COMMITMENT_ONLY"
    authorization_authority: str = "REFERENCE_ONLY"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_COMMITMENT_STATE":
            raise DistributionCapacityReservationV1Error("commitment state authority mismatch")
        if self.accounting_authority != "COMMITMENT_ONLY" or self.authorization_authority != "REFERENCE_ONLY":
            raise DistributionCapacityReservationV1Error("commitment state authority boundary mismatch")
        if self.payment_authority != "NONE" or self.execution_authority != "NONE":
            raise DistributionCapacityReservationV1Error("commitment state cannot pay or execute")
        object.__setattr__(self, "state_id", _text(self.state_id, "state_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        if isinstance(self.state_version, bool) or not isinstance(self.state_version, int) or self.state_version < 1:
            raise DistributionCapacityReservationV1Error("commitment state version must be positive integer")
        if self.state_version == 1 and self.previous_state_digest is not None:
            raise DistributionCapacityReservationV1Error("state version 1 cannot have previous digest")
        if self.state_version > 1 and self.previous_state_digest is None:
            raise DistributionCapacityReservationV1Error("state version >1 requires previous digest")
        if self.previous_state_digest is not None:
            object.__setattr__(self, "previous_state_digest", _hex64(self.previous_state_digest, "previous_state_digest", nullable=True))
        for name in ("current_available_capacity_digest", "current_snapshot_digest", "current_snapshot_ledger_digest"):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        if isinstance(self.current_snapshot_ledger_sequence, bool) or not isinstance(self.current_snapshot_ledger_sequence, int) or self.current_snapshot_ledger_sequence < 1:
            raise DistributionCapacityReservationV1Error("current snapshot ledger sequence must be positive integer")
        capacity = _amount(self.current_available_capacity, "current_available_capacity")
        outstanding = _amount(self.outstanding_commitments, "outstanding_commitments")
        remaining = _amount(self.remaining_authorizable_capacity, "remaining_authorizable_capacity")
        expected_remaining = max(ZERO, capacity - outstanding)
        if remaining != expected_remaining:
            raise DistributionCapacityReservationV1Error("remaining authorizable capacity mismatch")
        object.__setattr__(self, "current_available_capacity", capacity)
        object.__setattr__(self, "outstanding_commitments", outstanding)
        object.__setattr__(self, "remaining_authorizable_capacity", remaining)
        digests = tuple(sorted(_hex64(item, "reservation_latest_digest") for item in self.reservation_latest_digests))
        if len(digests) != len(set(digests)):
            raise DistributionCapacityReservationV1Error("reservation latest digests must be unique")
        object.__setattr__(self, "reservation_latest_digests", digests)
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        if outstanding > capacity and "OUTSTANDING_COMMITMENTS_EXCEED_CURRENT_CAPACITY" not in blockers:
            raise DistributionCapacityReservationV1Error("overcommitted state must declare blocker")
        object.__setattr__(self, "blockers", blockers)
        expected_status = "AUTHORIZATION_CAPACITY_AVAILABLE" if remaining > ZERO and not blockers else "NO_ACTION"
        if self.status != expected_status:
            raise DistributionCapacityReservationV1Error("commitment state status mismatch")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": STATE_SCHEMA,
            "state_id": self.state_id,
            "state_version": self.state_version,
            "previous_state_digest": self.previous_state_digest,
            "reporting_currency": self.reporting_currency,
            "current_available_capacity_digest": self.current_available_capacity_digest,
            "current_snapshot_digest": self.current_snapshot_digest,
            "current_snapshot_ledger_digest": self.current_snapshot_ledger_digest,
            "current_snapshot_ledger_sequence": self.current_snapshot_ledger_sequence,
            "current_available_capacity": canonical_decimal_text(self.current_available_capacity),
            "outstanding_commitments": canonical_decimal_text(self.outstanding_commitments),
            "remaining_authorizable_capacity": canonical_decimal_text(self.remaining_authorizable_capacity),
            "reservation_latest_digests": list(self.reservation_latest_digests),
            "blockers": list(self.blockers),
            "status": self.status,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "accounting_authority": self.accounting_authority,
            "authorization_authority": self.authorization_authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


class DistributionCommitmentBookV1:
    """Reference serial commitment book; production must use durable CAS storage."""

    def __init__(self) -> None:
        self._latest: dict[str, DistributionCapacityReservationV1] = {}
        self._plan_reservation: dict[str, str] = {}
        self._state: DistributionCommitmentStateV1 | None = None

    @property
    def state(self) -> DistributionCommitmentStateV1 | None:
        return self._state

    def reservation(self, reservation_id: str) -> DistributionCapacityReservationV1:
        try:
            return self._latest[reservation_id]
        except KeyError as exc:
            raise DistributionCapacityReservationV1Error("unknown distribution reservation") from exc

    def _outstanding(self) -> Decimal:
        return sum((item.outstanding_amount for item in self._latest.values()), ZERO)

    def _assert_currency_domain(self, capacity: DistributionAvailableCapacityV2) -> None:
        currencies = {item.distribution_currency for item in self._latest.values() if item.outstanding_amount > ZERO}
        if currencies and currencies != {capacity.reporting_currency}:
            raise DistributionCapacityReservationV1Error("one commitment book cannot mix outstanding distribution currencies")

    def _next_state(self, capacity: DistributionAvailableCapacityV2, *, generated_at: datetime) -> DistributionCommitmentStateV1:
        self._assert_currency_domain(capacity)
        previous = self._state
        version = 1 if previous is None else previous.state_version + 1
        outstanding = self._outstanding()
        blockers = set()
        if capacity.status != "CAPACITY_AVAILABLE" or capacity.final_available_capacity <= ZERO:
            blockers.add("CURRENT_AVAILABLE_CAPACITY_NO_ACTION")
        if outstanding > capacity.final_available_capacity:
            blockers.add("OUTSTANDING_COMMITMENTS_EXCEED_CURRENT_CAPACITY")
        remaining = max(ZERO, capacity.final_available_capacity - outstanding)
        state = DistributionCommitmentStateV1(
            state_id=f"commitment-state-{version}",
            state_version=version,
            previous_state_digest=None if previous is None else previous.digest,
            reporting_currency=capacity.reporting_currency,
            current_available_capacity_digest=capacity.digest,
            current_snapshot_digest=capacity.current_financial_snapshot_digest,
            current_snapshot_ledger_digest=capacity.current_snapshot_ledger_digest,
            current_snapshot_ledger_sequence=capacity.current_snapshot_sequence,
            current_available_capacity=capacity.final_available_capacity,
            outstanding_commitments=outstanding,
            remaining_authorizable_capacity=remaining,
            reservation_latest_digests=tuple(item.digest for item in self._latest.values()),
            blockers=tuple(blockers),
            status="AUTHORIZATION_CAPACITY_AVAILABLE" if remaining > ZERO and not blockers else "NO_ACTION",
            generated_at=generated_at,
        )
        self._state = state
        return state

    def refresh_capacity(self, capacity: DistributionAvailableCapacityV2, *, generated_at: datetime) -> DistributionCommitmentStateV1:
        return self._next_state(capacity, generated_at=generated_at)

    def reserve(self, *, reservation_id: str, plan_digest: str, plan_amount: Decimal | int | str,
                affected_period_id: str, distribution_currency: str,
                capacity: DistributionAvailableCapacityV2, created_at: datetime,
                expires_at: datetime) -> tuple[DistributionCapacityReservationV1, DistributionCommitmentStateV1]:
        now = _utc(created_at, "created_at")
        expires = _utc(expires_at, "expires_at")
        if expires <= now:
            raise DistributionCapacityReservationV1Error("reservation expires_at must be later than created_at")
        reservation_key = _text(reservation_id, "reservation_id")
        plan = _hex64(plan_digest, "plan_digest")
        if reservation_key in self._latest:
            raise DistributionCapacityReservationV1Error("duplicate reservation_id")
        if plan in self._plan_reservation:
            raise DistributionCapacityReservationV1Error("distribution plan already has a reservation")
        if capacity.status != "CAPACITY_AVAILABLE" or capacity.final_available_capacity <= ZERO:
            raise DistributionCapacityReservationV1Error("current capacity is not reservable")
        if affected_period_id != capacity.affected_period_id:
            raise DistributionCapacityReservationV1Error("reservation affected period differs from capacity")
        if distribution_currency.upper().strip() != capacity.reporting_currency:
            raise DistributionCapacityReservationV1Error("reservation currency differs from capacity")
        if self._state is None or self._state.current_available_capacity_digest != capacity.digest:
            self._next_state(capacity, generated_at=now)
        state = self._state
        assert state is not None
        if state.blockers:
            raise DistributionCapacityReservationV1Error("current commitment state is not reservable")
        amount = _amount(plan_amount, "plan_amount", positive=True)
        if amount > state.remaining_authorizable_capacity:
            raise DistributionCapacityReservationV1Error("insufficient unreserved distribution authorization capacity")
        reservation = DistributionCapacityReservationV1(
            reservation_id=reservation_key,
            plan_digest=plan,
            affected_period_id=affected_period_id,
            distribution_currency=distribution_currency,
            capacity_basis_digest=capacity.digest,
            capacity_basis_snapshot_digest=capacity.current_financial_snapshot_digest,
            capacity_basis_ledger_digest=capacity.current_snapshot_ledger_digest,
            capacity_basis_ledger_sequence=capacity.current_snapshot_sequence,
            reserved_amount=amount,
            settled_amount=ZERO,
            outstanding_amount=amount,
            status="ACTIVE",
            version=1,
            created_at=now,
            updated_at=now,
            expires_at=expires,
        )
        self._latest[reservation_key] = reservation
        self._plan_reservation[plan] = reservation_key
        return reservation, self._next_state(capacity, generated_at=now)

    def _require_current_capacity(self, capacity: DistributionAvailableCapacityV2) -> DistributionCommitmentStateV1:
        if self._state is None or self._state.current_available_capacity_digest != capacity.digest:
            self._next_state(capacity, generated_at=capacity.generated_at)
        assert self._state is not None
        return self._state

    def mark_attempted(self, reservation_id: str, *, attempt_digest: str,
                       capacity: DistributionAvailableCapacityV2, attempted_at: datetime):
        current = self.reservation(reservation_id)
        now = _utc(attempted_at, "attempted_at")
        state = self._require_current_capacity(capacity)
        if current.status != "ACTIVE":
            raise DistributionCapacityReservationV1Error("only ACTIVE reservation can become ATTEMPTED")
        if now >= current.expires_at:
            raise DistributionCapacityReservationV1Error("expired reservation cannot be attempted")
        if state.blockers or state.outstanding_commitments > state.current_available_capacity:
            raise DistributionCapacityReservationV1Error("current commitment/capacity state blocks attempt")
        updated = replace(current, status="ATTEMPTED", version=current.version + 1,
                          previous_reservation_digest=current.digest,
                          attempt_digest=_hex64(attempt_digest, "attempt_digest"), updated_at=now)
        self._latest[current.reservation_id] = updated
        return updated, self._next_state(capacity, generated_at=now)

    def apply_terminal_utilization(self, reservation_id: str, *, utilization_digest: str,
                                   utilization_status: str, planned_total_amount: Decimal | int | str,
                                   settled_total_amount: Decimal | int | str,
                                   capacity: DistributionAvailableCapacityV2, finalized_at: datetime):
        current = self.reservation(reservation_id)
        if current.status != "ATTEMPTED":
            raise DistributionCapacityReservationV1Error("terminal utilization requires ATTEMPTED reservation")
        status = _text(utilization_status, "utilization_status").upper()
        if status not in UTILIZATION_STATUSES:
            raise DistributionCapacityReservationV1Error("unsupported distribution utilization status")
        planned = _amount(planned_total_amount, "planned_total_amount", positive=True)
        settled = _amount(settled_total_amount, "settled_total_amount")
        if planned != current.reserved_amount or settled > planned:
            raise DistributionCapacityReservationV1Error("utilization amount differs from reserved plan")
        if status == "FULLY_SETTLED" and settled != planned:
            raise DistributionCapacityReservationV1Error("FULLY_SETTLED must settle full reservation")
        if status == "PARTIALLY_SETTLED_REQUIRES_NEW_PLAN" and not (ZERO < settled < planned):
            raise DistributionCapacityReservationV1Error("partial utilization amount mismatch")
        if status == "FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION" and settled != ZERO:
            raise DistributionCapacityReservationV1Error("failed utilization must settle zero")
        now = _utc(finalized_at, "finalized_at")
        if now < current.updated_at:
            raise DistributionCapacityReservationV1Error("utilization cannot predate attempt")
        next_status = "SETTLED_PENDING_ACCOUNTING" if settled > ZERO else "RELEASED_TERMINAL_FAILED"
        updated = replace(current, status=next_status, version=current.version + 1,
                          previous_reservation_digest=current.digest,
                          utilization_digest=_hex64(utilization_digest, "utilization_digest"),
                          settled_amount=settled, outstanding_amount=settled, updated_at=now)
        self._latest[current.reservation_id] = updated
        return updated, self._next_state(capacity, generated_at=now)

    def mark_accounted(self, reservation_id: str, *, accounting_entry_digest: str,
                       accounted_amount: Decimal | int | str,
                       refreshed_capacity: DistributionAvailableCapacityV2,
                       accounted_at: datetime):
        current = self.reservation(reservation_id)
        if current.status != "SETTLED_PENDING_ACCOUNTING":
            raise DistributionCapacityReservationV1Error("only settled-pending reservation can become ACCOUNTED")
        amount = _amount(accounted_amount, "accounted_amount", positive=True)
        if amount != current.settled_amount or amount != current.outstanding_amount:
            raise DistributionCapacityReservationV1Error("accounted amount must equal exact settled outstanding reservation")
        if refreshed_capacity.current_snapshot_sequence <= current.capacity_basis_ledger_sequence:
            raise DistributionCapacityReservationV1Error("ACCOUNTED transition requires a refreshed closed ledger after payout posting")
        if refreshed_capacity.current_snapshot_ledger_digest == current.capacity_basis_ledger_digest:
            raise DistributionCapacityReservationV1Error("ACCOUNTED transition cannot reuse pre-payout ledger digest")
        now = _utc(accounted_at, "accounted_at")
        if now < current.updated_at:
            raise DistributionCapacityReservationV1Error("accounting cannot predate utilization")
        updated = replace(current, status="ACCOUNTED", version=current.version + 1,
                          previous_reservation_digest=current.digest,
                          accounting_entry_digest=_hex64(accounting_entry_digest, "accounting_entry_digest"),
                          outstanding_amount=ZERO, updated_at=now)
        self._latest[current.reservation_id] = updated
        return updated, self._next_state(refreshed_capacity, generated_at=now)

    def release_expired(self, reservation_id: str, *, capacity: DistributionAvailableCapacityV2,
                        released_at: datetime):
        current = self.reservation(reservation_id)
        now = _utc(released_at, "released_at")
        if current.status != "ACTIVE":
            raise DistributionCapacityReservationV1Error("only unattempted ACTIVE reservation can expire-release")
        if now < current.expires_at:
            raise DistributionCapacityReservationV1Error("reservation cannot release before expiry")
        updated = replace(current, status="RELEASED_EXPIRED", version=current.version + 1,
                          previous_reservation_digest=current.digest,
                          outstanding_amount=ZERO, updated_at=now)
        self._latest[current.reservation_id] = updated
        return updated, self._next_state(capacity, generated_at=now)
