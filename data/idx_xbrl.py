"""Strict extraction of the small, reviewed factor set from official IDX XBRL.

The parser intentionally does not try to turn every taxonomy element into a
financial database.  Unknown concepts are ignored and ambiguous/dimensional
facts are excluded.  That keeps the production factor contract auditable.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from io import BytesIO
import hashlib
from pathlib import PurePosixPath
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


XBRLI = "http://www.xbrl.org/2003/instance"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
MAX_ARCHIVE_FILES = 25
MAX_INSTANCE_BYTES = 25 * 1024 * 1024

# Ordered aliases: lower numbers win when two IDX concepts describe the same
# normalized value for the same period.
CONCEPTS = {
    "ProfitLossAttributableToParentEntity": ("net_income", 0),
    "ProfitLoss": ("net_income", 1),
    "NetCashFlowsReceivedFromUsedInOperatingActivities": ("operating_cash_flow", 0),
    "EquityAttributableToEquityOwnersOfParentEntity": ("stockholders_equity", 0),
    "Equity": ("stockholders_equity", 1),
    "TotalEquity": ("stockholders_equity", 1),
    "CashAndCashEquivalents": ("cash_and_cash_equivalents", 0),
    "CashAndCashEquivalentsCashFlows": ("cash_and_cash_equivalents", 1),
    "BasicEarningsLossPerShareFromContinuingOperations": ("basic_earnings_per_share", 0),
    "Assets": ("total_assets", 0),
    "TotalAssets": ("total_assets", 1),
    "Liabilities": ("total_liabilities", 0),
    "TotalLiabilities": ("total_liabilities", 1),
    "ShortTermAndLongTermLoans": ("total_debt", 0),
    "InterestBearingLiabilities": ("total_debt", 1),
    "LoansAndReceivables": ("gross_loans", 1),
    "LoansAndReceivablesGross": ("gross_loans", 0),
    "DepositsFromCustomers": ("customer_deposits", 0),
    "AllowanceForImpairmentLossesOnLoans": ("loan_loss_allowance", 0),
    "ImpairedLoans": ("impaired_loans", 0),
    "InterestAndShariaIncome": ("interest_income", 1),
    "InterestIncome": ("interest_income", 0),
    "ImpairmentLossesOnFinancialAssets": ("credit_impairment_expense", 0),
    "CapitalAdequacyRatio": ("capital_adequacy_ratio", 0),
}


def validate_official_idx_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "idx.co.id" or host.endswith(".idx.co.id")
                                        or host == "idx.id" or host.endswith(".idx.id")):
        raise ValueError("IDX filing URLs must use HTTPS on an official idx.co.id or idx.id host.")


def _instance_bytes(body: bytes) -> bytes:
    if body[:2] != b"PK":
        if len(body) > MAX_INSTANCE_BYTES:
            raise ValueError("XBRL instance exceeds the 25 MiB safety limit.")
        return body
    try:
        with ZipFile(BytesIO(body)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > MAX_ARCHIVE_FILES:
                raise ValueError("IDX instance archive contains too many files.")
            candidates = []
            for item in members:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("IDX instance archive contains an unsafe path.")
                if item.file_size > MAX_INSTANCE_BYTES:
                    raise ValueError("XBRL instance exceeds the 25 MiB safety limit.")
                if path.suffix.lower() in {".xbrl", ".xml"}:
                    candidates.append(item)
            if not candidates:
                raise ValueError("IDX archive contains no XBRL/XML instance.")
            # Real IDX instance archives contain one instance. If auxiliary XML
            # exists, the instance is normally the largest document.
            selected = max(candidates, key=lambda item: item.file_size)
            return archive.read(selected)
    except BadZipFile as exc:
        raise ValueError("IDX filing is not a valid ZIP archive.") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _contexts(root: ET.Element) -> dict[str, dict]:
    result = {}
    for node in root.findall(f"{{{XBRLI}}}context"):
        context_id = node.get("id")
        period = node.find(f"{{{XBRLI}}}period")
        if not context_id or period is None:
            continue
        instant = period.findtext(f"{{{XBRLI}}}instant")
        start = period.findtext(f"{{{XBRLI}}}startDate")
        end = period.findtext(f"{{{XBRLI}}}endDate")
        # Main consolidated facts use a context without segment/scenario
        # dimensions. Dimensional note facts would otherwise be double-counted.
        dimensional = any(_local(child.tag) in {"segment", "scenario"} for child in node.iter())
        if (instant or end) and not dimensional:
            result[context_id] = {"period_start": start, "period_end": instant or end}
    return result


def _units(root: ET.Element) -> dict[str, str]:
    result = {}
    for node in root.findall(f"{{{XBRLI}}}unit"):
        unit_id = node.get("id")
        if not unit_id:
            continue
        measures = [str(value).strip() for value in node.itertext() if str(value).strip()]
        result[unit_id] = "/".join(measures) or unit_id
    return result


def _numeric(text: str | None, scale: int) -> Decimal | None:
    if text is None:
        return None
    try:
        value = Decimal(text.strip().replace(",", "")) * (Decimal(10) ** scale)
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _period_classification(period_start: str | None, period_end: str, filing_type: str) -> dict:
    """Classify a fact from explicit filing semantics, never from row order."""
    if not period_start:
        return {"period_type": "INSTANT", "duration_class": None,
                "fiscal_year": date.fromisoformat(period_end).year, "fiscal_quarter": None}
    kind = str(filing_type or "").upper()
    end = date.fromisoformat(period_end)
    duration = (end - date.fromisoformat(period_start)).days
    if kind in {"ANNUAL", "FY", "AUDITED"} or 330 <= duration <= 380:
        duration_class, quarter = "FY", 4
    elif "QTD" in kind or "DISCRETE" in kind:
        duration_class, quarter = "QTD", max(1, min(4, (end.month - 1) // 3 + 1))
    elif kind in {"Q1", "TW1"}:
        duration_class, quarter = "YTD", 1
    elif kind in {"Q2", "TW2", "HY", "HALF_YEAR"}:
        duration_class, quarter = "YTD", 2
    elif kind in {"Q3", "TW3", "9M"}:
        duration_class, quarter = "YTD", 3
    else:
        duration_class, quarter = "OTHER", None
    return {"period_type": "DURATION", "duration_class": duration_class,
            "fiscal_year": end.year, "fiscal_quarter": quarter}


def parse_idx_xbrl(body: bytes, *, ticker: str, source_url: str, published_at: str,
                   filing_type: str, filing_period_end: str, document_checksum: str,
                   object_key: str, audit_status: str = "UNAUDITED",
                   restatement_version: int = 1) -> dict:
    """Return canonical statement facts and point-in-time diagnostics."""
    validate_official_idx_url(source_url)
    if not published_at:
        raise ValueError("published_at is required; retrieval time must not be backdated as filing availability.")
    try:
        publication_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        declared_period_end = date.fromisoformat(filing_period_end)
    except ValueError as exc:
        raise ValueError("published_at or filing period_end is invalid.") from exc
    if publication_time.tzinfo is None:
        raise ValueError("published_at must include an explicit timezone.")
    if publication_time.date() < declared_period_end:
        raise ValueError("published_at cannot precede the filing period end.")
    raw = _instance_bytes(body)
    lowered = raw[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("DTD/entity declarations are not allowed in IDX XBRL.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("IDX XBRL instance is malformed.") from exc
    if _local(root.tag).lower() != "xbrl":
        raise ValueError("IDX attachment is XML but is not an XBRL instance.")

    contexts, units = _contexts(root), _units(root)
    candidates = {}
    entity_code = None
    sector = None
    industry = None
    xbrl_period_end = None
    for node in root:
        name = _local(node.tag)
        if name == "EntityCode" and node.text:
            entity_code = node.text.strip().upper().replace(".JK", "")
        elif name == "Sector" and node.text and not sector:
            sector = node.text.strip()
        elif name == "EntityMainIndustry" and node.text and not industry:
            industry = node.text.strip()
        elif name == "CurrentPeriodEndDate" and node.text:
            xbrl_period_end = node.text.strip()
        definition = CONCEPTS.get(name)
        context = contexts.get(node.get("contextRef", ""))
        if not definition or not context or node.get(f"{{{XSI}}}nil") == "true":
            continue
        scale = int(node.get("scale", "0"))
        value = _numeric(node.text, scale)
        if value is None:
            continue
        normalized, priority = definition
        key = (normalized, context["period_start"], context["period_end"])
        previous = candidates.get(key)
        if previous is None or priority < previous[0]:
            unit = units.get(node.get("unitRef", ""), node.get("unitRef") or "pure")
            currency = "IDR" if "IDR" in unit.upper() else None
            candidates[key] = (priority, {
                "ticker": ticker.upper().replace(".JK", ""),
                "filing_type": filing_type,
                "period_start": context["period_start"],
                "period_end": context["period_end"],
                "published_at": published_at,
                "available_at": published_at,
                "taxonomy": node.tag.partition("}")[0].lstrip("{") or "IDX",
                "concept": name,
                "normalized_concept": normalized,
                # Scale is applied here so all stored canonical values use scale 0.
                "value": str(value),
                "currency": currency,
                "unit": unit,
                "source_url": source_url,
                "document_checksum": document_checksum,
                "restatement_version": int(restatement_version),
                "consolidated": True,
                "audit_status": audit_status,
                "object_key": object_key,
                "scale": 0,
                **_period_classification(context["period_start"], context["period_end"], filing_type),
            })
    expected = ticker.upper().replace(".JK", "")
    if entity_code and entity_code != expected:
        raise ValueError(f"XBRL entity {entity_code} does not match manifest ticker {expected}.")
    if xbrl_period_end and xbrl_period_end != filing_period_end:
        raise ValueError(
            f"XBRL period end {xbrl_period_end} does not match manifest period end {filing_period_end}."
        )
    facts = [value[1] for value in candidates.values()]
    if not facts:
        raise ValueError("IDX XBRL contains none of the reviewed factor concepts.")
    if not any(item["normalized_concept"] == "net_income" for item in facts):
        raise ValueError("IDX XBRL has no supported consolidated net-income fact.")
    checksum = hashlib.sha256(raw).hexdigest()
    return {
        "facts": sorted(facts, key=lambda item: (item["period_end"], item["normalized_concept"])),
        "diagnostics": {
            "ticker": expected,
            "filing_period_end": filing_period_end,
            "xbrl_period_end": xbrl_period_end,
            "entity_code": entity_code,
            "sector": sector,
            "industry": industry,
            "instance_checksum": checksum,
            "fact_count": len(facts),
            "concepts": sorted({item["normalized_concept"] for item in facts}),
        },
    }
