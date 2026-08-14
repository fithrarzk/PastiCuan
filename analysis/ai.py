"""Deterministic narrative rendering for the structured analysis contract."""

import json
import os
from datetime import datetime
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_AI_PROVIDER = "ollama"

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _env_provider() -> str:
    return os.environ.get("AI_PROVIDER", DEFAULT_AI_PROVIDER).strip().lower()


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()


def _http_json(method: str, url: str, payload: dict | None = None, timeout: int = 10) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_ai_provider_status() -> dict:
    """Return the configured AI provider and whether it is ready."""
    # v3 keeps narrative output deterministic even after research validation;
    # validation is not authorization for an LLM to derive an action label.
    return {
        "provider": "deterministic",
        "ready": True,
        "label": "Structured shadow report",
        "message": "Canonical values only; generative action narratives are disabled by policy.",
    }
def _build_prompt(
    fundamental_data: dict,
    technical_data: dict,
    ticker: str,
    bands: dict | None = None,
    seasonality: dict | None = None,
    comparison_summary: str | None = None,
) -> str:
    """Build the Super Prompt combining all cross-tab data."""

    sector = fundamental_data.get("sector_matched", "N/A")

    # ── Fundamental section ───────────────────────────────────────────────────
    fundamental_section = (
        f"  Sector: {sector}\n"
        f"  PE Ratio: {fundamental_data.get('pe_value', 'N/A')} — {fundamental_data.get('pe_label', 'N/A')} "
        f"(Sector range: {fundamental_data.get('pe_range', 'N/A')})\n"
        f"  PBV Ratio: {fundamental_data.get('pbv_value', 'N/A')} — {fundamental_data.get('pbv_label', 'N/A')} "
        f"(Sector range: {fundamental_data.get('pbv_range', 'N/A')})\n"
        f"  Overall Valuation Signal: {fundamental_data.get('overall', 'N/A')}"
    )

    # ── Technical section ─────────────────────────────────────────────────────
    macd_val = technical_data.get("macd")
    macd_sig = technical_data.get("macd_signal_val")
    macd_hist = technical_data.get("macd_hist")
    macd_signal_text = technical_data.get("macd_signal", "N/A")
    macd_params = technical_data.get("macd_params", (12, 26, 9))
    score = technical_data.get("technical_score")
    confidence = technical_data.get("confidence")
    entry_zone = technical_data.get("entry_zone", ("N/A", "N/A"))
    stop_loss = technical_data.get("stop_loss")
    take_profit = technical_data.get("take_profit")
    rr = technical_data.get("risk_reward")

    technical_section = (
        f"  Adaptive Profile: {technical_data.get('profile_label', 'N/A')}\n"
        f"  Profile Reason: {technical_data.get('profile_reason', 'N/A')}\n"
        f"  Preferred Technical Horizon: {technical_data.get('horizon', 'N/A')}\n"
        f"  Technical Score: {f'{score:.0f}/100' if score is not None else 'N/A'} — "
        f"{technical_data.get('recommendation', 'N/A')} "
        f"(Confidence: {f'{confidence:.0f}%' if confidence is not None else 'N/A'})\n"
        f"  Score Components: {technical_data.get('score_components', 'N/A')}\n"
        f"  RSI({technical_data.get('rsi_period', 14)}): {technical_data.get('rsi', 'N/A')} — "
        f"{technical_data.get('rsi_signal', 'N/A')}\n"
        f"  MACD Line: {f'{macd_val:.2f}' if macd_val is not None else 'N/A'}\n"
        f"  MACD Signal Line: {f'{macd_sig:.2f}' if macd_sig is not None else 'N/A'}\n"
        f"  MACD Histogram: {f'{macd_hist:+.2f}' if macd_hist is not None else 'N/A'}\n"
        f"  MACD Momentum {macd_params}: {macd_signal_text}\n"
        f"  Fast MA({technical_data.get('fast_ma_period', 'N/A')}): {technical_data.get('fast_ma', 'N/A')}\n"
        f"  Slow MA({technical_data.get('slow_ma_period', 'N/A')}): {technical_data.get('slow_ma', 'N/A')}\n"
        f"  SMA Trend Signal: {technical_data.get('sma_signal', 'N/A')}\n"
        f"  Adaptive Support ({technical_data.get('sr_lookback_days', 'N/A')} bars): {technical_data.get('support', 'N/A')}\n"
        f"  Adaptive Resistance ({technical_data.get('sr_lookback_days', 'N/A')} bars): {technical_data.get('resistance', 'N/A')}\n"
        f"  Price Position Signal: {technical_data.get('sr_signal', 'N/A')}\n"
        f"  ATR(14): {technical_data.get('atr', 'N/A')} ({technical_data.get('atr_pct', 'N/A')}%) "
        f"— {technical_data.get('atr_signal', 'N/A')}\n"
        f"  Realized Volatility: {technical_data.get('realized_volatility', 'N/A')}%\n"
        f"  Suggested Entry Zone: {entry_zone[0]} - {entry_zone[1]}\n"
        f"  Suggested Stop Loss: {f'Rp {stop_loss:,.0f}' if stop_loss is not None else 'N/A'}\n"
        f"  Suggested Take Profit: {f'Rp {take_profit:,.0f}' if take_profit is not None else 'N/A'}\n"
        f"  Risk/Reward: {f'{rr:.2f}R' if rr is not None else 'N/A'}"
    )

    # ── Smart Money Flow section ─────────────────────────────────────────────
    mfi_v = technical_data.get("mfi")
    smart_money_section = (
        f"  MFI(14): {f'{mfi_v:.1f}' if mfi_v is not None else 'N/A'} "
        f"— {technical_data.get('mfi_signal', 'N/A')}\n"
        f"  OBV Trend: {technical_data.get('obv_signal', 'N/A')}\n"
        f"  Smart Money Verdict: {technical_data.get('smart_money', 'N/A')}"
    )

    # ── Valuation Bands section ───────────────────────────────────────────────
    if bands:
        pe_band = bands.get("pe")
        pbv_band = bands.get("pbv")
        band_lines = []
        if pe_band:
            band_lines.append(
                f"  PE Band — Mean: {pe_band['pe_mean']:.2f}x, "
                f"Current: {pe_band['current_pe']:.2f}x, "
                f"SD Position: {pe_band['sd_position']:+.2f} SD  "
                f"({'Undervalued' if pe_band['sd_position'] < 0 else 'Overvalued'} vs history)"
            )
        else:
            band_lines.append("  PE Band — Insufficient data")
        if pbv_band:
            band_lines.append(
                f"  PBV Band — Mean: {pbv_band['pbv_mean']:.2f}x, "
                f"Current: {pbv_band['current_pbv']:.2f}x, "
                f"SD Position: {pbv_band['sd_position']:+.2f} SD  "
                f"({'Undervalued' if pbv_band['sd_position'] < 0 else 'Overvalued'} vs history)"
            )
        else:
            band_lines.append("  PBV Band — Insufficient data")
        valuation_band_section = "\n".join(band_lines)
    else:
        valuation_band_section = "  No valuation band data available."

    # ── Seasonality section (current month) ───────────────────────────────────
    current_month = datetime.now().month
    current_month_name = _MONTH_NAMES[current_month - 1]
    has_seasonality = (
        bool(seasonality)
        and hasattr(seasonality.get("monthly_avg", {}), "empty")
        and not seasonality.get("monthly_avg", {}).empty
    )
    if has_seasonality:
        avg = seasonality["monthly_avg"]
        pos = seasonality["monthly_pos_pct"]
        month_avg = avg.get(current_month, None)
        month_win = pos.get(current_month, None)
        if month_avg is not None and month_win is not None:
            bias = "bullish" if month_avg > 0 else "bearish"
            seasonality_section = (
                f"  Current Month: {current_month_name}\n"
                f"  Historical Avg Return for {current_month_name}: {month_avg:+.2f}%\n"
                f"  Win Rate (positive closes): {month_win:.0f}%\n"
                f"  Historical Bias: {bias.upper()}"
            )
        else:
            seasonality_section = f"  Current Month: {current_month_name}\n  Insufficient seasonality data."
    else:
        seasonality_section = f"  Current Month: {current_month_name}\n  No seasonality data available."

    # ── Competitor section ────────────────────────────────────────────────────
    comparison_section = (
        f"  {comparison_summary}"
        if comparison_summary
        else "  No comparison data available (user has not run a comparison)."
    )

    # ── Assemble the Super Prompt ─────────────────────────────────────────────
    prompt = f"""\
You are a Senior Equity Research Analyst covering the Indonesia Stock Exchange (IDX). \
Prepare a formal equity research memorandum for {ticker} in the {sector} sector. \
Today's date is {datetime.now().strftime('%B %d, %Y')}.

Analyze ALL data sections below holistically before writing.

---

**1. Fundamentals:**
{fundamental_section}

**2. Technical Indicators (Adaptive horizon, RSI, MACD, MA, Support/Resistance, ATR):**
{technical_section}

**3. Smart Money Flow (MFI + OBV):**
{smart_money_section}

**4. Historical Valuation Bands (PE & PBV vs ±1 SD / ±2 SD):**
{valuation_band_section}

**5. Monthly Seasonality — 10-Year History:**
{seasonality_section}

**6. Competitive Standing:**
{comparison_section}

---

Format your response as a Professional Investment Memorandum using exactly the \
seven sections below. Use bold all-caps headers exactly as shown. No emojis. \
Write in complete, dense paragraphs.

**INVESTMENT THESIS**
State whether this stock is a BUY, HOLD, or SELL. Provide a concise justification \
integrating valuation and price momentum.

**VALUATION ANALYSIS**
Compare current PE and PBV against both sector norms and the stock's own historical \
SD-band positions. Assess whether the current level represents a genuine discount \
or a potential value trap.

**TECHNICAL SETUP**
First state whether the adaptive profile and preferred horizon fit the stock's \
sector/volatility character. Interpret technical score, confidence, MACD momentum, \
RSI level, and adaptive MA trend. Comment on proximity to key Support and \
Resistance levels and contextualize ATR-based volatility.

**SMART MONEY FLOW**
Interpret MFI and OBV data to assess whether price moves are supported by \
institutional volume accumulation or distribution. Note any divergence between \
price direction and volume flow.

**SEASONALITY & TIMING**
Assess whether {current_month_name} is historically favorable for this stock. \
Cite average monthly return and win rate. Provide a clear timing recommendation.

**ACTIONABLE PLAN**
Based on Support, Resistance, ATR, and valuation bands, state:
- Entry Price — suggested entry zone with rationale
- Take Profit (TP) — target level
- Stop Loss (SL) — hard cut-loss level
Use the suggested technical plan when it is consistent with the setup; otherwise \
explain why you override it. Format all price levels as "Rp X,XXX". Include a \
one-line risk/reward summary.

**FINAL VERDICT: [BUY / HOLD / SELL]** — One sentence.
"""
    return prompt


