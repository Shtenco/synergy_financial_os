from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
    FlowType,
)
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule
from sinergy_financial_os.valuation_policy_artifact_v1 import (
    ValuationPolicyArtifactV1Error,
    build_valuation_policy_artifact_v1,
    verify_valuation_policy_against_snapshot_v1,
    verify_valuation_policy_artifact_payload_v1,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/valuation_policy_artifact_v1.schema.json"


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def policy() -> ValuationPolicy:
    return ValuationPolicy(
        "valuation-2026-08-19",
        "USDC",
        dt("2026-08-19T10:00:00Z"),
        (
            ValuationRule("CASH", Decimal("1.000"), Decimal("1"), Decimal("1.0"), "BANK_BALANCE", True, False, 3600, "bank cash"),
            ValuationRule("TAX_REC", Decimal("0.8"), Decimal("0.9"), Decimal("1"), "AUDITED_NAV", True, False, 86400, "recoverable tax claim"),
        ),
    )


def ledger() -> ReportingLedger:
    value = ReportingLedger("USDC")
    value.register_account(ReportingAccountSpec("cash", "Cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    value.register_account(ReportingAccountSpec("equity", "Capital", AccountClass.EQUITY, ConsolidationClass.EXTERNAL, "EQUITY"))
    return value


def horizons(amount):
    return (
        LiquidityHorizonState(1, amount, Decimal("0")),
        LiquidityHorizonState(4, amount, Decimal("0")),
        LiquidityHorizonState(8, amount, Decimal("0")),
    )


def test_policy_artifact_round_trip_preserves_existing_policy_digest_and_schema():
    artifact = build_valuation_policy_artifact_v1(
        policy(), generated_at=dt("2026-08-19T10:05:00Z")
    )
    payload = artifact.to_dict()
    assert payload["policy"]["rules"][0]["hard_factor"] == "1"
    assert payload["policy"]["rules"][1]["hard_factor"] == "0.8"
    assert payload["valuation_policy_digest"] == artifact.policy.digest
    assert verify_valuation_policy_artifact_payload_v1(payload) == artifact
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(payload)


def test_policy_artifact_binds_exact_financial_snapshot_policy_identity():
    source_policy = policy()
    artifact = build_valuation_policy_artifact_v1(
        source_policy, generated_at=dt("2026-08-19T10:05:00Z")
    )
    book = ledger()
    book.post(
        event_id="capital-001", reference="capital-evidence-001", flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("100")), ReportingLine("equity", credit=Decimal("100"))),
        evidence_digest="11" * 32,
    )
    snapshot = capture_financial_snapshot_v2(
        book, source_policy, as_of=dt("2026-08-19T11:00:00Z"), accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("100")), required_hard_nav_buffer=Decimal("0"), policy_mode="NORMAL"
    )
    assert verify_valuation_policy_against_snapshot_v1(artifact, snapshot.to_dict()) is True


def test_changed_haircut_cannot_keep_old_inner_policy_digest_even_with_new_outer_hash():
    artifact = build_valuation_policy_artifact_v1(
        policy(), generated_at=dt("2026-08-19T10:05:00Z")
    )
    bad = copy.deepcopy(artifact.to_dict())
    bad["policy"]["rules"][1]["hard_factor"] = "0.7"
    bad.pop("digest")
    import hashlib
    bad["digest"] = hashlib.sha256(
        json.dumps(bad, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValuationPolicyArtifactV1Error, match="valuation_policy_digest mismatch"):
        verify_valuation_policy_artifact_payload_v1(bad)


def test_noncanonical_decimal_and_boolean_like_integer_fail_closed():
    artifact = build_valuation_policy_artifact_v1(
        policy(), generated_at=dt("2026-08-19T10:05:00Z")
    )
    bad = copy.deepcopy(artifact.to_dict())
    bad["policy"]["rules"][0]["hard_factor"] = "1.0"
    with pytest.raises(ValuationPolicyArtifactV1Error, match="not canonical decimal text"):
        verify_valuation_policy_artifact_payload_v1(bad)
    bad = copy.deepcopy(artifact.to_dict())
    bad["policy"]["rules"][0]["requires_external_enforceability"] = 1
    with pytest.raises(ValuationPolicyArtifactV1Error, match="must be boolean"):
        verify_valuation_policy_artifact_payload_v1(bad)
