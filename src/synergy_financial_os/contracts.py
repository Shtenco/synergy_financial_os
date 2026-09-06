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
