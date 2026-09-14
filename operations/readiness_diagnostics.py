"""Diagnostic-only evidence inventory for candidate readiness."""

from datetime import date
import math
import re
from collections.abc import Callable
from urllib.parse import urlparse

from analysis.snapshots import ResearchSnapshot


MAX_DIAGNOSTIC_ITEMS = 20
MAX_DIAGNOSTIC_TEXT_LENGTH = 2048
_CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{64}")
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
_SEMANTIC_GROUPS = frozenset(_GENERAL_CONCEPTS) | frozenset(_BANK_CONCEPTS)
_NORMALIZED_CONCEPTS = frozenset(
    concept
    for definitions in (_GENERAL_CONCEPTS, _BANK_CONCEPTS)
    for aliases in definitions.values()
    for concept in aliases
)


def is_official_source_url(value: object) -> bool:
    """Accept only bounded, credential-free canonical IDX HTTPS identities."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_DIAGNOSTIC_TEXT_LENGTH
    ):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    official = (
        host == "idx.co.id"
        or host.endswith(".idx.co.id")
        or host == "idx.id"
        or host.endswith(".idx.id")
    )
    return bool(
        parsed.scheme == "https"
        and official
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def are_semantic_groups(values: list[str]) -> bool:
    """Reject arbitrary text masquerading as normalized concept diagnostics."""
    return all(value in _SEMANTIC_GROUPS for value in values)


def _bounded_strings(
    value: object, validator: Callable[[str], bool]
) -> tuple[list[str], bool]:
    if not isinstance(value, (list, tuple, set)) or len(value) > MAX_DIAGNOSTIC_ITEMS:
        return [], False
    normalized = []
    for item in value:
        if not isinstance(item, str):
            return [], False
        item = item.strip()
        if not item or len(item) > MAX_DIAGNOSTIC_TEXT_LENGTH or not validator(item):
            return [], False
        normalized.append(item)
    return sorted(set(normalized)), True


def is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _annual_history_years(value: object) -> int | None:
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (str, int, float))
    ):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return (
        int(number)
        if math.isfinite(number) and number >= 0 and number.is_integer()
        else None
    )


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
        candidate_profile = str(evidence.get("issuer_profile") or "UNVERIFIED").upper()
        raw_profile_checksum = str(evidence.get("profile_checksum") or "").lower()
        profile_checksum = (
            raw_profile_checksum
            if _CHECKSUM_PATTERN.fullmatch(raw_profile_checksum)
            else None
        )
        raw_profile_source = evidence.get("profile_source_url")
        profile_source = (
            raw_profile_source if is_official_source_url(raw_profile_source) else None
        )
        profile = (
            candidate_profile
            if candidate_profile in {"GENERAL", "BANK"}
            and profile_checksum is not None
            and profile_source is not None
            else "UNVERIFIED"
        )
        if profile == "UNVERIFIED":
            profile_source = None
            profile_checksum = None
        available_concepts, concepts_valid = _bounded_strings(
            evidence.get("available_concepts") or [],
            lambda value: value.lower() in _NORMALIZED_CONCEPTS,
        )
        concept_status = (
            concept_diagnostics(available_concepts, profile)
            if concepts_valid
            else {"status": "UNAVAILABLE", "missing_concepts": []}
        )
        annual_history_years = _annual_history_years(
            evidence.get("annual_history_years")
        )
        financial_periods, periods_valid = _bounded_strings(
            evidence.get("financial_periods") or [], is_iso_date
        )
        source_documents, documents_valid = _bounded_strings(
            evidence.get("source_documents") or [],
            lambda value: bool(_CHECKSUM_PATTERN.fullmatch(value.lower())),
        )
        source_urls, sources_valid = _bounded_strings(
            evidence.get("source_urls") or [], is_official_source_url
        )
        merged[ticker] = {
            **ranking,
            "diagnostic_issuer_profile": profile,
            "diagnostic_profile_source_url": profile_source,
            "diagnostic_profile_checksum": profile_checksum,
            "diagnostic_profile_valid": profile != "UNVERIFIED",
            "diagnostic_annual_history_years": annual_history_years,
            "diagnostic_history_valid": annual_history_years is not None,
            "diagnostic_financial_periods": financial_periods,
            "diagnostic_financial_periods_valid": periods_valid,
            "diagnostic_source_documents": source_documents,
            "diagnostic_checksums_valid": documents_valid,
            "diagnostic_source_urls": source_urls,
            "diagnostic_sources_valid": sources_valid,
            "diagnostic_concept_status": concept_status["status"],
            "diagnostic_missing_concepts": concept_status["missing_concepts"],
            "diagnostic_concepts_valid": concepts_valid,
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
