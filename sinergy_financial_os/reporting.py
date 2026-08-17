from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from .core import AccountingInvariantError, FinancialState
from .valuation import ValuationRule


ZERO = Decimal("0")
GENESIS_DIGEST = "0" * 64


class AccountClass(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class ConsolidationClass(str, Enum):
    EXTERNAL = "EXTERNAL"
    INTRA_GROUP = "INTRA_GROUP"
    MEMO = "MEMO"


class FlowType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL_CAPITAL = "EXTERNAL_CAPITAL"
    EXTERNAL_REVENUE = "EXTERNAL_REVENUE"
    EXTERNAL_EXPENSE = "EXTERNAL_EXPENSE"
    LIABILITY_ISSUANCE = "LIABILITY_ISSUANCE"
    LIABILITY_REDEMPTION = "LIABILITY_REDEMPTION"
    CREDIT_ORIGINATION = "CREDIT_ORIGINATION"
    CREDIT_REPAYMENT = "CREDIT_REPAYMENT"
    CREDIT_LOSS = "CREDIT_LOSS"
    SETTLEMENT = "SETTLEMENT"


EVIDENCE_REQUIRED_FLOWS = frozenset(
    flow_type for flow_type in FlowType if flow_type != FlowType.INTERNAL
)


def _d(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


@dataclass(frozen=True)
class ReportingAccountSpec:
    account_id: str
    name: str
    account_class: AccountClass
    consolidation_class: ConsolidationClass
    valuation_class: str
    immediate_liability: bool = False

    def __post_init__(self) -> None:
        account_id = self.account_id.strip()
        name = self.name.strip()
        valuation_class = self.valuation_class.upper().strip()
        if not account_id or not name:
            raise AccountingInvariantError("account_id and name are required")
        if not valuation_class:
            raise AccountingInvariantError("valuation_class is required")
        if self.immediate_liability and self.account_class != AccountClass.LIABILITY:
            raise AccountingInvariantError(
                "immediate_liability is valid only for liability accounts"
            )
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "valuation_class", valuation_class)

    @property
    def normal_side(self) -> str:
        if self.account_class in {AccountClass.ASSET, AccountClass.EXPENSE}:
            return "DEBIT"
        return "CREDIT"

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "name": self.name,
            "account_class": self.account_class.value,
            "consolidation_class": self.consolidation_class.value,
            "valuation_class": self.valuation_class,
            "immediate_liability": self.immediate_liability,
            "normal_side": self.normal_side,
        }


@dataclass(frozen=True)
class ReportingLine:
    account_id: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO

    def __post_init__(self) -> None:
        account_id = self.account_id.strip()
        debit = _d(self.debit)
        credit = _d(self.credit)
        if not account_id:
            raise AccountingInvariantError("account_id is required")
        if debit < ZERO or credit < ZERO:
            raise AccountingInvariantError("debit and credit must be non-negative")
        if (debit > ZERO) == (credit > ZERO):
            raise AccountingInvariantError(
                "reporting line must contain exactly one positive debit or credit"
            )
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "debit", debit)
        object.__setattr__(self, "credit", credit)

    def canonical_dict(self) -> dict[str, str]:
        return {
            "account_id": self.account_id,
            "debit": format(self.debit, "f"),
            "credit": format(self.credit, "f"),
        }


@dataclass(frozen=True)
class ReportingEntry:
    sequence: int
    event_id: str
    reference: str
    flow_type: FlowType
    lines: tuple[ReportingLine, ...]
    previous_entry_digest: str
    evidence_digest: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise AccountingInvariantError("sequence must be >= 1")
        event_id = self.event_id.strip()
        reference = self.reference.strip()
        if not event_id or not reference:
            raise AccountingInvariantError("event_id and reference are required")
        if len(self.lines) < 2:
            raise AccountingInvariantError("reporting entry requires at least two lines")
        previous_digest = _hex64(self.previous_entry_digest, "previous_entry_digest")
        evidence_digest = self.evidence_digest
        if evidence_digest is not None:
            evidence_digest = _hex64(evidence_digest, "evidence_digest")
        debit_total = sum((line.debit for line in self.lines), ZERO)
        credit_total = sum((line.credit for line in self.lines), ZERO)
        if debit_total <= ZERO or debit_total != credit_total:
            raise AccountingInvariantError(
                f"unbalanced reporting entry: debits={debit_total} credits={credit_total}"
            )
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "previous_entry_digest", previous_digest)
        object.__setattr__(self, "evidence_digest", evidence_digest)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "reference": self.reference,
            "flow_type": self.flow_type.value,
            "lines": [line.canonical_dict() for line in self.lines],
            "previous_entry_digest": self.previous_entry_digest,
            "evidence_digest": self.evidence_digest,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @property
    def digest(self) -> str:
        return _sha256(self.canonical_dict())


