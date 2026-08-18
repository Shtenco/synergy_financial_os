import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config/repository_federation_v2.json"
EXPECTED_REPOSITORIES = {
    "Shtenco/synergy_financial_os",
    "Shtenco/ai_financial_system",
    "Shtenco/synergy_matrix_sota",
    "Shtenco/usds",
    "Shtenco/synergy_eurasian",
    "Shtenco/synergy_pay_system",
    "Shtenco/synergychain",
    "Shtenco/synergy_ai_blockchain",
    "Shtenco/agi_olga",
    "Shtenco/ai_language",
    "Shtenco/ai_compress",
    "Shtenco/ai_coder",
    "Shtenco/cashero",
    "Shtenco/synergychain.github.io",
    "Shtenco/shtencoauantai.github.io",
    "Shtenco/shtenco.github.io",
}


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_federation_v2_contains_exact_current_repository_set() -> None:
    registry = _registry()
    names = [item["name"] for item in registry["repositories"]]
    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_REPOSITORIES


def test_every_authority_domain_has_one_existing_owner() -> None:
    registry = _registry()
    repos = {item["name"]: item for item in registry["repositories"]}
    assert registry["authority_domains"]
    for domain, owner in registry["authority_domains"].items():
        assert domain.strip()
        assert owner in repos
        assert repos[owner]["authoritative"] is True


def test_accounting_and_profit_authority_is_exclusive_to_financial_os() -> None:
    registry = _registry()
    authorities = registry["authority_domains"]
    assert authorities["accounting"] == "Shtenco/synergy_financial_os"
    assert (
        authorities["nav_and_profit_recognition"]
        == "Shtenco/synergy_financial_os"
    )
    assert (
        authorities["risk_and_monetary_constitution"]
        == "Shtenco/synergy_financial_os"
    )


def test_settlement_and_maturity_have_separate_owners() -> None:
    authorities = _registry()["authority_domains"]
    assert authorities["household_maturity_schedule"] == "Shtenco/synergy_matrix_sota"
    assert authorities["payment_routing"] == "Shtenco/synergy_pay_system"
    assert (
        authorities["settlement_and_reconciliation"]
        == "Shtenco/synergy_pay_system"
    )


def test_ai_and_trust_are_not_execution_authorities() -> None:
    registry = _registry()
    repos = {item["name"]: item for item in registry["repositories"]}
    for name in ("Shtenco/agi_olga", "Shtenco/synergy_ai_blockchain"):
        assert repos[name]["live_execution_authority"] is False
    assert "AI_PROPOSAL_AUTHORITY_IS_NOT_EXECUTION_AUTHORITY" in registry["hard_rules"]
    assert "TRUST_COMMITMENT_IS_NOT_FINANCIAL_AUTHORIZATION" in registry["hard_rules"]


def test_public_and_historical_surfaces_cannot_own_financial_authority() -> None:
    registry = _registry()
    authorities = registry["authority_domains"]
    financial_domains = {
        "accounting",
        "nav_and_profit_recognition",
        "risk_and_monetary_constitution",
        "capital_allocation_screening",
        "payment_routing",
        "settlement_and_reconciliation",
        "household_maturity_schedule",
    }
    forbidden = {
        "Shtenco/synergychain.github.io",
        "Shtenco/shtencoauantai.github.io",
        "Shtenco/shtenco.github.io",
    }
    assert all(authorities[domain] not in forbidden for domain in financial_domains)


def test_only_metapay_has_a_nonfalse_live_execution_boundary() -> None:
    registry = _registry()
    enabled = {
        item["name"]: item["live_execution_authority"]
        for item in registry["repositories"]
        if item["live_execution_authority"] is not False
    }
    assert enabled == {
        "Shtenco/synergy_pay_system": "DENY_BY_DEFAULT_UNTIL_READINESS"
    }


def test_legacy_preservation_is_mandatory_for_every_repository() -> None:
    registry = _registry()
    assert registry["legacy_preservation_required"] is True
    assert all(item["preserve_history"] is True for item in registry["repositories"])
    assert (
        "LEGACY_FILES_ARE_NOT_DELETED_TO_SIMPLIFY_THE_CURRENT_ARCHITECTURE"
        in registry["hard_rules"]
    )


def test_new_repo_policy_prevents_unnecessary_repository_sprawl() -> None:
    registry = _registry()
    assert (
        registry["new_repository_policy"]
        == "CREATE_ONLY_FOR_NEW_EXCLUSIVE_DOMAIN_AUTHORITY"
    )
