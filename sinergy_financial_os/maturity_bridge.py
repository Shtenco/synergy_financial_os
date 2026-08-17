from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .core import AccountingInvariantError
from .snapshot import LiquidityHorizonState


ZERO = Decimal("0")
HORIZONS = (1, 4, 8)


def _d(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def verify_maturity_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Verify the Matrix `maturity.snapshot/v1` content digest."""

    if snapshot.get("schema") != "maturity.snapshot/v1":
        raise AccountingInvariantError("unsupported maturity snapshot schema")
    raw_digest = snapshot.get("digest")
    if not isinstance(raw_digest, str):
        raise AccountingInvariantError("maturity snapshot requires a digest")
    digest = _hex64(raw_digest, "maturity snapshot digest")
    payload = dict(snapshot)
    payload.pop("digest", None)
    expected = _canonical_digest(payload)
    if digest != expected:
        raise AccountingInvariantError(
            f"maturity snapshot digest mismatch: expected={expected} got={digest}"
        )
    return digest


def contractual_outflows_by_horizon(snapshot: Mapping[str, Any]) -> dict[int, Decimal]:
    """Return native-currency contractual outflows for 1/4/8 weeks.

    Outflow = immediately callable principal + cumulative non-callable maturity
    unlock by the horizon. Callable balances are intentionally excluded from the
    future cumulative schedule to prevent double counting.
    """

    verify_maturity_snapshot_digest(snapshot)
    callable_principal = _d(snapshot.get("immediately_callable_principal", "0"))
    if callable_principal < ZERO:
        raise AccountingInvariantError("immediately_callable_principal must be non-negative")

    buckets = snapshot.get("buckets")
    if not isinstance(buckets, list):
        raise AccountingInvariantError("maturity snapshot buckets must be a list")
    by_week: dict[int, Mapping[str, Any]] = {}
    for bucket in buckets:
        if not isinstance(bucket, Mapping):
            raise AccountingInvariantError("maturity bucket must be an object")
        week = bucket.get("week")
        if not isinstance(week, int) or week < 1 or week > 100:
            raise AccountingInvariantError("maturity bucket week must be 1..100")
        if week in by_week:
            raise AccountingInvariantError(f"duplicate maturity bucket week: {week}")
        by_week[week] = bucket

    outflows: dict[int, Decimal] = {}
    for horizon in HORIZONS:
        try:
            bucket = by_week[horizon]
        except KeyError as exc:
            raise AccountingInvariantError(
                f"maturity snapshot must contain bucket for {horizon} weeks"
            ) from exc
        cumulative = _d(bucket.get("cumulative_noncallable_unlock", "-1"))
        if cumulative < ZERO:
            raise AccountingInvariantError(
                "cumulative_noncallable_unlock must be non-negative"
            )
        outflows[horizon] = callable_principal + cumulative
    return outflows


@dataclass(frozen=True)
class MaturityTranslation:
    source_currency: str
    reporting_currency: str
    reporting_units_per_source_unit: Decimal
    translation_evidence_digest: str | None = None

    def __post_init__(self) -> None:
        source = self.source_currency.upper().strip()
        reporting = self.reporting_currency.upper().strip()
        rate = _d(self.reporting_units_per_source_unit)
        if not source or not reporting:
            raise AccountingInvariantError("source and reporting currencies are required")
        if rate <= ZERO:
            raise AccountingInvariantError(
                "reporting_units_per_source_unit must be strictly positive"
            )
        evidence = self.translation_evidence_digest
        if source != reporting and evidence is None:
            raise AccountingInvariantError(
                "cross-currency maturity translation requires an evidence digest"
            )
        if evidence is not None:
            evidence = _hex64(evidence, "translation_evidence_digest")
        if source == reporting and rate != Decimal("1"):
            raise AccountingInvariantError(
                "same-currency maturity translation rate must equal exactly 1"
            )
        object.__setattr__(self, "source_currency", source)
        object.__setattr__(self, "reporting_currency", reporting)
        object.__setattr__(self, "reporting_units_per_source_unit", rate)
        object.__setattr__(self, "translation_evidence_digest", evidence)


def translate_maturity_outflows(
    snapshot: Mapping[str, Any],
    translation: MaturityTranslation,
) -> dict[int, Decimal]:
    snapshot_currency = str(snapshot.get("currency", "")).upper().strip()
    if snapshot_currency != translation.source_currency:
        raise AccountingInvariantError(
            "maturity snapshot currency does not match translation source currency"
        )
    native = contractual_outflows_by_horizon(snapshot)
    return {
        horizon: amount * translation.reporting_units_per_source_unit
        for horizon, amount in native.items()
    }


def liquidity_horizon_states_from_maturity(
    snapshot: Mapping[str, Any],
    translation: MaturityTranslation,
    liquid_resources_by_horizon: Mapping[int, Decimal | int | str],
) -> tuple[LiquidityHorizonState, ...]:
    """Combine translated Matrix outflows with Financial OS liquid resources."""

    outflows = translate_maturity_outflows(snapshot, translation)
    states: list[LiquidityHorizonState] = []
    for horizon in HORIZONS:
        if horizon not in liquid_resources_by_horizon:
            raise AccountingInvariantError(
                f"missing liquid resources for {horizon}-week horizon"
            )
        states.append(
            LiquidityHorizonState(
                horizon_weeks=horizon,
                liquid_resources=_d(liquid_resources_by_horizon[horizon]),
                expected_net_outflows=outflows[horizon],
            )
        )
    return tuple(states)
