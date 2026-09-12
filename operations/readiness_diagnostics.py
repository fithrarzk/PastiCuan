"""Diagnostic-only evidence inventory for candidate readiness."""

from analysis.snapshots import ResearchSnapshot


_GENERAL_CONCEPTS = {
    "assets": {"total_assets"},
    "basic_eps": {"basic_earnings_per_share"},
    "cash": {
        "cash_and_cash_equivalents",
        "cash_cash_equivalents_and_short_term_investments",
    },
    "debt": {"total_debt", "short_and_long_term_debt"},
    "equity": {"stockholders_equity", "common_stock_equity", "total_equity"},
    "net_income": {"net_income", "net_income_common_stockholders"},
    "operating_cash_flow": {"operating_cash_flow", "cash_flow_from_operations"},
}
_BANK_CONCEPTS = {
    "assets": {"total_assets"},
    "basic_eps": {"basic_earnings_per_share"},
    "capital_adequacy_ratio": {"capital_adequacy_ratio"},
    "cash": {
        "cash_and_cash_equivalents",
        "cash_cash_equivalents_and_short_term_investments",
    },
    "credit_impairment": {"credit_impairment_expense"},
    "deposits": {"customer_deposits"},
    "equity": {"stockholders_equity", "common_stock_equity", "total_equity"},
    "impaired_loans": {"impaired_loans"},
    "loan_allowance": {"loan_loss_allowance"},
    "loans": {"gross_loans"},
    "net_income": {"net_income", "net_income_common_stockholders"},
}


def concept_diagnostics(concepts, issuer_profile: str) -> dict:
    """Disclose absent semantic groups without changing scoring requirements."""
    profile = str(issuer_profile or "").upper()
    definitions = {"GENERAL": _GENERAL_CONCEPTS, "BANK": _BANK_CONCEPTS}.get(profile)
    if definitions is None:
        return {"status": "PROFILE_UNVERIFIED", "missing_concepts": []}
    available = {str(value or "").strip().lower() for value in concepts or []}
    return {
        "status": "AVAILABLE",
        "missing_concepts": sorted(
            name
            for name, aliases in definitions.items()
            if available.isdisjoint(aliases)
        ),
    }


def merge_readiness_evidence(rankings: dict, evidence_rows: list[dict]) -> dict:
    """Attach point-in-time evidence identity without changing calculated values."""
    evidence_by_ticker = {
        str(row.get("ticker") or "").upper(): row for row in evidence_rows
    }
    merged = {}
    for ticker, ranking in rankings.items():
        evidence = evidence_by_ticker.get(ticker, {})
        profile = str(evidence.get("issuer_profile") or "UNVERIFIED").upper()
        concept_status = concept_diagnostics(
            evidence.get("available_concepts") or [], profile
        )
        merged[ticker] = {
            **ranking,
            "issuer_profile": profile,
            "issuer_profile_source": evidence.get("profile_source_url"),
            "issuer_profile_checksum": evidence.get("profile_checksum"),
            "annual_history_years": int(evidence.get("annual_history_years") or 0),
            "financial_periods": sorted(evidence.get("financial_periods") or []),
            "source_documents": sorted(evidence.get("source_documents") or []),
            "source_urls": sorted(evidence.get("source_urls") or []),
            "concept_diagnostic_status": concept_status["status"],
            "missing_concepts": concept_status["missing_concepts"],
        }
    return merged


def with_readiness_evidence(
    snapshot: ResearchSnapshot, evidence_rows: list[dict]
) -> ResearchSnapshot:
    """Return a candidate with evidence diagnostics and a matching checksum."""
    unsigned = {
        **snapshot.unsigned_dict(),
        "rankings": merge_readiness_evidence(snapshot.rankings, evidence_rows),
    }
    candidate = ResearchSnapshot(**unsigned)
    return ResearchSnapshot(
        **{**candidate.unsigned_dict(), "checksum": candidate.calculated_checksum()}
    )
