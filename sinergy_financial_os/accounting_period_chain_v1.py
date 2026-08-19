from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence

from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError


SCHEMA = "accounting.period-chain-proof/v1"
HEX = frozenset("0123456789abcdef")


class AccountingPeriodChainV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingPeriodChainV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise AccountingPeriodChainV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingPeriodChainV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class AccountingPeriodChainProofV1:
    origin_period_close_digest: str
    target_period_digest: str
    target_opening_period_close_digest: str
    chain_close_digests: tuple[str, ...]
    generated_at: datetime
    authority: str = "PROVENANCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "PROVENANCE_ONLY" or self.execution_authority != "NONE":
            raise AccountingPeriodChainV1Error("period chain proof is provenance-only")
        origin = _hex64(self.origin_period_close_digest, "origin_period_close_digest")
        target = _hex64(
            self.target_opening_period_close_digest,
            "target_opening_period_close_digest",
        )
        period = _hex64(self.target_period_digest, "target_period_digest")
        chain = tuple(_hex64(item, "chain_close_digest") for item in self.chain_close_digests)
        if not chain:
            raise AccountingPeriodChainV1Error("period chain proof requires at least origin close")
        if chain[0] != origin:
            raise AccountingPeriodChainV1Error("chain must start at origin PeriodClose")
        if chain[-1] != target:
            raise AccountingPeriodChainV1Error("chain must end at target opening PeriodClose")
        if len(set(chain)) != len(chain):
            raise AccountingPeriodChainV1Error("period close chain cannot contain a cycle/repeated digest")
        object.__setattr__(self, "origin_period_close_digest", origin)
        object.__setattr__(self, "target_period_digest", period)
        object.__setattr__(self, "target_opening_period_close_digest", target)
        object.__setattr__(self, "chain_close_digests", chain)
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "origin_period_close_digest": self.origin_period_close_digest,
            "target_period_digest": self.target_period_digest,
            "target_opening_period_close_digest": self.target_opening_period_close_digest,
            "chain_close_digests": list(self.chain_close_digests),
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def build_accounting_period_chain_proof_v1(
    period_closes: Sequence[AccountingPeriodCloseV1],
    target_period: AccountingPeriodV1,
    *,
    generated_at: datetime,
) -> AccountingPeriodChainProofV1:
    closes = tuple(period_closes)
    if not closes:
        raise AccountingPeriodChainV1Error("period_closes cannot be empty")
    for index, close in enumerate(closes):
        if not isinstance(close, AccountingPeriodCloseV1):
            raise AccountingPeriodChainV1Error(f"period_closes[{index}] must be AccountingPeriodCloseV1")
        if index > 0 and close.previous_period_close_digest != closes[index - 1].digest:
            raise AccountingPeriodChainV1Error(
                f"PeriodClose chain breaks at index {index}: previous digest mismatch"
            )
    if target_period.opening_period_close_digest != closes[-1].digest:
        raise AccountingPeriodChainV1Error(
            "target period opening close must equal final PeriodClose in chain"
        )
    proof = AccountingPeriodChainProofV1(
        origin_period_close_digest=closes[0].digest,
        target_period_digest=target_period.digest,
        target_opening_period_close_digest=closes[-1].digest,
        chain_close_digests=tuple(close.digest for close in closes),
        generated_at=generated_at,
    )
    verify_accounting_period_chain_proof_v1(proof, closes, target_period)
    return proof


def verify_accounting_period_chain_proof_v1(
    proof: AccountingPeriodChainProofV1,
    period_closes: Sequence[AccountingPeriodCloseV1],
    target_period: AccountingPeriodV1,
) -> bool:
    if not isinstance(proof, AccountingPeriodChainProofV1):
        raise AccountingPeriodChainV1Error("proof must be AccountingPeriodChainProofV1")
    closes = tuple(period_closes)
    if not closes:
        raise AccountingPeriodChainV1Error("period_closes cannot be empty")
    digests = tuple(close.digest for close in closes)
    if digests != proof.chain_close_digests:
        raise AccountingPeriodChainV1Error("supplied PeriodClose objects do not match proof digest chain")
    if target_period.digest != proof.target_period_digest:
        raise AccountingPeriodChainV1Error("target period digest mismatch")
    if target_period.opening_period_close_digest != proof.target_opening_period_close_digest:
        raise AccountingPeriodChainV1Error("target opening PeriodClose mismatch")
    if closes[0].digest != proof.origin_period_close_digest:
        raise AccountingPeriodChainV1Error("origin PeriodClose mismatch")
    for index in range(1, len(closes)):
        if closes[index].previous_period_close_digest != closes[index - 1].digest:
            raise AccountingPeriodChainV1Error(
                f"PeriodClose ancestry breaks at index {index}"
            )
    return True
