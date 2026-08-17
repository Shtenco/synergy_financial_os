from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .core import AccountingInvariantError


ZERO = Decimal("0")
ONE = Decimal("1")
EVIDENCE_RANK = {
    "SCENARIO": 0,
    "MODEL_ESTIMATE": 1,
    "OBSERVED_OPERATIONAL": 2,
    "EXTERNALLY_SETTLED": 3,
    "AUDITED": 4,
}
OBSERVED_STATUSES = frozenset({"OBSERVED_OPERATIONAL", "EXTERNALLY_SETTLED", "AUDITED"})


def _d(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_project_evidence_bundle(bundle: Mapping[str, Any]) -> str:
    if bundle.get("schema") != "project.evidence/v1":
        raise AccountingInvariantError("unsupported project evidence schema")
    project_id = str(bundle.get("project_id", "")).strip()
    if not project_id:
        raise AccountingInvariantError("project evidence project_id is required")
    digest_raw = bundle.get("digest")
    if not isinstance(digest_raw, str):
        raise AccountingInvariantError("project evidence bundle requires digest")
    digest = _hex64(digest_raw, "project evidence digest")
    payload = dict(bundle)
    payload.pop("digest", None)
    expected = _canonical_digest(payload)
    if digest != expected:
        raise AccountingInvariantError(
            f"project evidence digest mismatch: expected={expected} got={digest}"
        )
    return digest


def project_proposal_digest(proposal: Mapping[str, Any]) -> str:
    if proposal.get("schema") != "project.proposal/v1":
        raise AccountingInvariantError("unsupported project proposal schema")
    return _canonical_digest(dict(proposal))


@dataclass(frozen=True)
class ProjectMoneyTranslation:
    source_asset: str
    reporting_currency: str
    reporting_units_per_source_unit: Decimal
    translation_evidence_digest: str | None = None

    def __post_init__(self) -> None:
        source = self.source_asset.upper().strip()
        reporting = self.reporting_currency.upper().strip()
        rate = _d(self.reporting_units_per_source_unit)
        if not source or not reporting:
            raise AccountingInvariantError("source_asset and reporting_currency are required")
        if rate <= ZERO:
            raise AccountingInvariantError(
                "reporting_units_per_source_unit must be strictly positive"
            )
        evidence = self.translation_evidence_digest
        if source == reporting:
            if rate != ONE:
                raise AccountingInvariantError("same-currency project translation rate must be 1")
        elif evidence is None:
            raise AccountingInvariantError(
                "cross-currency project translation requires evidence digest"
            )
        if evidence is not None:
            evidence = _hex64(evidence, "translation_evidence_digest")
        object.__setattr__(self, "source_asset", source)
        object.__setattr__(self, "reporting_currency", reporting)
        object.__setattr__(self, "reporting_units_per_source_unit", rate)
        object.__setattr__(self, "translation_evidence_digest", evidence)


def _translate_money_items(
    items: Iterable[Mapping[str, Any]],
    *,
    reporting_currency: str,
    translations: Mapping[str, ProjectMoneyTranslation],
) -> Decimal:
    reporting = reporting_currency.upper().strip()
    total = ZERO
    for item in items:
        asset = str(item.get("asset", "")).upper().strip()
        amount = _d(item.get("amount", "-1"))
        if not asset or amount < ZERO:
            raise AccountingInvariantError("project money item requires asset and non-negative amount")
        if asset == reporting:
            rate = ONE
        else:
            try:
                translation = translations[asset]
            except KeyError as exc:
                raise AccountingInvariantError(
                    f"missing project translation for {asset}->{reporting}"
                ) from exc
            if translation.source_asset != asset or translation.reporting_currency != reporting:
                raise AccountingInvariantError(
                    f"project translation does not match {asset}->{reporting}"
                )
            rate = translation.reporting_units_per_source_unit
        total += amount * rate
    return total


@dataclass(frozen=True)
class ProjectScreeningPolicy:
    policy_id: str
    minimum_evidence_status: str = "MODEL_ESTIMATE"
    maximum_risk_score: Decimal = Decimal("0.50")
    minimum_private_to_requested_ratio: Decimal = Decimal("0")
    minimum_first_loss_to_requested_ratio: Decimal = Decimal("0")
    minimum_foreign_fx_hedged_fraction: Decimal = Decimal("0")
    maximum_maturity_weeks: int | None = None

    def __post_init__(self) -> None:
        policy_id = self.policy_id.strip()
        evidence = self.minimum_evidence_status.upper().strip()
        max_risk = _d(self.maximum_risk_score)
        private_ratio = _d(self.minimum_private_to_requested_ratio)
        first_loss_ratio = _d(self.minimum_first_loss_to_requested_ratio)
        hedge = _d(self.minimum_foreign_fx_hedged_fraction)
        if not policy_id:
            raise AccountingInvariantError("project screening policy_id is required")
        if evidence not in EVIDENCE_RANK:
            raise AccountingInvariantError(f"unsupported minimum evidence status: {evidence}")
        if not ZERO <= max_risk <= ONE:
            raise AccountingInvariantError("maximum_risk_score must be between 0 and 1")
        if private_ratio < ZERO or first_loss_ratio < ZERO:
            raise AccountingInvariantError("project capital ratios must be non-negative")
        if not ZERO <= hedge <= ONE:
            raise AccountingInvariantError(
                "minimum_foreign_fx_hedged_fraction must be between 0 and 1"
            )
        if self.maximum_maturity_weeks is not None and self.maximum_maturity_weeks < 1:
            raise AccountingInvariantError("maximum_maturity_weeks must be positive")
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "minimum_evidence_status", evidence)
        object.__setattr__(self, "maximum_risk_score", max_risk)
        object.__setattr__(self, "minimum_private_to_requested_ratio", private_ratio)
        object.__setattr__(self, "minimum_first_loss_to_requested_ratio", first_loss_ratio)
        object.__setattr__(self, "minimum_foreign_fx_hedged_fraction", hedge)