def _fmt_price(value) -> str:
    return "N/A" if value is None else f"Rp {value:,.0f}"


def _build_deterministic_report(
    fundamental_data: dict,
    technical_data: dict,
    ticker: str,
    seasonality: dict | None = None,
) -> str:
    """Build a useful report without an LLM so the app remains fully local."""
    score = technical_data.get("technical_score")
    score_text = f"{score:.0f}/100" if score is not None else "N/A"
    confidence = technical_data.get("confidence")
    confidence_text = f"{confidence:.0f}%" if confidence is not None else "N/A"
    entry_zone = technical_data.get("entry_zone", ("N/A", "N/A"))
    rr = technical_data.get("risk_reward")

    # Narratives never derive an action. The gated decision engine is the only
    # authority for policy labels, and the Yahoo compatibility path is shadow.
    final_verdict = fundamental_data.get("decision_label", "RESEARCH_ONLY")

    current_month = datetime.now().month
    month_name = _MONTH_NAMES[current_month - 1]
    seasonality_line = "Seasonality data is unavailable."
    if seasonality and hasattr(seasonality.get("monthly_avg", {}), "get"):
        avg = seasonality.get("monthly_avg")
        pos = seasonality.get("monthly_pos_pct")
        month_avg = avg.get(current_month, None)
        month_win = pos.get(current_month, None)
        if month_avg is not None and month_win is not None:
            seasonality_line = (
                f"{month_name} historical average return is {month_avg:+.2f}% "
                f"with {month_win:.0f}% positive-close frequency."
            )

    return f"""\
> Local deterministic report. No LLM was used.

**INVESTMENT THESIS**
{ticker} is **{final_verdict}**. The sections below describe evidence and do not alter that gated label. Technical score is **{score_text}** with **{confidence_text}** data confidence, using the **{technical_data.get('profile_label', 'N/A')}** profile and **{technical_data.get('horizon', 'N/A')}** horizon.

**VALUATION ANALYSIS**
PE is **{fundamental_data.get('pe_value', 'N/A')}** ({fundamental_data.get('pe_label', 'N/A')}) and PBV is **{fundamental_data.get('pbv_value', 'N/A')}** ({fundamental_data.get('pbv_label', 'N/A')}). Overall valuation signal: **{fundamental_data.get('overall', 'N/A')}**.

**TECHNICAL SETUP**
Trend: {technical_data.get('sma_signal', 'N/A')}. Momentum: RSI {technical_data.get('rsi', 'N/A')} and {technical_data.get('macd_signal', 'N/A')}. Volatility: ATR {technical_data.get('atr_pct', 'N/A')}% ({technical_data.get('atr_signal', 'N/A')}).

**SMART MONEY FLOW**
{technical_data.get('smart_money', 'N/A')} MFI signal: {technical_data.get('mfi_signal', 'N/A')}. OBV signal: {technical_data.get('obv_signal', 'N/A')}.

**SEASONALITY & TIMING**
{seasonality_line}

**RESEARCH RISK LEVELS**
- Observed entry zone — {entry_zone[0]} - {entry_zone[1]}
- Technical upside reference — {_fmt_price(technical_data.get('take_profit'))}
- Technical invalidation reference — {_fmt_price(technical_data.get('stop_loss'))}
Risk/reward: {f'{rr:.2f}R' if rr is not None else 'N/A'}.

**POLICY LABEL: {final_verdict}** — Only the structured gate engine may change this label.
"""


