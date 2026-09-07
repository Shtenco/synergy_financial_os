from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal


class FinancialContractError(ValueError):
    pass


@dataclass(frozen=True)
class ReconciledTradingResult:
    execution_intent_id: str
    settlement_contract_id: str
    realized_pnl: float
    hardnav_delta: float
    reconciliation_status: Literal["MATCHED", "EXCEPTION", "REVERSED"]

    def __post_init__(self) -> None:
        if self.reconciliation_status == "MATCHED" and abs(self.realized_pnl - self.hardnav_delta) > 1e-9:
            raise FinancialContractError("matched external trading result must reconcile realized_pnl to hardnav_delta")

    def as_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProjectUnderwritingDecision:
    project_id: str
    decision: Literal["APPROVE", "REJECT", "CONDITIONAL", "DEFER"]
    approved_capacity: float
    required_reserves: float
    underwriting_snapshot_ref: str
    conditions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.approved_capacity < 0 or self.required_reserves < 0:
            raise FinancialContractError("capacity and reserves must be non-negative")
        if self.decision == "REJECT" and self.approved_capacity != 0:
            raise FinancialContractError("rejected project cannot have approved capacity")

    def as_payload(self) -> dict:
        payload = asdict(self)
        payload["conditions"] = list(self.conditions)
        return payload


@dataclass(frozen=True)
class BudgetAccountingRecognition:
    authorization_id: str
    settlement_contract_id: str
    ledger_entry_ref: str
    recognition_status: Literal["RECOGNIZED", "EXCEPTION", "REVERSED"]
    economic_classification: str

    def __post_init__(self) -> None:
        if not self.ledger_entry_ref:
            raise FinancialContractError("ledger_entry_ref is required")

    def as_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EligibleAssetGrowthAttestation:
    """Canonical Financial OS input for real-asset-backed emission release.

    The attestation intentionally separates gross eligible asset growth from
    HardNAV and liabilities. Emission credit is the conservative minimum of
    positive HardNAV growth and eligible growth net of new liabilities.

    Internal marks and flash principal are audit fields only; they never enter
    the credited-growth calculation.
    """

    close_id: str
    close_sequence: int
    previous_hardnav: float
    current_hardnav: float
    previous_liabilities: float
    current_liabilities: float
    eligible_asset_gross_growth: float
    internal_mark_change: float
    flash_principal_inflow: float
    eligible_asset_classes: tuple[
        Literal["EXTERNAL_CASH", "SETTLED_RECEIVABLE", "VERIFIED_PRODUCTIVE_ASSET"], ...
    ] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.close_id:
            raise FinancialContractError("close_id is required")
        if self.close_sequence <= 0:
            raise FinancialContractError("close_sequence must be positive")
        for name, value in (
            ("previous_hardnav", self.previous_hardnav),
            ("current_hardnav", self.current_hardnav),
            ("previous_liabilities", self.previous_liabilities),
            ("current_liabilities", self.current_liabilities),
            ("eligible_asset_gross_growth", self.eligible_asset_gross_growth),
            ("flash_principal_inflow", self.flash_principal_inflow),
        ):
            if value < 0:
                raise FinancialContractError(f"{name} must be non-negative")

        allowed_classes = {
            "EXTERNAL_CASH",
            "SETTLED_RECEIVABLE",
            "VERIFIED_PRODUCTIVE_ASSET",
        }
        unknown = set(self.eligible_asset_classes) - allowed_classes
        if unknown:
            raise FinancialContractError(f"unsupported eligible asset classes: {sorted(unknown)}")
        if self.eligible_asset_gross_growth > 0 and not self.eligible_asset_classes:
            raise FinancialContractError("positive eligible growth requires an eligible asset class")
        if self.eligible_asset_gross_growth > 0 and not self.evidence_refs:
            raise FinancialContractError("positive eligible growth requires evidence refs")
        if any(not ref for ref in self.evidence_refs):
            raise FinancialContractError("evidence refs cannot contain empty values")

    @property
    def hardnav_growth(self) -> float:
        return max(self.current_hardnav - self.previous_hardnav, 0.0)

    @property
    def liability_increase(self) -> float:
        return max(self.current_liabilities - self.previous_liabilities, 0.0)

    @property
    def net_eligible_asset_growth(self) -> float:
        return max(self.eligible_asset_gross_growth - self.liability_increase, 0.0)

    @property
    def credited_growth(self) -> float:
        return min(self.hardnav_growth, self.net_eligible_asset_growth)

    def as_payload(self) -> dict:
        payload = asdict(self)
        payload["eligible_asset_classes"] = list(self.eligible_asset_classes)
        payload["evidence_refs"] = list(self.evidence_refs)
        payload["hardnav_growth"] = self.hardnav_growth
        payload["liability_increase"] = self.liability_increase
        payload["net_eligible_asset_growth"] = self.net_eligible_asset_growth
        payload["credited_growth"] = self.credited_growth
        return payload


@dataclass(frozen=True)
class EmissionReleaseRecognition:
    """Financial OS recognition of an AICB escrow release.

    Minting or releasing a monetary unit is not revenue and is not realized
    profit. The legal/accounting classification of the circulating unit is kept
    explicit because it depends on the sandbox instrument and issuer structure.
    """

    proposal_id: str
    release_tx_ref: str
    financial_growth_attestation_ref: str
    productive_growth_attestation_ref: str
    released_units: float
    unit_value: float
    accounting_classification: Literal[
        "MONETARY_LIABILITY",
        "EQUITY_LIKE_CIRCULATION",
        "OFF_BALANCE_SHEET_UNIT",
    ]
    recognition_status: Literal["RECOGNIZED", "EXCEPTION", "REVERSED"] = "RECOGNIZED"
    recognized_revenue: float = 0.0
    recognized_profit: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("released_units", self.released_units),
            ("unit_value", self.unit_value),
        ):
            if value < 0:
                raise FinancialContractError(f"{name} must be non-negative")
        for name, value in (
            ("proposal_id", self.proposal_id),
            ("release_tx_ref", self.release_tx_ref),
            ("financial_growth_attestation_ref", self.financial_growth_attestation_ref),
            ("productive_growth_attestation_ref", self.productive_growth_attestation_ref),
        ):
            if not value:
                raise FinancialContractError(f"{name} is required")
        if abs(self.recognized_revenue) > 1e-12 or abs(self.recognized_profit) > 1e-12:
            raise FinancialContractError("mint/release cannot be recognized as revenue or profit")
        if self.recognition_status == "RECOGNIZED" and self.released_units <= 0:
            raise FinancialContractError("recognized release must contain positive units")

    @property
    def released_monetary_value(self) -> float:
        return self.released_units * self.unit_value

    def as_payload(self) -> dict:
        payload = asdict(self)
        payload["released_monetary_value"] = self.released_monetary_value
        return payload


@dataclass(frozen=True)
class FinancialCommitmentArtifact:
    close_id: str
    snapshot_hash: str
    merkle_root: str
    hardnav: float
    liquid_nav: float
    liabilities: float
    accounting_period_end: datetime

    def __post_init__(self) -> None:
        for label, value in (("snapshot_hash", self.snapshot_hash), ("merkle_root", self.merkle_root)):
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise FinancialContractError(f"{label} must be lowercase SHA-256 hex")
        if self.liabilities < 0:
            raise FinancialContractError("liabilities must be non-negative")

    def as_payload(self) -> dict:
        payload = asdict(self)
        payload["accounting_period_end"] = self.accounting_period_end.isoformat().replace("+00:00", "Z")
        return payload
