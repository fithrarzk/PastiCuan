"""
Gemini AI-powered stock analysis.

Uses Google's Generative AI (Gemini) to produce a markdown-formatted
investment summary from fundamental and technical data.
"""

import os

from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()


def _build_prompt(fundamental_data: dict, technical_data: dict, ticker: str) -> str:
    """Build a structured prompt for the Gemini model."""

    fundamental_section = (
        f"  Sector: {fundamental_data.get('sector_matched', 'N/A')}\n"
        f"  PE Ratio: {fundamental_data.get('pe_value', 'N/A')} — {fundamental_data.get('pe_label', 'N/A')} "
        f"(Sector range: {fundamental_data.get('pe_range', 'N/A')})\n"
        f"  PBV Ratio: {fundamental_data.get('pbv_value', 'N/A')} — {fundamental_data.get('pbv_label', 'N/A')} "
        f"(Sector range: {fundamental_data.get('pbv_range', 'N/A')})\n"
        f"  Overall Valuation: {fundamental_data.get('overall', 'N/A')}"
    )

    technical_section = (
        f"  RSI(14): {technical_data.get('rsi', 'N/A')} — {technical_data.get('rsi_signal', 'N/A')}\n"
        f"  SMA 50: {technical_data.get('sma50', 'N/A')}\n"
        f"  SMA 200: {technical_data.get('sma200', 'N/A')}\n"
        f"  SMA Signal: {technical_data.get('sma_signal', 'N/A')}\n"
        f"  Support: {technical_data.get('support', 'N/A')}\n"
        f"  Resistance: {technical_data.get('resistance', 'N/A')}\n"
        f"  Support/Resistance Signal: {technical_data.get('sr_signal', 'N/A')}\n"
        f"  ATR(14): {technical_data.get('atr', 'N/A')} ({technical_data.get('atr_pct', 'N/A')}%)\n"
        f"  ATR Signal: {technical_data.get('atr_signal', 'N/A')}"
    )

    prompt = (
        f"You are a professional stock analyst. "
        f"Based on this data for **{ticker}**:\n\n"
        f"**Fundamental Data:**\n{fundamental_section}\n\n"
        f"**Technical Data:**\n{technical_section}\n\n"
        f"Provide a concise summary covering:\n"
        f"1. Is it a **Good** or **Bad** time to buy?\n"
        f"2. Analysis of the value (undervalued / overvalued).\n"
        f"3. Technical trend analysis.\n"
        f"4. Recommended **Take Profit** and **Cut Loss** levels based on the "
        f"calculated Support/Resistance.\n\n"
        f"Format the output in Markdown suitable for Streamlit rendering. "
        f"Use headers, bullet points, and bold text for clarity."
    )

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
    except Exception as exc:  # noqa: BLE001
        return (
            f"> ⚠️ **AI analysis failed.**\n>\n"
            f"> `{type(exc).__name__}: {exc}`\n>\n"
            f"> Please check your API key and network connection."
        )
