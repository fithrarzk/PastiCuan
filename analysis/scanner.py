"""Bounded research scanner consumed by Telegram delivery."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from analysis.contracts import ScanBundle
from analysis.engine import run_analysis_bundle
from analysis.quant import compute_cross_sectional_factors
from analysis.snapshots import get_research_snapshot
from data.extended import get_extended_data
from data.validation import completed_eod_history, split_adjusted_ohlcv


DEFAULT_SCAN_TICKERS = ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNTR", "ICBP", "AMRT", "ADRO"]
MAX_SCAN_TICKERS = 10
_CACHE_TTL_SECONDS = 15 * 60
_CACHE_MAX_ENTRIES = 50
_cache: OrderedDict[tuple[str, str], tuple[float, dict]] = OrderedDict()
_cache_lock = Lock()


def normalize_scan_tickers(tickers: list[str] | None, *, limit: int = MAX_SCAN_TICKERS) -> tuple[list[str], list[dict[str, str]]]:
    raw = tickers or DEFAULT_SCAN_TICKERS
    valid: list[str] = []
    excluded: list[dict[str, str]] = []
    for value in raw:
        ticker = str(value).strip().upper().replace(".JK", "")
        if not ticker or not ticker.replace("-", "").isalnum() or len(ticker) > 12:
            excluded.append({"ticker": str(value), "reason": "Invalid IDX ticker format."})
        elif ticker not in valid:
            valid.append(ticker)
    if len(valid) > limit:
        for ticker in valid[limit:]:
            excluded.append({"ticker": ticker, "reason": f"Scan limit is {limit} tickers."})
        valid = valid[:limit]
    return valid, excluded


def _cache_get(key: tuple[str, str]) -> dict | None:
    now = monotonic()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        created, value = item
        if now - created > _CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return value.copy()


def _cache_put(key: tuple[str, str], value: dict) -> None:
    with _cache_lock:
        _cache[key] = (monotonic(), value.copy())
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def _returns_features(history: pd.DataFrame) -> dict[str, float | None]:
    history = split_adjusted_ohlcv(completed_eod_history(history))
    close = history.get("Close", pd.Series(dtype=float)).dropna()
    returns = close.pct_change().dropna()

    def skip_return(lookback: int, skip: int = 20) -> float | None:
        if len(close) <= lookback:
            return None
        return float(close.iloc[-skip - 1] / close.iloc[-lookback - 1] - 1) if len(close) > lookback + skip else None

    realized = float(returns.tail(252).std() * np.sqrt(252)) if len(returns) >= 60 else None
    downside = returns.tail(252).clip(upper=0)
    downside_dev = float(np.sqrt((downside ** 2).mean()) * np.sqrt(252)) if len(returns) >= 60 else None
    return {
        "return_6m_skip_1m": skip_return(126),
        "return_12m_skip_1m": skip_return(252),
        "realized_volatility": realized,
        "downside_deviation": downside_dev,
    }


def _fetch_base(ticker: str, period: str, loader: Callable) -> dict:
    cached = _cache_get((ticker, period))
    if cached is not None and loader is get_extended_data:
        return cached
    data = (
        loader(ticker, period=period, include_fundamentals=False)
        if loader is get_extended_data
        else loader(ticker, period=period)
    )
    if data.get("error"):
        raise ValueError(str(data["error"]))
    analysis = run_analysis_bundle(data, include_backtest=False)
    tech, fund = analysis["tech"], analysis["fund"]
    quality = analysis["bundle"].data_quality
    info = data.get("info") or {}
    pe = fund.get("pe_value") if fund.get("pe_status") == "AVAILABLE" else None
    pbv = fund.get("pbv_value") if fund.get("pbv_status") == "AVAILABLE" else None
    momentum = _returns_features(data.get("history"))
    base = {
        "ticker": ticker,
        "display_ticker": data.get("ticker", f"{ticker}.JK"),
        "company": (data.get("basic") or {}).get("longName", ticker),
        "sector": (data.get("basic") or {}).get("sector", "N/A"),
        "as_of": quality.price_timestamp,
        "data_usable": quality.usable,
        "data_grade": quality.grade,
        "data_coverage": quality.coverage_pct,
        "quality_reasons": [issue.message for issue in quality.issues],
        "current_price": tech.get("current_price"),
        "technical_score": tech.get("technical_score"),
        "technical_coverage": tech.get("coverage_pct", 0),
        "technical_components": tech.get("score_components", {}),
        "technical_indicators": tech.get("indicators", {}),
        "fundamental_score": fund.get("fundamental_score"),
        "fundamental_coverage": fund.get("coverage_pct", 0),
        "buy_range": analysis["buy_range"],
        "risk_reward": tech.get("risk_reward"),
        "stop_loss": tech.get("stop_loss"),
        "take_profit": tech.get("take_profit"),
        "atr": tech.get("atr"),
        "support": tech.get("support"),
        "resistance": tech.get("resistance"),
        "avg_value": analysis["liquidity"].get("avg_value"),
        "pe": pe,
        "pbv": pbv,
        "quant_inputs": {
            "earnings_yield": 1 / pe if pe else None,
            "book_yield": 1 / pbv if pbv else None,
            "dividend_yield": fund.get("dividend_yield"),
            "roe": fund.get("roe"),
            "roic": info.get("returnOnCapital"),
            "cash_conversion": fund.get("cash_conversion"),
            "leverage": fund.get("debt_to_equity"),
            **momentum,
        },
        "source": fund.get("source"),
        "_history": data.get("history"),
    }
    if loader is get_extended_data:
        _cache_put((ticker, period), base)
    return base


def _liquidity_score(value: float | None) -> float | None:
    if value is None:
        return None
    if value >= 25_000_000_000:
        return 90.0
    if value >= 10_000_000_000:
        return 75.0
    if value >= 3_000_000_000:
        return 60.0
    if value >= 1_000_000_000:
        return 45.0
    return 20.0


def _relative_value_scores(bases: list[dict]) -> dict[str, float | None]:
    frame = pd.DataFrame({"ticker": [b["ticker"] for b in bases], "pe": [b["pe"] for b in bases], "pbv": [b["pbv"] for b in bases]})
    components = []
    for column in ("pe", "pbv"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() >= 5:
            components.append(100 - values.rank(pct=True, method="average") * 100)
    if not components:
        return {ticker: None for ticker in frame["ticker"]}
    scores = pd.concat(components, axis=1).mean(axis=1, skipna=True)
    return dict(zip(frame["ticker"], scores.where(scores.notna(), None)))


def run_scan(
    tickers: list[str] | None = None,
    *,
    period: str = "3y",
    loader: Callable = get_extended_data,
    max_workers: int = 2,
    timeout_seconds: float = 55,
    max_tickers: int = MAX_SCAN_TICKERS,
) -> ScanBundle:
    normalized, excluded = normalize_scan_tickers(tickers, limit=max_tickers)
    if not normalized:
        return ScanBundle(datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(), [], [], excluded)
    if tickers is not None and len(normalized) < 5:
        excluded.append({"ticker": "SCAN", "reason": "At least 5 unique valid tickers are required for comparison."})
        return ScanBundle(datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(), normalized, [], excluded)

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pasticuan-scan")
    futures = {executor.submit(_fetch_base, ticker, period, loader): ticker for ticker in normalized}
    done, pending = wait(futures, timeout=timeout_seconds)
    bases = []
    for future in done:
        ticker = futures[future]
        try:
            bases.append(future.result())
        except Exception as exc:
            excluded.append({"ticker": ticker, "reason": str(exc)[:180]})
    for future in pending:
        future.cancel()
        excluded.append({"ticker": futures[future], "reason": f"Provider timeout after {timeout_seconds:.0f}s."})
    executor.shutdown(wait=False, cancel_futures=True)
    bases.sort(key=lambda item: normalized.index(item["ticker"]))

    quant_rows = [{"ticker": b["ticker"], "sector": b["sector"], **b["quant_inputs"]} for b in bases]
    quant = compute_cross_sectional_factors(
        pd.DataFrame(quant_rows), min_universe=5, allow_global_fallback=True,
        as_of=max((b["as_of"] for b in bases if b["as_of"]), default=None),
    )
    quant_map = {}
    if quant["status"] == "AVAILABLE":
        quant_map = {row["ticker"]: row for row in quant["scores"].to_dict("records")}
    approved_snapshot = get_research_snapshot()
    snapshot_hits = 0
    for ticker in normalized:
        approved = approved_snapshot.ticker(ticker)
        if approved:
            quant_map[ticker] = {
                **approved,
                "ticker": ticker,
                "composite_percentile": approved.get("composite_percentile", approved.get("quant_percentile")),
                "ranking_scope": approved.get("ranking_scope", "historical_lq45"),
                "coverage_pct": approved.get("coverage_pct", 0),
            }
            snapshot_hits += 1
    value_scores = _relative_value_scores(bases)

    weights = {"technical": .35, "fundamental": .25, "quant": .20, "range": .10, "liquidity": .10}
    candidates = []
    for base in bases:
        mandatory_reason = None
        if not base["data_usable"]:
            mandatory_reason = "; ".join(base["quality_reasons"]) or "OHLCV data-quality gate failed."
        elif base["technical_coverage"] < 60:
            mandatory_reason = "Technical coverage is below 60%."
        elif base["avg_value"] is None or base["avg_value"] < 1_000_000_000:
            mandatory_reason = "Average traded value is below IDR 1bn or unavailable."
        if mandatory_reason:
            excluded.append({"ticker": base["ticker"], "reason": mandatory_reason})
            continue

        relative_value = value_scores.get(base["ticker"])
        fundamental = base["fundamental_score"]
        if fundamental is not None and relative_value is not None:
            fundamental = fundamental * .75 + float(relative_value) * .25
        quant_row = quant_map.get(base["ticker"], {})
        quant_score = quant_row.get("composite_percentile")
        range_status = base["buy_range"].get("status")
        range_score = 100.0 if base["buy_range"].get("preferred_range") else (0.0 if range_status == "NO_OVERLAP" else None)
        components = {
            "technical": base["technical_score"], "fundamental": fundamental,
            "quant": quant_score, "range": range_score,
            "liquidity": _liquidity_score(base["avg_value"]),
        }
        present = {key: float(value) for key, value in components.items() if value is not None and not pd.isna(value)}
        component_coverage = {
            "technical": base["technical_coverage"] / 100 if components["technical"] is not None else 0,
            "fundamental": base["fundamental_coverage"] / 100 if components["fundamental"] is not None else 0,
            "quant": float(quant_row.get("coverage_pct", 0)) / 100 if components["quant"] is not None else 0,
            "range": 1.0 if components["range"] is not None else 0,
            "liquidity": 1.0 if components["liquidity"] is not None else 0,
        }
        coverage = sum(weights[key] * component_coverage[key] for key in weights) * 100
        minimum_coverage = 55 if loader is get_extended_data else 70
        if coverage < minimum_coverage:
            excluded.append({
                "ticker": base["ticker"],
                "reason": (
                    f"Composite evidence coverage is {coverage:.0f}%, "
                    f"below {minimum_coverage}%."
                ),
            })
            continue
        composite = sum(value * weights[key] for key, value in present.items()) / sum(weights[key] for key in present)
        candidates.append({
            "ticker": base["ticker"], "display_ticker": base["display_ticker"],
            "company": base["company"], "sector": base["sector"], "as_of": base["as_of"],
            "current_price": base["current_price"], "composite_score": composite,
            "technical_score": base["technical_score"], "fundamental_score": fundamental,
            "quant_percentile": quant_score, "quant_scope": quant_row.get("ranking_scope", "unavailable"),
            "preferred_range": base["buy_range"].get("preferred_range"),
            "range_status": range_status, "risk_reward": base["risk_reward"],
            "avg_value": base["avg_value"], "coverage_pct": coverage,
            "data_grade": base["data_grade"], "source": base["source"],
            "policy_label": "RESEARCH_ONLY", "components": components,
            "component_coverage": {key: value * 100 for key, value in component_coverage.items()},
        })
    candidates.sort(key=lambda item: (-item["composite_score"], item["ticker"]))
    for rank, candidate in enumerate(candidates, 1):
        candidate["rank"] = rank
    warnings = list(quant.get("warnings", []))
    if snapshot_hits:
        warnings.insert(0, f"Quant evidence uses approved {approved_snapshot.snapshot_id} effective {approved_snapshot.effective_at}.")
    if any(value is not None for value in value_scores.values()):
        warnings.append("Relative PE/PBV evidence uses the global scan universe, not sector peers.")
    if loader is get_extended_data:
        warnings.append(
            "Interactive scan intentionally skips Yahoo quote-summary fundamentals; "
            "scores use market evidence and any approved snapshot quant only."
        )
    else:
        warnings.append("Yahoo fundamentals are fallback data without authoritative filing publication timestamps.")
    return ScanBundle(
        as_of=datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        requested_tickers=normalized, candidates=candidates, excluded=excluded,
        warnings=list(dict.fromkeys(warnings)),
    )
