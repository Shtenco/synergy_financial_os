from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.accounting_period_chain_v1 import AccountingPeriodChainProofV1
from sinergy_financial_os.revenue_adjustment_v1 import RevenueAdjustmentAuthorizationV1


ROOT = Path(__file__).resolve().parents[1]
CHAIN_SCHEMA = ROOT / "schemas/accounting_period_chain_proof_v1.schema.json"
ADJUSTMENT_SCHEMA = ROOT / "schemas/revenue_adjustment_authorization_v1.schema.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def chain_payload():
    return AccountingPeriodChainProofV1(
        origin_period_close_digest="11" * 32,
        target_period_digest="22" * 32,
        target_opening_period_close_digest="33" * 32,
        chain_close_digests=("11" * 32, "33" * 32),
        generated_at=dt("2026-08-19T12:05:00Z"),
    ).to_dict()


def adjustment_payload():
    return RevenueAdjustmentAuthorizationV1(
        authorization_id="adjustment-auth-001",
        target_period_id="period-n-plus-2",
        project_id="project-001",
        reason="CHARGEBACK",
        original_period_close_digest="11" * 32,
        original_accounting_close_digest="22" * 32,
        original_revenue_recognition_digest="33" * 32,
        original_ledger_event_digest="44" * 32,
        original_reporting_entry_digest="55" * 32,
        period_chain_proof_digest="66" * 32,
        customer_refund_amount=Decimal("30.00"),
        revenue_reduction_amount=Decimal("27.0"),
        refund_reserve_release_amount=Decimal("1.00"),
        tax_adjustment_amount=Decimal("2.000"),
        tax_treatment="RECOVERABLE_RECEIVABLE",
        external_fee_expense_amount=Decimal("1.0"),
        external_refund_evidence_digest="77" * 32,
        tax_evidence_digest="88" * 32,
        fee_evidence_digest="99" * 32,
        decision_evidence_digest="aa" * 32,
        accounting_policy_digest="bb" * 32,
        requirement_registry_digest="cc" * 32,
        decision_authority="MULTISIG_GOVERNANCE",
        decided_at=dt("2026-08-19T12:10:00Z"),
        effective_at=dt("2026-08-19T12:20:00Z"),
    ).to_dict()


def test_runtime_objects_validate_against_strict_schemas_and_normalize_decimals():
    chain = chain_payload()
    adjustment = adjustment_payload()
    jsonschema.Draft202012Validator(load(CHAIN_SCHEMA)).validate(chain)
    jsonschema.Draft202012Validator(load(ADJUSTMENT_SCHEMA)).validate(adjustment)
    assert adjustment["customer_refund_amount"] == "30"
    assert adjustment["revenue_reduction_amount"] == "27"
    assert adjustment["refund_reserve_release_amount"] == "1"
    assert adjustment["tax_adjustment_amount"] == "2"
    assert adjustment["external_fee_expense_amount"] == "1"
    assert adjustment["total_cash_outflow_amount"] == "31"


def test_schema_rejects_noncanonical_decimal_ai_authority_and_unknown_tax_treatment():
    schema = load(ADJUSTMENT_SCHEMA)
    for field, value in (
        ("customer_refund_amount", "30.0"),
        ("revenue_reduction_amount", "027"),
        ("tax_adjustment_amount", "2.00"),
    ):
        bad = copy.deepcopy(adjustment_payload())
        bad[field] = value
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(bad)
    bad = adjustment_payload()
    bad["ai_authority"] = "AI_CENTRAL_BANK"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(bad)
    bad = adjustment_payload()
    bad["tax_treatment"] = "MAGIC_TAX_RESET"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(bad)


def test_period_chain_schema_rejects_duplicate_close_digest():
    bad = chain_payload()
    bad["chain_close_digests"] = ["11" * 32, "11" * 32]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(load(CHAIN_SCHEMA)).validate(bad)