@dataclass(frozen=True)
class ProjectScreeningResult:
    project_id: str
    proposal_digest: str
    evidence_bundle_digest: str | None
    policy_id: str
    reporting_currency: str
    requested_funding: Decimal
    private_capital: Decimal
    first_loss_capital: Decimal
    private_to_requested_ratio: Decimal
    first_loss_to_requested_ratio: Decimal
    evidence_status: str
    risk_score: Decimal | None
    maturity_weeks: int
    status: str
    blockers: tuple[str, ...]

    @property
    def reviewable(self) -> bool:
        return self.status == "REVIEWABLE"


def screen_project_for_financial_review(
    proposal: Mapping[str, Any],
    policy: ProjectScreeningPolicy,
    *,
    reporting_currency: str,
    translations: Mapping[str, ProjectMoneyTranslation] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
) -> ProjectScreeningResult:
    """Deterministically screen a project; never authorize funding itself.

    `REVIEWABLE` means the proposal cleared this narrow pre-underwriting gate.
    It is not credit approval, QE authorization, investment advice or a promise
    of funding. Any blocker returns explicit `NO_ACTION`.
    """

    if proposal.get("schema") != "project.proposal/v1":
        raise AccountingInvariantError("unsupported project proposal schema")
    project_id = str(proposal.get("project_id", "")).strip()
    if not project_id:
        raise AccountingInvariantError("project_id is required")
    reporting = reporting_currency.upper().strip()
    if not reporting:
        raise AccountingInvariantError("reporting_currency is required")

    translation_map = {
        key.upper().strip(): value for key, value in dict(translations or {}).items()
    }
    requested = _translate_money_items(
        proposal.get("requested_funding", []),
        reporting_currency=reporting,
        translations=translation_map,
    )
    if requested <= ZERO:
        raise AccountingInvariantError("requested funding must be strictly positive")
    private = _translate_money_items(
        proposal.get("private_capital", []),
        reporting_currency=reporting,
        translations=translation_map,
    )
    first_loss = _translate_money_items(
        proposal.get("first_loss_capital", []),
        reporting_currency=reporting,
        translations=translation_map,
    )

    evidence_status = str(proposal.get("evidence_status", "")).upper().strip()
    if evidence_status not in EVIDENCE_RANK:
        raise AccountingInvariantError(f"unsupported project evidence status: {evidence_status}")
    maturity_weeks = proposal.get("maturity_weeks")
    if not isinstance(maturity_weeks, int) or maturity_weeks < 1:
        raise AccountingInvariantError("maturity_weeks must be a positive integer")
    risk_raw = proposal.get("risk_score")
    risk_score = None if risk_raw is None else _d(risk_raw)
    if risk_score is not None and not ZERO <= risk_score <= ONE:
        raise AccountingInvariantError("project risk_score must be between 0 and 1")

    proposal_evidence_digest = proposal.get("evidence_bundle_digest")
    if proposal_evidence_digest is not None:
        proposal_evidence_digest = _hex64(
            str(proposal_evidence_digest),
            "proposal evidence_bundle_digest",
        )
    if evidence_status in OBSERVED_STATUSES and proposal_evidence_digest is None:
        raise AccountingInvariantError(
            f"{evidence_status} proposal requires evidence_bundle_digest"
        )

    verified_bundle_digest: str | None = None
    if evidence_bundle is not None:
        verified_bundle_digest = verify_project_evidence_bundle(evidence_bundle)
        if str(evidence_bundle.get("project_id", "")).strip() != project_id:
            raise AccountingInvariantError("project evidence bundle belongs to another project")
        if proposal_evidence_digest is None:
            raise AccountingInvariantError(
                "evidence bundle supplied but proposal does not bind its digest"
            )
        if verified_bundle_digest != proposal_evidence_digest:
            raise AccountingInvariantError(
                "project proposal evidence_bundle_digest does not match supplied bundle"
            )

    blockers: list[str] = []
    if EVIDENCE_RANK[evidence_status] < EVIDENCE_RANK[policy.minimum_evidence_status]:
        blockers.append(
            f"EVIDENCE_BELOW_POLICY:{evidence_status}<{policy.minimum_evidence_status}"
        )
    if risk_score is None:
        blockers.append("RISK_SCORE_MISSING")
    elif risk_score > policy.maximum_risk_score:
        blockers.append("RISK_SCORE_ABOVE_POLICY")
    if (
        policy.maximum_maturity_weeks is not None
        and maturity_weeks > policy.maximum_maturity_weeks
    ):
        blockers.append("MATURITY_ABOVE_POLICY")

    private_ratio = private / requested
    first_loss_ratio = first_loss / requested
    if private_ratio < policy.minimum_private_to_requested_ratio:
        blockers.append("PRIVATE_MATCH_BELOW_POLICY")
    if first_loss_ratio < policy.minimum_first_loss_to_requested_ratio:
        blockers.append("FIRST_LOSS_BELOW_POLICY")

    for exposure in proposal.get("fx_exposures", []):
        asset = str(exposure.get("asset", "")).upper().strip()
        hedged_fraction = _d(exposure.get("hedged_fraction", "-1"))
        if not ZERO <= hedged_fraction <= ONE:
            raise AccountingInvariantError("FX exposure hedged_fraction must be 0..1")
        if asset and asset != reporting and hedged_fraction < policy.minimum_foreign_fx_hedged_fraction:
            blockers.append(f"FX_HEDGE_BELOW_POLICY:{asset}")

    unique_blockers = tuple(sorted(set(blockers)))
    return ProjectScreeningResult(
        project_id=project_id,
        proposal_digest=project_proposal_digest(proposal),
        evidence_bundle_digest=verified_bundle_digest or proposal_evidence_digest,
        policy_id=policy.policy_id,
        reporting_currency=reporting,
        requested_funding=requested,
        private_capital=private,
        first_loss_capital=first_loss,
        private_to_requested_ratio=private_ratio,
        first_loss_to_requested_ratio=first_loss_ratio,
        evidence_status=evidence_status,
        risk_score=risk_score,
        maturity_weeks=maturity_weeks,
        status="NO_ACTION" if unique_blockers else "REVIEWABLE",
        blockers=unique_blockers,
    )
