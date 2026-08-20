from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_capacity_reservation_contract_v1 import (
    verify_distribution_capacity_reservation_payload_v1,
    verify_distribution_commitment_state_payload_v1,
    verify_reservation_chain_v1,
)
from sinergy_financial_os.distribution_capacity_reservation_v1 import (
    DistributionCapacityReservationV1,
    DistributionCapacityReservationV1Error,
    DistributionCommitmentStateV1,
)


ROOT = Path(__file__).resolve().parents[1]
RESERVATION_SCHEMA = json.loads((ROOT / "schemas/distribution_capacity_reservation_v1.schema.json").read_text(encoding="utf-8"))
STATE_SCHEMA = json.loads((ROOT / "schemas/distribution_commitment_state_v1.schema.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 8, 21, 3, 0, tzinfo=UTC)


def active() -> DistributionCapacityReservationV1:
    return DistributionCapacityReservationV1(
        reservation_id="reservation-contract",
        plan_digest="10" * 32,
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity_basis_digest="11" * 32,
        capacity_basis_snapshot_digest="12" * 32,
        capacity_basis_ledger_digest="13" * 32,
        capacity_basis_ledger_sequence=7,
        reserved_amount=Decimal("5"),
        settled_amount=Decimal("0"),
        outstanding_amount=Decimal("5"),
        status="ACTIVE",
        version=1,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def state(reservation: DistributionCapacityReservationV1) -> DistributionCommitmentStateV1:
    return DistributionCommitmentStateV1(
        state_id="commitment-state-contract",
        state_version=1,
        previous_state_digest=None,
        reporting_currency="USD",
        current_available_capacity_digest="20" * 32,
        current_snapshot_digest="21" * 32,
        current_snapshot_ledger_digest="13" * 32,
        current_snapshot_ledger_sequence=7,
        current_available_capacity=Decimal("8"),
        outstanding_commitments=Decimal("5"),
        remaining_authorizable_capacity=Decimal("3"),
        reservation_latest_digests=(reservation.digest,),
        blockers=(),
        status="AUTHORIZATION_CAPACITY_AVAILABLE",
        generated_at=NOW,
    )


def test_reservation_and_commitment_state_round_trip_schema_and_runtime() -> None:
    reservation = active()
    commitment = state(reservation)
    jsonschema.Draft202012Validator(RESERVATION_SCHEMA).validate(reservation.to_dict())
    jsonschema.Draft202012Validator(STATE_SCHEMA).validate(commitment.to_dict())
    assert verify_distribution_capacity_reservation_payload_v1(reservation.to_dict()).digest == reservation.digest
    assert verify_distribution_commitment_state_payload_v1(commitment.to_dict()).digest == commitment.digest


def test_fresh_hash_cannot_invent_more_remaining_authorizable_capacity() -> None:
    payload = state(active()).to_dict()
    payload["remaining_authorizable_capacity"] = "8"
    body = dict(payload)
    body.pop("digest")
    payload["digest"] = canonical_json_digest(body)
    jsonschema.Draft202012Validator(STATE_SCHEMA).validate(payload)
    with pytest.raises(DistributionCapacityReservationV1Error, match="remaining authorizable capacity mismatch"):
        verify_distribution_commitment_state_payload_v1(payload)


def test_valid_individual_objects_cannot_skip_reservation_lifecycle() -> None:
    first = active()
    illegal_accounted = DistributionCapacityReservationV1(
        reservation_id=first.reservation_id,
        plan_digest=first.plan_digest,
        affected_period_id=first.affected_period_id,
        distribution_currency=first.distribution_currency,
        capacity_basis_digest=first.capacity_basis_digest,
        capacity_basis_snapshot_digest=first.capacity_basis_snapshot_digest,
        capacity_basis_ledger_digest=first.capacity_basis_ledger_digest,
        capacity_basis_ledger_sequence=first.capacity_basis_ledger_sequence,
        reserved_amount=first.reserved_amount,
        settled_amount=Decimal("5"),
        outstanding_amount=Decimal("0"),
        status="ACCOUNTED",
        version=2,
        previous_reservation_digest=first.digest,
        attempt_digest="30" * 32,
        utilization_digest="31" * 32,
        accounting_entry_digest="32" * 32,
        created_at=first.created_at,
        updated_at=NOW + timedelta(minutes=10),
        expires_at=first.expires_at,
    )
    jsonschema.Draft202012Validator(RESERVATION_SCHEMA).validate(illegal_accounted.to_dict())
    assert verify_distribution_capacity_reservation_payload_v1(illegal_accounted.to_dict()).digest == illegal_accounted.digest
    with pytest.raises(DistributionCapacityReservationV1Error, match="invalid reservation transition"):
        verify_reservation_chain_v1((first, illegal_accounted))