class ReportingLedger:
    """Append-only Decimal ledger in one explicit reporting currency.

    Native settlement amounts belong to operational/source ledgers. This ledger
    accepts only already translated/valued reporting-currency entries under an
    explicit accounting policy and preserves their evidence binding.
    """

    def __init__(self, reporting_currency: str) -> None:
        currency = reporting_currency.upper().strip()
        if not currency:
            raise AccountingInvariantError("reporting_currency is required")
        self.reporting_currency = currency
        self._accounts: dict[str, ReportingAccountSpec] = {}
        self._entries: list[ReportingEntry] = []
        self._event_ids: set[str] = set()
        self._references: set[str] = set()
        self._raw_debits: dict[str, Decimal] = defaultdict(lambda: ZERO)
        self._raw_credits: dict[str, Decimal] = defaultdict(lambda: ZERO)

    @property
    def sequence(self) -> int:
        return len(self._entries)

    @property
    def chart_is_frozen(self) -> bool:
        return bool(self._entries)

    def register_account(self, spec: ReportingAccountSpec) -> None:
        if self.chart_is_frozen:
            raise AccountingInvariantError(
                "chart of accounts is frozen after the first reporting entry"
            )
        if spec.account_id in self._accounts:
            raise AccountingInvariantError(f"duplicate account_id: {spec.account_id}")
        self._accounts[spec.account_id] = spec

    def account(self, account_id: str) -> ReportingAccountSpec:
        try:
            return self._accounts[account_id]
        except KeyError as exc:
            raise AccountingInvariantError(f"unknown account: {account_id}") from exc

    def post(
        self,
        *,
        event_id: str,
        reference: str,
        flow_type: FlowType,
        lines: Iterable[ReportingLine],
        evidence_digest: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> ReportingEntry:
        event_id = event_id.strip()
        reference = reference.strip()
        if not event_id or not reference:
            raise AccountingInvariantError("event_id and reference are required")
        if event_id in self._event_ids:
            raise AccountingInvariantError(f"duplicate event_id: {event_id}")
        if reference in self._references:
            raise AccountingInvariantError(f"duplicate reference: {reference}")
        if flow_type in EVIDENCE_REQUIRED_FLOWS and evidence_digest is None:
            raise AccountingInvariantError(
                f"{flow_type.value} requires an external evidence digest"
            )

        lines_tuple = tuple(lines)
        for line in lines_tuple:
            self.account(line.account_id)

        previous_digest = self._entries[-1].digest if self._entries else GENESIS_DIGEST
        entry = ReportingEntry(
            sequence=self.sequence + 1,
            event_id=event_id,
            reference=reference,
            flow_type=flow_type,
            lines=lines_tuple,
            previous_entry_digest=previous_digest,
            evidence_digest=evidence_digest,
            metadata=dict(metadata or {}),
        )

        for line in lines_tuple:
            self._raw_debits[line.account_id] += line.debit
            self._raw_credits[line.account_id] += line.credit
        self._entries.append(entry)
        self._event_ids.add(event_id)
        self._references.add(reference)
        return entry

    def balance(self, account_id: str) -> Decimal:
        spec = self.account(account_id)
        debit = self._raw_debits[account_id]
        credit = self._raw_credits[account_id]
        value = debit - credit if spec.normal_side == "DEBIT" else credit - debit
        if value < ZERO:
            raise AccountingInvariantError(
                f"abnormal negative balance for {account_id}: {value}"
            )
        return value

    def trial_balance(self) -> tuple[Decimal, Decimal]:
        return (
            sum(self._raw_debits.values(), ZERO),
            sum(self._raw_credits.values(), ZERO),
        )

    def assert_balanced(self) -> None:
        debits, credits = self.trial_balance()
        if debits != credits:
            raise AccountingInvariantError(
                f"reporting trial balance mismatch: {debits} != {credits}"
            )

    def entries_since(self, sequence: int) -> tuple[ReportingEntry, ...]:
        if sequence < 0 or sequence > self.sequence:
            raise AccountingInvariantError("invalid reporting ledger sequence")
        return tuple(self._entries[sequence:])

    def immediate_external_liabilities(self) -> Decimal:
        return sum(
            (
                self.balance(account_id)
                for account_id, spec in self._accounts.items()
                if spec.account_class == AccountClass.LIABILITY
                and spec.consolidation_class == ConsolidationClass.EXTERNAL
                and spec.immediate_liability
            ),
            ZERO,
        )

    def financial_state(
        self,
        valuation_policy: Mapping[str, ValuationRule],
    ) -> FinancialState:
        hard_assets = ZERO
        liquid_assets = ZERO
        economic_assets = ZERO
        external_liabilities = ZERO

        for account_id, spec in self._accounts.items():
            balance = self.balance(account_id)
            if balance == ZERO:
                continue
            if spec.consolidation_class != ConsolidationClass.EXTERNAL:
                continue
            if spec.account_class == AccountClass.ASSET:
                try:
                    rule = valuation_policy[spec.valuation_class]
                except KeyError as exc:
                    raise AccountingInvariantError(
                        f"missing valuation rule for {spec.valuation_class}"
                    ) from exc
                if rule.valuation_class != spec.valuation_class:
                    raise AccountingInvariantError(
                        "valuation policy key/class mismatch for "
                        f"{spec.account_id}: {spec.valuation_class} != {rule.valuation_class}"
                    )
                valued = rule.apply(balance)
                hard_assets += valued.hard
                liquid_assets += valued.liquid
                economic_assets += valued.economic
            elif spec.account_class == AccountClass.LIABILITY:
                external_liabilities += balance

        return FinancialState(
            hard_external_assets=hard_assets,
            liquid_haircut_assets=liquid_assets,
            economic_haircut_assets=economic_assets,
            external_liabilities=external_liabilities,
        )

    @property
    def account_registry_digest(self) -> str:
        payload = [
            self._accounts[account_id].canonical_dict()
            for account_id in sorted(self._accounts)
        ]
        return _sha256(payload)

    @property
    def last_entry_digest(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS_DIGEST

    def canonical_state(self) -> dict[str, Any]:
        balances = {
            account_id: format(self.balance(account_id), "f")
            for account_id in sorted(self._accounts)
        }
        return {
            "schema": "reporting-ledger.state/v1",
            "reporting_currency": self.reporting_currency,
            "sequence": self.sequence,
            "account_registry_digest": self.account_registry_digest,
            "last_entry_digest": self.last_entry_digest,
            "balances": balances,
        }

    @property
    def digest(self) -> str:
        return _sha256(self.canonical_state())
