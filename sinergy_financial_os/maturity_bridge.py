from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .canonical_json import MAX_SAFE_JSON_INTEGER, canonical_json_digest
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal
from .snapshot import LiquidityHorizonState


ZERO = Decimal("0")
ONE = Decimal("1")
HORIZONS = (1, 4, 8)
LIQUIDITY_OUTFLOW_RULE = (
    "immediately_callable_principal + cumulative_noncallable_unlock"
)


def _d(value: Decimal | int | str, field_name: str = "value") -> Decimal:
    return finite_decimal(value, field_name)


def _canonical_digest(payload: Any) -> str:
    return canonical_json_digest(payload)


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def _require_canonical_nonnegative_decimal(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise AccountingInvariantError(f"{field_name} must be a canonical decimal string")
    amount = _d(value, field_name)
    if amount < ZERO:
        raise AccountingInvariantError(f"{field_name} must be non-negative")
    expected = canonical_decimal_text(amount, field_name)
    if value != expected:
        raise AccountingInvariantError(
            f"{field_name} is not canonical decimal text: expected {expected!r}, got {value!r}"
        )
    return amount


def _require_timezone_aware_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AccountingInvariantError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AccountingInvariantError(f"{field_name} must be ISO-8601 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AccountingInvariantError(f"{field_name} must be timezone-aware")
    return parsed


def _validate_maturity_snapshot_semantics(
    snapshot: Mapping[str, Any],
) -> dict[int, Mapping[str, Any]]:
    if snapshot.get("schema") != "maturity.snapshot/v1":
        raise AccountingInvariantError("unsupported maturity snapshot schema")

    _require_timezone_aware_datetime(snapshot.get("as_of"), "maturity snapshot as_of")

    as_of_week = snapshot.get("as_of_week")
    if (
        not isinstance(as_of_week, int)
        or isinstance(as_of_week, bool)
        or as_of_week < 0
        or as_of_week > MAX_SAFE_JSON_INTEGER
    ):
        raise AccountingInvariantError(
            "maturity snapshot as_of_week must be a non-negative safe integer"
        )

    currency = str(snapshot.get("currency", "")).upper().strip()
    if not currency:
        raise AccountingInvariantError("maturity snapshot currency is required")
    if snapshot.get("currency") != currency:
        raise AccountingInvariantError("maturity snapshot currency must be uppercase canonical text")

    total_open = _require_canonical_nonnegative_decimal(
        snapshot.get("total_open_principal"),
        "total_open_principal",
    )
    callable_principal = _require_canonical_nonnegative_decimal(
        snapshot.get("immediately_callable_principal"),
        "immediately_callable_principal",
    )
    if callable_principal > total_open:
        raise AccountingInvariantError(
            "immediately_callable_principal cannot exceed total_open_principal"
        )

    metadata = snapshot.get("metadata")
    if not isinstance(metadata, Mapping):
        raise AccountingInvariantError("maturity snapshot metadata must be an object")
    if set(metadata) != {"horizon_weeks", "liquidity_outflow_rule"}:
        raise AccountingInvariantError(
            "maturity snapshot metadata must contain exactly horizon_weeks and liquidity_outflow_rule"
        )
    horizon_weeks = metadata.get("horizon_weeks")
    if (
        not isinstance(horizon_weeks, int)
        or isinstance(horizon_weeks, bool)
        or horizon_weeks < 1
        or horizon_weeks > 100
    ):
        raise AccountingInvariantError("maturity horizon_weeks must be integer 1..100")
    if metadata.get("liquidity_outflow_rule") != LIQUIDITY_OUTFLOW_RULE:
        raise AccountingInvariantError("unsupported maturity liquidity_outflow_rule")

    buckets = snapshot.get("buckets")
    if not isinstance(buckets, list) or len(buckets) != horizon_weeks:
        raise AccountingInvariantError(
            "maturity snapshot bucket count must equal metadata.horizon_weeks"
        )

    by_week: dict[int, Mapping[str, Any]] = {}
    cumulative_contractual = ZERO
    cumulative_noncallable = ZERO
    previous_duration_eligible: Decimal | None = None

    for expected_week, bucket in enumerate(buckets, start=1):
        if not isinstance(bucket, Mapping):
            raise AccountingInvariantError("maturity bucket must be an object")
        expected_keys = {
            "week",
            "scheduled_unlock",
            "cumulative_unlock",
            "scheduled_noncallable_unlock",
            "cumulative_noncallable_unlock",
            "duration_eligible_principal",
        }
        if set(bucket) != expected_keys:
            raise AccountingInvariantError(
                f"maturity bucket {expected_week} has an invalid shape"
            )
        week = bucket.get("week")
        if week != expected_week:
            raise AccountingInvariantError(
                "maturity bucket weeks must be contiguous and ordered from 1"
            )

        scheduled = _require_canonical_nonnegative_decimal(
            bucket.get("scheduled_unlock"),
            f"buckets[{expected_week - 1}].scheduled_unlock",
        )
        cumulative = _require_canonical_nonnegative_decimal(
            bucket.get("cumulative_unlock"),
            f"buckets[{expected_week - 1}].cumulative_unlock",
        )
        scheduled_noncallable = _require_canonical_nonnegative_decimal(
            bucket.get("scheduled_noncallable_unlock"),
            f"buckets[{expected_week - 1}].scheduled_noncallable_unlock",
        )
        cumulative_noncallable_value = _require_canonical_nonnegative_decimal(
            bucket.get("cumulative_noncallable_unlock"),
            f"buckets[{expected_week - 1}].cumulative_noncallable_unlock",
        )
        duration_eligible = _require_canonical_nonnegative_decimal(
            bucket.get("duration_eligible_principal"),
            f"buckets[{expected_week - 1}].duration_eligible_principal",
        )

        if scheduled_noncallable > scheduled:
            raise AccountingInvariantError(
                "scheduled_noncallable_unlock cannot exceed scheduled_unlock"
            )

        cumulative_contractual += scheduled
        cumulative_noncallable += scheduled_noncallable
        if cumulative != cumulative_contractual:
            raise AccountingInvariantError(
                f"cumulative_unlock mismatch at week {expected_week}"
            )
        if cumulative_noncallable_value != cumulative_noncallable:
            raise AccountingInvariantError(
                f"cumulative_noncallable_unlock mismatch at week {expected_week}"
            )
        if cumulative_noncallable > cumulative_contractual:
            raise AccountingInvariantError(
                "cumulative_noncallable_unlock cannot exceed cumulative_unlock"
            )
        if cumulative_contractual > total_open:
            raise AccountingInvariantError(
                "cumulative contractual unlock cannot exceed total_open_principal"
            )
        if callable_principal + cumulative_noncallable > total_open:
            raise AccountingInvariantError(
                "callable plus cumulative non-callable outflow cannot exceed total_open_principal"
            )
        if duration_eligible > total_open:
            raise AccountingInvariantError(
                "duration_eligible_principal cannot exceed total_open_principal"
            )
        if previous_duration_eligible is not None and duration_eligible > previous_duration_eligible:
            raise AccountingInvariantError(
                "duration_eligible_principal must be non-increasing across longer maturities"
            )
        previous_duration_eligible = duration_eligible
        by_week[expected_week] = bucket

    return by_week


def verify_maturity_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Verify Matrix maturity content, schedule semantics and content digest."""

    _validate_maturity_snapshot_semantics(snapshot)
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
    callable_principal = _require_canonical_nonnegative_decimal(
        snapshot.get("immediately_callable_principal"),
        "immediately_callable_principal",
    )
    buckets = snapshot["buckets"]
    by_week = {bucket["week"]: bucket for bucket in buckets}

    outflows: dict[int, Decimal] = {}
    for horizon in HORIZONS:
        try:
            bucket = by_week[horizon]
        except KeyError as exc:
            raise AccountingInvariantError(
                f"maturity snapshot must contain bucket for {horizon} weeks"
            ) from exc
        cumulative = _require_canonical_nonnegative_decimal(
            bucket.get("cumulative_noncallable_unlock"),
            f"week {horizon} cumulative_noncallable_unlock",
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
        rate = _d(
            self.reporting_units_per_source_unit,
            "reporting_units_per_source_unit",
        )
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
        if source == reporting and rate != ONE:
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
        horizon: _d(
            amount * translation.reporting_units_per_source_unit,
            f"translated {horizon}-week maturity outflow",
        )
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
                liquid_resources=_d(
                    liquid_resources_by_horizon[horizon],
                    f"{horizon}-week liquid resources",
                ),
                expected_net_outflows=outflows[horizon],
            )
        )
    return tuple(states)