def _generate_with_ollama(prompt: str) -> str:
    timeout = int(os.environ.get("OLLAMA_TIMEOUT", "180"))
    payload = {
        "model": _ollama_model(),
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a careful IDX equity research analyst. "
                    "Use only the supplied data. Do not invent prices, ratios, or news."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": float(os.environ.get("OLLAMA_TEMPERATURE", "0.2")),
            "top_p": 0.9,
            "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "8192")),
        },
    }
    data = _http_json("POST", f"{_ollama_base_url()}/api/chat", payload=payload, timeout=timeout)
    return data.get("message", {}).get("content", "").strip() or "Ollama returned an empty response."


def _generate_with_gemini(prompt: str) -> str:
    from google.api_core.exceptions import ResourceExhausted
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "> Gemini API key is not configured."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))
        response = model.generate_content(prompt)
        return response.text
    except ResourceExhausted:
        return (
            "> Gemini quota limit reached. The app can still use the local "
            "deterministic report or Ollama if configured."
        )


def generate_ai_analysis(
    fundamental_data: dict,
    technical_data: dict,
    ticker: str,
    bands: dict | None = None,
    seasonality: dict | None = None,
    comparison_summary: str | None = None,
) -> str:
    """Render a Markdown analysis without delegating facts or labels to an LLM.

    Parameters
    ----------
    fundamental_data : dict from ``analyze_fundamental()``
    technical_data   : dict from ``analyze_technical()``
    ticker           : resolved ticker string
    bands            : dict from ``compute_valuation_bands()`` (optional)
    seasonality      : dict from ``compute_seasonality()`` (optional)
    comparison_summary : one-line summary from comparison tab (optional)
    """
    # During the reliability rollout only a deterministic rendering is allowed.
    # This makes it impossible for an LLM to mutate numbers, action labels or
    # warnings. Legacy private provider helpers remain unreachable from this
    # public entry point and require separate review before any future use.
    fallback = _build_deterministic_report(
        fundamental_data,
        technical_data,
        ticker,
        seasonality=seasonality,
    )
    return fallback
