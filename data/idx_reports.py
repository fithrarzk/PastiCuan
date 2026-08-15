"""Discovery of official IDX XBRL attachment URLs.

Discovery only creates a draft manifest. It never imports or approves data;
the generated URL list remains a human-reviewed boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from http.cookiejar import CookieJar
import json
import re
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from data.idx_xbrl import validate_official_idx_url


IDX_ORIGIN = "https://www.idx.id"
REPORTS_PAGE = f"{IDX_ORIGIN}/en/listed-companies/financial-statements-and-annual-report"
CATALOG_URL = f"{IDX_ORIGIN}/primary/ListedCompany/GetFinancialReport"
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
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": REPORTS_PAGE,
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
    }
    request = Request(
        f"{CATALOG_URL}?{query}",
        headers=headers,
    )
    try:
        # The idx.id frontend sets the normal visitor cookies needed by the
        # catalog. Going directly to the legacy idx.co.id API is rejected by
        # Cloudflare even though the same public catalog works in a web session.
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        with opener.open(Request(REPORTS_PAGE, headers=headers), timeout=45):
            pass
        with opener.open(request, timeout=45) as response:
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
    period_chain = ["tw1", "tw2", "tw3"]
    requested_index = period_chain.index(period)
    current_periods = list(reversed(period_chain[:requested_index + 1]))
    current = {}
    for report_period in current_periods:
        for row in fetch(year, report_period):
            ticker = str(row.get("KodeEmiten") or "").upper().replace(".JK", "")
            if ticker not in wanted or ticker in current:
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
            source_url = urljoin(f"{IDX_ORIGIN}/", quote(str(path), safe="/%:"))
            validate_official_idx_url(source_url)
            published = (attachment.get("File_Modified") or row.get("File_Modified")
                         or row.get("PublishedAt"))
            current[ticker] = {
                "ticker": ticker, "source_url": source_url,
                "published_at": _published_at(published),
                "filing_type": FILING_TYPE[report_period],
                "period_end": f"{year}-{PERIOD_END[report_period]}",
                "audit_status": "UNAUDITED",
                "restatement_version": 1,
            }

    annual = {}
    if include_prior_audit:
        for row in fetch(year - 1, "audit"):
            ticker = str(row.get("KodeEmiten") or "").upper().replace(".JK", "")
            if ticker not in wanted:
                continue
            candidates = [item for item in (row.get("Attachments") or []) if
                          str(item.get("File_Name") or "").lower() == "instance.zip"]
            if not candidates or not candidates[0].get("File_Path"):
                continue
            attachment = candidates[0]
            source_url = urljoin(
                f"{IDX_ORIGIN}/", quote(str(attachment["File_Path"]), safe="/%:"),
            )
            validate_official_idx_url(source_url)
            published = attachment.get("File_Modified") or row.get("File_Modified")
            annual[ticker] = {
                "ticker": ticker, "source_url": source_url,
                "published_at": _published_at(published), "filing_type": "ANNUAL",
                "period_end": f"{year - 1}-12-31", "audit_status": "AUDITED",
                "restatement_version": 1,
            }
    filings = [*current.values(), *annual.values()]
    return {
        "filings": sorted(filings, key=lambda row: (row["ticker"], row["period_end"])),
        "discovery": {
            "year": year, "period": period, "requested_tickers": len(wanted),
            "current_period_missing": sorted(wanted - set(current)),
            "prior_annual_missing": sorted(wanted - set(annual)) if include_prior_audit else [],
            "period_counts": {
                filing_type: sum(row["filing_type"] == filing_type for row in current.values())
                for filing_type in ("Q1", "Q2", "Q3")
            },
            "review_required": True,
        },
    }
