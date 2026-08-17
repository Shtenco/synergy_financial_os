from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .canonical_json import (
    MAX_SAFE_JSON_INTEGER,
    assert_canonical_json_profile,
    canonical_json_digest,
)
from .errors import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal
from .project_bridge import (
    ProjectMoneyTranslation,
    ProjectScreeningPolicy,
    ProjectScreeningResult,
    screen_project_for_financial_review,
)


ZERO = Decimal("0")
ONE = Decimal("1")


def _require_canonical_decimal_string(
    value: Any,
    field_name: str,
    *,
    nonnegative: bool = False,
    unit_interval: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise AccountingInvariantError(
            f"{field_name} must be a canonical decimal string in project.proposal/v2"
        )
    number = finite_decimal(value, field_name)
    expected = canonical_decimal_text(number, field_name)
    if value != expected:
        raise AccountingInvariantError(
            f"{field_name} is not canonical decimal text: expected {expected!r}, got {value!r}"
        )
    if nonnegative and number < ZERO:
        raise AccountingInvariantError(f"{field_name} must be non-negative")
    if unit_interval and not ZERO <= number <= ONE:
        raise AccountingInvariantError(f"{field_name} must be between 0 and 1")
    return number


def _require_money_array(
    items: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
) -> None:
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        raise AccountingInvariantError(f"{field_name} must be an array")
    if not allow_empty and not items:
        raise AccountingInvariantError(f"{field_name} must not be empty")
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise AccountingInvariantError(f"{field_name}[{index}] must be an object")
        if not str(item.get("asset", "")).strip():
            raise AccountingInvariantError(f"{field_name}[{index}].asset is required")
        _require_canonical_decimal_string(
            item.get("amount"),
            f"{field_name}[{index}].amount",
            nonnegative=True,
        )


def _validate_v2_decimal_fields(proposal: Mapping[str, Any]) -> None:
    _require_money_array(proposal.get("capex"), "capex", allow_empty=False)
    _require_money_array(
        proposal.get("requested_funding"),
        "requested_funding",
        allow_empty=False,
    )
    _require_money_array(proposal.get("private_capital"), "private_capital")
    _require_money_array(proposal.get("opex_annual"), "opex_annual")
    _require_money_array(proposal.get("first_loss_capital"), "first_loss_capital")

    cash_flows = proposal.get("expected_cash_flows")
    if not isinstance(cash_flows, Sequence) or isinstance(
        cash_flows,
        (str, bytes, bytearray),
    ):
        raise AccountingInvariantError("expected_cash_flows must be an array")
    for index, item in enumerate(cash_flows):
        if not isinstance(item, Mapping):
            raise AccountingInvariantError(
                f"expected_cash_flows[{index}] must be an object"
            )
        _require_canonical_decimal_string(
            item.get("amount"),
            f"expected_cash_flows[{index}].amount",
        )

    fx_exposures = proposal.get("fx_exposures")
    if not isinstance(fx_exposures, Sequence) or isinstance(
        fx_exposures,
        (str, bytes, bytearray),
    ):
        raise AccountingInvariantError("fx_exposures must be an array")
    for index, item in enumerate(fx_exposures):
        if not isinstance(item, Mapping):
            raise AccountingInvariantError(f"fx_exposures[{index}] must be an object")
        _require_canonical_decimal_string(
            item.get("amount"),
            f"fx_exposures[{index}].amount",
            nonnegative=True,
        )
        _require_canonical_decimal_string(
            item.get("hedged_fraction"),
            f"fx_exposures[{index}].hedged_fraction",
            unit_interval=True,
        )

    risk_score = proposal.get("risk_score")
    if risk_score is not None:
        _require_canonical_decimal_string(
            risk_score,
            "risk_score",
            unit_interval=True,
        )

    maturity_weeks = proposal.get("maturity_weeks")
    if (
        not isinstance(maturity_weeks, int)
        or isinstance(maturity_weeks, bool)
        or maturity_weeks < 1
        or maturity_weeks > MAX_SAFE_JSON_INTEGER
    ):
        raise AccountingInvariantError(
            "maturity_weeks must be a positive cross-language safe integer"
        )

    dependencies = proposal.get("dependencies")
    if not isinstance(dependencies, list):
        raise AccountingInvariantError("dependencies must be an array")
    if len(dependencies) != len(set(dependencies)):
        raise AccountingInvariantError("project.proposal/v2 dependencies must be unique")


def project_proposal_v2_digest(proposal: Mapping[str, Any]) -> str:
    if proposal.get("schema") != "project.proposal/v2":
        raise AccountingInvariantError("unsupported project proposal v2 schema")
    assert_canonical_json_profile(proposal)
    _validate_v2_decimal_fields(proposal)
    return canonical_json_digest(dict(proposal))


def screen_project_v2_for_financial_review(
    proposal: Mapping[str, Any],
    policy: ProjectScreeningPolicy,
    *,
    reporting_currency: str,
    translations: Mapping[str, ProjectMoneyTranslation] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
) -> ProjectScreeningResult:
    """Screen canonical project.proposal/v2 through the established economics gate.

    The established economic/evidence logic remains in the existing v1 bridge.
    This adapter adds v2 canonical-byte validation, reuses those rules on an
    internal compatibility view, then restores the digest binding to the exact
    original v2 proposal. It never authorizes funding or execution.
    """

    proposal_digest = project_proposal_v2_digest(proposal)
    compatibility_view = dict(proposal)
    compatibility_view["schema"] = "project.proposal/v1"

    result = screen_project_for_financial_review(
        compatibility_view,
        policy,
        reporting_currency=reporting_currency,
        translations=translations,
        evidence_bundle=evidence_bundle,
    )
    return replace(result, proposal_digest=proposal_digest)
