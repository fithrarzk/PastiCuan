"""
Gemini AI-powered stock analysis.

Uses Google's Generative AI (Gemini) to produce a markdown-formatted
investment summary from fundamental and technical data.
"""

import os

from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

load_dotenv()


def _build_prompt(fundamental_data: dict, technical_data: dict, ticker: str) -> str:
    """Build a structured, senior-analyst-style prompt for the Gemini model."""

    sector = fundamental_data.get("sector_matched", "N/A")

    fundamental_section = (
        f"  Sector: {sector}\n"
        f"  PE Ratio: {fundamental_data.get('pe_value', 'N/A')} — {fundamental_data.get('pe_label', 'N/A')} "
        f"(Sector range: {fundamental_data.get('pe_range', 'N/A')})\n"
        f"  PBV Ratio: {fundamental_data.get('pbv_value', 'N/A')} — {fundamental_data.get('pbv_label', 'N/A')} "
        f"(Sector range: {fundamental_data.get('pbv_range', 'N/A')})\n"
        f"  Overall Valuation Signal: {fundamental_data.get('overall', 'N/A')}"
    )

    technical_section = (
        f"  RSI(14): {technical_data.get('rsi', 'N/A')} — {technical_data.get('rsi_signal', 'N/A')}\n"
        f"  SMA 50: {technical_data.get('sma50', 'N/A')}\n"
        f"  SMA 200: {technical_data.get('sma200', 'N/A')}\n"
        f"  SMA Trend Signal: {technical_data.get('sma_signal', 'N/A')}\n"
        f"  3-Month Support: {technical_data.get('support', 'N/A')}\n"
        f"  3-Month Resistance: {technical_data.get('resistance', 'N/A')}\n"
        f"  Price Position Signal: {technical_data.get('sr_signal', 'N/A')}\n"
        f"  ATR(14): {technical_data.get('atr', 'N/A')} ({technical_data.get('atr_pct', 'N/A')}%) "
        f"— {technical_data.get('atr_signal', 'N/A')}"
    )

    prompt = f"""\
Act as a Senior Equity Research Analyst with 20 years of experience on the IDX \
(Indonesia Stock Exchange). Analyze the following data for ticker **{ticker}** \
in the **{sector}** sector.

---

**Fundamentals:**
{fundamental_section}

**Technicals (RSI, SMA, Support/Resistance):**
{technical_section}

---

Please provide a structured report using the four sections below. \
Use bold Markdown headers for each section. Be professional, objective, \
and slightly witty like a seasoned floor trader — concise but not dry.

## 1. 📌 Investment Thesis
A brief, punchy summary: is this stock a **Buy**, **Hold**, or **Sell** right now, \
and why in one sentence?

## 2. 🔍 Valuation Deep Dive
Compare the current PE and PBV against sector norms. Is this a genuine discount \
worth acting on, or could it be a value trap? Mention what the overall valuation \
signal implies.

## 3. 📈 Technical Setup
Interpret price action relative to SMA 50 and SMA 200 (Golden Cross / Death Cross). \
Comment on RSI momentum and whether the stock is near a key support or resistance \
level. Factor in ATR volatility when assessing risk.

## 4. 🎯 Actionable Plan
Based strictly on the calculated Support and Resistance levels, provide:
- **Entry Price** — suggested entry zone
- **Take Profit** — target level with rationale
- **Cut Loss** — hard stop-loss level

Format all price levels clearly (e.g. "Rp 9,500"). \
End with a one-line risk/reward summary.
"""

    return prompt


def generate_ai_analysis(
    fundamental_data: dict,
    technical_data: dict,
    ticker: str,
) -> str:
    """Send fundamental & technical data to Gemini and return a Markdown analysis.

    Parameters
    ----------
    fundamental_data : dict
        Output of ``analyze_fundamental()``.
    technical_data : dict
        Output of ``analyze_technical()``.
    ticker : str
        Stock ticker symbol (e.g. ``"BBCA.JK"``).

    Returns
    -------
    str
        Markdown-formatted AI analysis, or an error message on failure.
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
        prompt = _build_prompt(fundamental_data, technical_data, ticker)
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
