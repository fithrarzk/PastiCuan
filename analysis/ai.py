"""
Gemini AI-powered stock analysis — Super Prompt.

Uses Google's Generative AI (Gemini 2.0 Flash) to produce a markdown-formatted
investment summary that combines fundamental, technical, valuation-band,
seasonality, and competitor data.
"""

import os
from datetime import datetime

from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

load_dotenv()

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


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
    if seasonality and not seasonality.get("monthly_avg", {}).empty if hasattr(seasonality.get("monthly_avg", {}), "empty") else not seasonality:
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


def generate_ai_analysis(
    fundamental_data: dict,
    technical_data: dict,
    ticker: str,
    bands: dict | None = None,
    seasonality: dict | None = None,
    comparison_summary: str | None = None,
) -> str:
    """Send all cross-tab data to Gemini and return a Markdown analysis.

    Parameters
    ----------
    fundamental_data : dict from ``analyze_fundamental()``
    technical_data   : dict from ``analyze_technical()``
    ticker           : resolved ticker string
    bands            : dict from ``compute_valuation_bands()`` (optional)
    seasonality      : dict from ``compute_seasonality()`` (optional)
    comparison_summary : one-line summary from comparison tab (optional)
    """

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return (
            "> ⚠️ **Gemini API key not configured.**\n>\n"
            "> Set `GEMINI_API_KEY` in your `.env` file to enable AI-powered analysis."
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = _build_prompt(
            fundamental_data, technical_data, ticker,
            bands=bands, seasonality=seasonality,
            comparison_summary=comparison_summary,
        )
        response = model.generate_content(prompt)
        return response.text

    except ResourceExhausted:
        return (
            "> ⚠️ **Quota limit reached (429 – Resource Exhausted).**\n>\n"
            "> Gemini's free-tier rate limit has been hit. "
            "> Please **wait 60 seconds** and try again.\n>\n"
            "> If this keeps happening, consider spacing out requests "
            "or upgrading your Gemini API plan."
        )

    except Exception as exc:  # noqa: BLE001
        return (
            f"> ⚠️ **AI analysis failed.**\n>\n"
            f"> `{type(exc).__name__}: {exc}`\n>\n"
            f"> Please check your API key and network connection."
        )
