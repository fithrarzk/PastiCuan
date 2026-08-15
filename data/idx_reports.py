"""Discovery of official IDX XBRL attachment URLs.

Discovery only creates a draft manifest. It never imports or approves data;
the generated URL list remains a human-reviewed boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from data.idx_xbrl import validate_official_idx_url


CATALOG_URL = "https://www.idx.co.id/primary/ListedCompany/GetFinancialReport"
PERIOD_END = {"audit": "12-31", "tw1": "03-31", "tw2": "06-30", "tw3": "09-30"}
FILING_TYPE = {"audit": "ANNUAL", "tw1": "Q1", "tw2": "Q2", "tw3": "Q3"}
JAKARTA = timezone(timedelta(hours=7))


def _published_at(value) -> str:
    if not value:
        raise ValueError("IDX catalog row has no publication/modification timestamp.")
    text = str(value).strip()
    match = re.fullmatch(r"/Date\((\d+)(?:[+-]\d+)?\)/", text)
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).isoformat()
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JAKARTA)
    return parsed.isoformat()


def _fetch_catalog(year: int, period: str) -> list[dict]:
    query = urlencode({
        "indexFrom": 1, "pageSize": 2000, "year": year, "reportType": "rdf",
        "EmitenType": "s", "periode": period, "SortColumn": "KodeEmiten",
        "SortOrder": "asc",
    })
    request = Request(
        f"{CATALOG_URL}?{query}",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.idx.co.id/en/listed-companies/financial-statements-and-annual-report",
            "User-Agent": "Mozilla/5.0 PastiCuan research manifest discovery/3.1",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        if exc.code in {403, 429}:
            raise RuntimeError(
                "IDX blocked automated catalog discovery. Use official attachment URLs from the "
                "Financial Statements page in data/idx_filing_manifest.json."
            ) from exc
        raise
    rows = payload.get("Results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("IDX catalog response has an unsupported shape.")
    return rows


def discover_idx_xbrl_manifest(tickers: list[str], *, year: int, period: str,
                               fetch_catalog=None, include_prior_audit: bool = True) -> dict:
    if period not in PERIOD_END or period == "audit":
        raise ValueError("Current period must be one of tw1, tw2, or tw3.")
    wanted = {ticker.upper().replace(".JK", "") for ticker in tickers}
    fetch = fetch_catalog or _fetch_catalog
    requests = [(year, period)]
    if include_prior_audit:
        requests.append((year - 1, "audit"))
    filings = []
    for report_year, report_period in requests:
        for row in fetch(report_year, report_period):
            ticker = str(row.get("KodeEmiten") or "").upper().replace(".JK", "")
            if ticker not in wanted:
                continue
            attachments = row.get("Attachments") or []
            candidates = [item for item in attachments if
                          "instance" in str(item.get("File_Name") or "").lower()
                          and "inline" not in str(item.get("File_Name") or "").lower()
                          and str(item.get("File_Name") or "").lower().endswith(".zip")]
            if not candidates:
                continue
            attachment = sorted(candidates, key=lambda item: str(item.get("File_Name")))[0]
            path = attachment.get("File_Path")
            if not path:
                continue
            source_url = urljoin("https://www.idx.co.id/", str(path))
            validate_official_idx_url(source_url)
            published = (attachment.get("File_Modified") or row.get("File_Modified")
                         or row.get("PublishedAt"))
            filings.append({
                "ticker": ticker, "source_url": source_url,
                "published_at": _published_at(published),
                "filing_type": FILING_TYPE[report_period],
                "period_end": f"{report_year}-{PERIOD_END[report_period]}",
                "audit_status": "AUDITED" if report_period == "audit" else "UNAUDITED",
                "restatement_version": 1,
            })
    current_found = {row["ticker"] for row in filings if row["filing_type"] != "ANNUAL"}
    annual_found = {row["ticker"] for row in filings if row["filing_type"] == "ANNUAL"}
    return {
        "filings": sorted(filings, key=lambda row: (row["ticker"], row["period_end"])),
        "discovery": {
            "year": year, "period": period, "requested_tickers": len(wanted),
            "current_period_missing": sorted(wanted - current_found),
            "prior_annual_missing": sorted(wanted - annual_found) if include_prior_audit else [],
            "review_required": True,
        },
    }
