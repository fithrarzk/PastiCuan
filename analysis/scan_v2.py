"""Offline, fixed-weight, full-LQ45 end-of-day scanner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.scan_snapshots import ScanResearchSnapshot, signed_scan_snapshot
from analysis.scanner import _fetch_base, _liquidity_score
from data.extended import get_extended_data


SCAN_WEIGHTS = {"technical": 0.30, "quant": 0.40, "risk_reward": 0.20, "liquidity": 0.10}
MIN_TECHNICAL_COVERAGE = 80.0
MIN_QUANT_COVERAGE = 75.0
MIN_UNIVERSE_COVERAGE = 90.0
MIN_AVERAGE_VALUE = 1_000_000_000
MAX_QUANT_AGE_DAYS = 45
JAKARTA = ZoneInfo("Asia/Jakarta")


def _finite(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def planned_entry_risk_reward(base: dict) -> dict:
    buy_range = base.get("buy_range") or {}
    preferred = buy_range.get("preferred_range")
    technical = buy_range.get("technical_range")
    zone = preferred or technical
    zone_type = "preferred_overlap" if preferred else ("technical_only" if technical else "unavailable")
    if not zone:
        return {"status": "INVALID", "reason": "Entry zone is unavailable.", "zone": None,
                "zone_type": zone_type, "planned_rr": None, "price_state": "UNKNOWN"}
    low, high = _finite(zone.get("low")), _finite(zone.get("high"))
    stop, target = _finite(base.get("stop_loss")), _finite(base.get("take_profit"))
    current = _finite(base.get("current_price"))
    if None in {low, high, stop, target} or not stop < high < target or low > high:
        return {"status": "INVALID", "reason": "Required ordering is stop < entry <= target.",
                "zone": zone, "zone_type": zone_type, "planned_rr": None, "price_state": "UNKNOWN"}
    risk, reward = high - stop, target - high
    rr = reward / risk if risk > 0 else None
    if current is None:
        price_state = "UNKNOWN"
    elif low <= current <= high:
        price_state = "IN_ZONE"
    elif current > high:
        price_state = "ABOVE_ZONE"
    else:
        price_state = "BELOW_ZONE"
    return {"status": "AVAILABLE", "reason": None, "zone": zone, "zone_type": zone_type,
            "planned_rr": rr, "price_state": price_state, "entry_reference": high}


def risk_reward_score(rr: float | None) -> float | None:
    value = _finite(rr)
    if value is None or value < 1:
        return None
    return min(100.0, 50.0 + (value - 1.0) * 50.0)


def _iso_date(value: str) -> str:
    return pd.Timestamp(value).date().isoformat()


def _quant_is_fresh(snapshot, observed_at: datetime) -> bool:
    if snapshot is None or snapshot.snapshot_id == "bundled-empty-shadow":
        return False
    # The latest completed price session can be Friday while the research
    # snapshot is built on Saturday/Sunday. Freshness is relative to when the
    # scan is observed, not to the OHLCV session label. Using session_date here
    # incorrectly rejects valid weekend snapshots as if they were future data.
    age = (pd.Timestamp(observed_at).date() - pd.Timestamp(snapshot.effective_at).date()).days
    return 0 <= age <= MAX_QUANT_AGE_DAYS


def score_candidate(base: dict, quant_row: dict | None, *, primary: bool) -> tuple[dict | None, str | None]:
    ticker = base["ticker"]
    if not base.get("data_usable"):
        return None, "; ".join(base.get("quality_reasons") or []) or "OHLCV quality gate failed."
    technical = _finite(base.get("technical_score"))
    technical_coverage = _finite(base.get("technical_coverage")) or 0
    if technical is None or technical_coverage < MIN_TECHNICAL_COVERAGE:
        return None, f"Technical coverage {technical_coverage:.0f}% is below {MIN_TECHNICAL_COVERAGE:.0f}%."
    liquidity = _liquidity_score(_finite(base.get("avg_value")))
    if liquidity is None or float(base.get("avg_value") or 0) < MIN_AVERAGE_VALUE:
        return None, "Average traded value is below IDR 1bn or unavailable."
    setup = planned_entry_risk_reward(base)
    rr = _finite(setup.get("planned_rr"))
    if setup["status"] != "AVAILABLE":
        return None, setup["reason"]
    if rr is None or rr < 1:
        return None, f"Planned-entry risk/reward is {rr:.2f}R, below 1.0R." if rr is not None else "Risk/reward is unavailable."

    quant = _finite((quant_row or {}).get("composite_percentile"))
    quant_coverage = _finite((quant_row or {}).get("coverage_pct")) or 0
    if primary and (quant is None or quant_coverage < MIN_QUANT_COVERAGE):
        return None, f"Approved quant coverage {quant_coverage:.0f}% is below {MIN_QUANT_COVERAGE:.0f}%."

    rr_score = risk_reward_score(rr)
    evidence_coverage = (
        SCAN_WEIGHTS["technical"] * technical_coverage
        + SCAN_WEIGHTS["quant"] * (quant_coverage if quant is not None else 0)
        + SCAN_WEIGHTS["risk_reward"] * 100
        + SCAN_WEIGHTS["liquidity"] * 100
    )
    ranking_score = None
    if primary:
        ranking_score = (
            technical * SCAN_WEIGHTS["technical"]
            + quant * SCAN_WEIGHTS["quant"]
            + rr_score * SCAN_WEIGHTS["risk_reward"]
            + liquidity * SCAN_WEIGHTS["liquidity"]
        )
    eligibility = "SHORTLIST" if primary and rr >= 1.5 and setup["price_state"] == "IN_ZONE" else "WATCH"
    reasons = []
    if rr < 1.5:
        reasons.append("Risk/reward is below the 1.5R shortlist threshold.")
    if setup["price_state"] != "IN_ZONE":
        reasons.append(f"Price state is {setup['price_state']}; wait for the entry zone.")
    if not primary:
        reasons.append("Approved quant evidence is unavailable or stale; no overall score is published.")
    factors = {name: (quant_row or {}).get(name) for name in ("value", "quality", "momentum", "low_volatility")}
    return {
        "ticker": ticker,
        "display_ticker": base.get("display_ticker", f"{ticker}.JK"),
        "company": base.get("company", ticker),
        "sector": base.get("sector", "N/A"),
        "session_date": base.get("session_date"),
        "current_price": _finite(base.get("current_price")),
        "ranking_score": ranking_score,
        "composite_score": ranking_score,
        "technical_score": technical,
        "quant_percentile": quant,
        "quant_factors": factors,
        "risk_reward": rr,
        "risk_reward_score": rr_score,
        "liquidity_score": liquidity,
        "avg_value": _finite(base.get("avg_value")),
        "entry_zone": setup["zone"],
        "entry_zone_type": setup["zone_type"],
        "entry_reference": setup.get("entry_reference"),
        "stop_loss": _finite(base.get("stop_loss")),
        "target": _finite(base.get("take_profit")),
        "price_state": setup["price_state"],
        "eligibility": eligibility,
        "eligibility_reasons": reasons,
        "coverage_pct": evidence_coverage,
        "component_coverage": {
            "technical": technical_coverage, "quant": quant_coverage if quant is not None else 0,
            "risk_reward": 100, "liquidity": 100,
        },
        "source": "Yahoo Finance OHLCV fallback + approved point-in-time quant" if primary else "Yahoo Finance OHLCV fallback",
        "policy_label": "RESEARCH_ONLY",
    }, None


def _archive_payload(bases: list[dict], session_date: str) -> tuple[str, bytes]:
    records = []
    for base in bases:
        history = base.get("_history")
        if history is None or history.empty:
            continue
        frame = history.reset_index()
        frame.columns = [str(column) for column in frame.columns]
        records.append({"ticker": base["ticker"], "rows": frame.where(pd.notna(frame), None).to_dict("records")})
    raw = json.dumps({"session_date": session_date, "provider": "Yahoo Finance", "records": records},
                     default=str, sort_keys=True, separators=(",", ":")).encode()
    compressed = gzip.compress(raw, mtime=0)
    return hashlib.sha256(compressed).hexdigest(), compressed


def build_full_lq45_scan(
    repository,
    *,
    loader: Callable = get_extended_data,
    now: datetime | None = None,
    max_workers: int = 6,
    timeout_seconds: float = 180,
    archive_callback: Callable[[str, bytes], None] | None = None,
) -> ScanResearchSnapshot:
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    market_date = observed.astimezone(JAKARTA).date()
    on_date = market_date.isoformat()
    issuers = repository.constituent_issuers_as_of("LQ45", on_date)
    if len(issuers) != 45:
        return signed_scan_snapshot(
            snapshot_id=str(uuid4()), session_date=on_date, created_at=observed.isoformat(),
            mode="UNAVAILABLE", universe_size=45,
            warnings=[f"Exactly 45 effective LQ45 constituents are required; found {len(issuers)}."],
            source_summary={"membership": "Supabase point-in-time", "price": "not fetched"},
        )

    issuer_map = {str(item["ticker"]).upper().replace(".JK", ""): item for item in issuers}

    def load(ticker: str, period: str):
        data = loader(ticker, period=period, include_fundamentals=False)
        if not data.get("error"):
            basic = dict(data.get("basic") or {})
            basic.update({"sector": issuer_map[ticker].get("sector", "N/A"),
                          "longName": issuer_map[ticker].get("legal_name") or ticker})
            data["basic"] = basic
        return data

    bases, excluded = [], []
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lq45-eod")
    futures = {executor.submit(_fetch_base, ticker, "3y", load): ticker for ticker in issuer_map}
    try:
        for future in as_completed(futures, timeout=timeout_seconds):
            ticker = futures[future]
            try:
                base = future.result()
                history = base.get("_history")
                if history is None or history.empty:
                    raise ValueError("No completed OHLCV history.")
                base["session_date"] = pd.Timestamp(history.index[-1]).date().isoformat()
                bases.append(base)
            except Exception as exc:
                excluded.append({"ticker": ticker, "reason": str(exc)[:180]})
    except TimeoutError:
        for future, ticker in futures.items():
            if not future.done():
                future.cancel()
                excluded.append({"ticker": ticker, "reason": f"Provider timeout after {timeout_seconds:.0f}s."})
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    coverage = len(bases) / 45 * 100
    session_counts = pd.Series([base["session_date"] for base in bases]).value_counts() if bases else pd.Series(dtype=int)
    session_date = str(session_counts.index[0]) if not session_counts.empty else on_date
    same_session = [
        base for base in bases
        if base["session_date"] == session_date and base.get("data_usable")
    ]
    coverage = len(same_session) / 45 * 100
    if coverage < MIN_UNIVERSE_COVERAGE:
        return signed_scan_snapshot(
            snapshot_id=str(uuid4()), session_date=session_date, created_at=observed.isoformat(),
            mode="UNAVAILABLE", universe_size=45, universe_coverage_pct=coverage,
            excluded=excluded,
            warnings=[f"Fresh market coverage {coverage:.1f}% is below {MIN_UNIVERSE_COVERAGE:.0f}%."],
            source_summary={"membership": "Supabase point-in-time", "price": "Yahoo Finance fallback"},
        )

    known_age = repository.completed_session_age(session_date, on_date)
    fallback_age = len(pd.bdate_range(pd.Timestamp(session_date) + pd.offsets.Day(1), market_date))
    # The local session table cannot prove that an expected session is missing,
    # so never let its count weaken the conservative weekday estimate.
    session_age = max(known_age or 0, fallback_age)
    if session_age > 1:
        return signed_scan_snapshot(
            snapshot_id=str(uuid4()), session_date=session_date, created_at=observed.isoformat(),
            mode="UNAVAILABLE", universe_size=45, universe_coverage_pct=coverage,
            excluded=excluded,
            warnings=[f"Market data is {session_age} completed-session estimate(s) old."],
            source_summary={"membership": "Supabase point-in-time", "price": "Yahoo Finance fallback"},
        )

    repository.import_yahoo_market_histories(
        {base["ticker"]: base["_history"] for base in same_session},
        available_at=observed.isoformat(),
    )
    repository.record_completed_market_session(session_date, observed_at=observed.isoformat())

    quant_snapshot = repository.latest_approved_quant_snapshot()
    quant_fresh = _quant_is_fresh(quant_snapshot, observed)
    quant_map = quant_snapshot.rankings if quant_fresh else {}
    quant_hits = sum(
        1 for base in same_session
        if _finite((quant_map.get(base["ticker"]) or {}).get("composite_percentile")) is not None
        and (_finite((quant_map.get(base["ticker"]) or {}).get("coverage_pct")) or 0)
        >= MIN_QUANT_COVERAGE
    )
    primary = quant_fresh and quant_hits / 45 * 100 >= MIN_UNIVERSE_COVERAGE
    mode = "PRIMARY" if primary else "DEGRADED"
    candidates = []
    for base in same_session:
        candidate, reason = score_candidate(base, quant_map.get(base["ticker"]), primary=primary)
        if candidate:
            candidates.append(candidate)
        else:
            excluded.append({"ticker": base["ticker"], "reason": reason or "Eligibility gate failed."})
    candidates.sort(key=lambda row: (
        0 if row["eligibility"] == "SHORTLIST" else 1,
        -(row["ranking_score"] if row["ranking_score"] is not None else row["technical_score"]),
        row["ticker"],
    ))
    for index, candidate in enumerate(candidates, 1):
        candidate["rank"] = index if primary else None

    warnings = []
    if not primary:
        warnings.append("Approved LQ45 quant evidence is missing, stale, or covers less than 90% of the universe.")
    warnings.append("Completed Yahoo OHLCV is a fallback source; Yahoo fundamentals are not used.")
    archive_summary = None
    if archive_callback:
        checksum, body = _archive_payload(same_session, session_date)
        archive_key = f"scan-inputs/{session_date}/{checksum}.json.gz"
        try:
            archive_callback(archive_key, body)
            archive_summary = {
                "status": "ARCHIVED",
                "object_key": archive_key,
                "checksum": checksum,
                "content": "normalized Yahoo OHLCV extraction",
            }
        except Exception as exc:
            # R2 is optional and cannot make a valid Supabase scan disappear.
            # Keep the failure visible without leaking credentials or provider
            # response bodies into the signed snapshot.
            archive_summary = {"status": "FAILED", "error_type": type(exc).__name__}
            warnings.append(
                f"Optional R2 scan-input archive failed ({type(exc).__name__}); "
                "the SHADOW snapshot was still published."
            )
    return signed_scan_snapshot(
        snapshot_id=str(uuid4()), session_date=session_date, created_at=observed.isoformat(),
        mode=mode, candidates=candidates, excluded=excluded, warnings=warnings,
        universe_size=45, universe_coverage_pct=coverage,
        quant_snapshot_id=quant_snapshot.snapshot_id if primary else None,
        model_status="SHADOW",
        source_summary={
            "membership": "Supabase point-in-time LQ45", "price": "Yahoo Finance OHLCV fallback",
            "quant": quant_snapshot.snapshot_id if primary else "unavailable",
            "r2_archive": archive_summary,
        },
    )
