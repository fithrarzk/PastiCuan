import os
import sys
import logging
from dotenv import load_dotenv
import pandas as pd
import yfinance as yf

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN is not set in environment or .env file.")
    sys.exit(1)

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from data.extended import get_extended_data
from analysis.technical import analyze_technical
from analysis.fundamental import analyze_fundamental
from analysis.valuation_bands import compute_valuation_bands
from analysis.seasonality import compute_seasonality
from analysis.backtest import backtest_technical_strategy
from analysis.decision import build_decision_report
from telegram_utils.chart_generator import generate_telegram_chart

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

POPULAR_TICKERS = ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNTR", "ICBP", "AMRT", "ADRO"]


def _clean_ticker(text: str) -> str:
    if not text:
        return ""
    ticker = text.strip().split()[0].upper()
    ticker = ticker.replace(".JK", "")
    return ticker


def _compute_liquidity(history):
    if history is None or history.empty:
        return {"avg_volume": None, "avg_value": None}
    window = history.tail(min(len(history), 60))
    avg_volume = float(window["Volume"].fillna(0).mean()) if "Volume" in window else None
    avg_value = (
        float((window["Close"] * window["Volume"].fillna(0)).mean())
        if {"Close", "Volume"}.issubset(window.columns)
        else None
    )
    return {"avg_volume": avg_volume, "avg_value": avg_value}


def _run_full_analysis(ticker_raw: str, period: str = "3y"):
    data = get_extended_data(ticker_raw, period=period)
    if data.get("error"):
        return None, data["error"]

    history = data["history"]
    info = data["info"]
    sector = data["basic"].get("sector", "N/A")

    tech = analyze_technical(history, sector=sector, info=info)
    fund = analyze_fundamental(
        info,
        sector,
        quarterly_income=data["quarterly_income"],
        quarterly_balance=data["quarterly_balance"],
    )
    bands = compute_valuation_bands(
        history,
        data["quarterly_income"],
        data["quarterly_balance"],
        info,
    )
    seasonality = compute_seasonality(history)
    backtest = backtest_technical_strategy(history, sector=sector, info=info)
    
    if backtest.get("setup_confidence") is not None:
        base_confidence = tech.get("confidence") or 50
        tech["data_confidence"] = base_confidence
        tech["historical_confidence"] = backtest["setup_confidence"]
        tech["confidence"] = min(95, base_confidence * 0.55 + backtest["setup_confidence"] * 0.45)

    liquidity = _compute_liquidity(history)
    decision = build_decision_report(
        tech,
        fund,
        bands=bands,
        seasonality=seasonality,
        backtest=backtest,
        liquidity=liquidity,
    )

    return {
        "data": data,
        "tech": tech,
        "fund": fund,
        "bands": bands,
        "seasonality": seasonality,
        "backtest": backtest,
        "liquidity": liquidity,
        "decision": decision,
    }, None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies to /start and /help with the main menu and instructions."""
    msg = (
        "📈 *PastiCuan — IDX Equity Research Bot*\n\n"
        "Welcome! Get instant technical analysis, decision scores, charts, and stock scans for Indonesian equities directly in Telegram.\n\n"
        "*Available Commands:*\n"
        "• `/ta <ticker>` — Adaptive Technical Analysis (e.g. `/ta BBCA`)\n"
        "• `/decision <ticker>` — Multi-factor Decision Matrix (e.g. `/decision TLKM`)\n"
        "• `/chart <ticker>` — Technical Candlestick & Indicator Chart (e.g. `/chart BMRI`)\n"
        "• `/scan` — Scan LQ45 / top IDX stocks for accumulation signals\n"
        "• `/help` — Display this command menu\n\n"
        "_Tip: Ticker symbols automatically default to IDX (.JK suffix)._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


async def ta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Technical Analysis for a given ticker."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/ta BBCA`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(f"⏳ Analyzing technicals for *{ticker_symbol}.JK*...", parse_mode=ParseMode.MARKDOWN)

    results, error = _run_full_analysis(ticker_symbol)
    if error:
        await update.message.reply_text(f"❌ *Error analyzing {ticker_symbol}:*\n{error}", parse_mode=ParseMode.MARKDOWN)
        return

    tech = results["tech"]
    data = results["data"]
    history = data["history"]
    basic = data["basic"]

    valid_close = history["Close"].dropna() if not history.empty else pd.Series()
    latest_close = float(valid_close.iloc[-1]) if not valid_close.empty else 0
    prev_close = float(valid_close.iloc[-2]) if len(valid_close) > 1 else latest_close
    pct_change = (latest_close - prev_close) / prev_close * 100 if prev_close else 0
    chg_sign = "+" if pct_change >= 0 else ""


    score = tech.get("technical_score", 0)
    rec = tech.get("recommendation", "N/A")
    conf = tech.get("confidence", 0)
    entry_low, entry_high = tech.get("entry_zone", ("N/A", "N/A"))
    stop_loss = tech.get("stop_loss")
    take_profit = tech.get("take_profit")
    rr = tech.get("risk_reward")

    stop_str = f"Rp {stop_loss:,.0f}" if stop_loss else "N/A"
    tp_str = f"Rp {take_profit:,.0f}" if take_profit else "N/A"
    rr_str = f"{rr:.2f}" if rr else "N/A"

    msg = (
        f"📈 *{data['ticker']}* — {basic.get('longName', '')}\n"
        f"💰 *Price:* Rp {latest_close:,.0f} ({chg_sign}{pct_change:.2f}%)\n"
        f"🏷️ *Profile:* {tech.get('profile_label', 'Balanced')}\n"
        f"───────────────\n"
        f"📊 *Technical Score:* `{score:.1f} / 100` (Conf: `{conf:.0f}%`)\n"
        f"🚦 *Signal:* {rec}\n\n"
        f"🎯 *Trading Setup:*\n"
        f"• *Entry Zone:* `{entry_low}` – `{entry_high}`\n"
        f"• *Stop Loss:* `{stop_str}`\n"
        f"• *Take Profit:* `{tp_str}`\n"
        f"• *Risk / Reward:* `{rr_str}`\n\n"
        f"🔍 *Indicator Signals:*\n"
        f"• *RSI ({tech.get('rsi_period', 14)}):* `{tech.get('rsi', 0):.1f}` — {tech.get('rsi_signal', '')}\n"
        f"• *Trend:* {tech.get('sma_signal', '')}\n"
        f"• *MACD:* {tech.get('macd_signal', '')}\n"
        f"• *Support/Res:* {tech.get('sr_signal', '')}\n"
        f"• *Smart Money:* {tech.get('smart_money', '')}\n\n"
        f"💡 _Send `/chart {ticker_symbol}` to get the visual candlestick chart!_"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def decision_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Multi-factor Decision Matrix analysis."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/decision TLKM`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(f"⏳ Generating Decision Report for *{ticker_symbol}.JK*...", parse_mode=ParseMode.MARKDOWN)

    results, error = _run_full_analysis(ticker_symbol)
    if error:
        await update.message.reply_text(f"❌ *Error evaluating {ticker_symbol}:*\n{error}", parse_mode=ParseMode.MARKDOWN)
        return

    decision = results["decision"]
    data = results["data"]
    history = data["history"]
    valid_close = history["Close"].dropna() if not history.empty else pd.Series()
    latest_close = float(valid_close.iloc[-1]) if not valid_close.empty else 0


    comp_score = decision.get("composite_score", 0)
    verdict = decision.get("action_verdict", "HOLD")
    pill = decision.get("verdict_pill", "🟡 HOLD")
    conf = decision.get("confidence", 0)

    cat_scores = decision.get("category_scores", {})
    tech_s = cat_scores.get("technical", {}).get("score", 0)
    fund_s = cat_scores.get("fundamental", {}).get("score", 0)
    val_s = cat_scores.get("valuation", {}).get("score", 0)
    seas_s = cat_scores.get("seasonality", {}).get("score", 0)

    summary_bullets = decision.get("executive_bullets", [])
    bullet_text = "\n".join([f"• {b}" for b in summary_bullets[:4]]) if summary_bullets else "• Multi-factor data evaluated cleanly."

    msg = (
        f"🏛️ *Decision Matrix:* *{data['ticker']}*\n"
        f"💰 *Current Price:* Rp {latest_close:,.0f}\n"
        f"───────────────\n"
        f"⚡ *Composite Score:* `{comp_score:.1f} / 100` (Conf: `{conf:.0f}%`)\n"
        f"🎯 *Action Verdict:* {pill}\n\n"
        f"📐 *Pillar Breakdown:*\n"
        f"• *Technical:* `{tech_s:.1f}/100`\n"
        f"• *Fundamental:* `{fund_s:.1f}/100`\n"
        f"• *Valuation:* `{val_s:.1f}/100`\n"
        f"• *Seasonality:* `{seas_s:.1f}/100`\n\n"
        f"📋 *Executive Key Points:*\n"
        f"{bullet_text}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renders and sends technical chart image."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/chart BMRI`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(f"📊 Rendering technical chart for *{ticker_symbol}.JK*...", parse_mode=ParseMode.MARKDOWN)

    results, error = _run_full_analysis(ticker_symbol)
    if error:
        await update.message.reply_text(f"❌ *Error rendering chart for {ticker_symbol}:*\n{error}", parse_mode=ParseMode.MARKDOWN)
        return

    buf = generate_telegram_chart(results["tech"], results["data"]["ticker"])
    if buf is None:
        await update.message.reply_text("❌ Could not generate chart image due to missing data.", parse_mode=ParseMode.MARKDOWN)
        return

    caption = (
        f"📈 *{results['data']['ticker']}* Chart\n"
        f"Signal: {results['tech'].get('recommendation', 'N/A')}"
    )
    await update.message.reply_photo(photo=buf, caption=caption, parse_mode=ParseMode.MARKDOWN)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scans popular IDX stocks and ranks them by technical score."""
    await update.message.reply_text("🔎 Scanning top IDX stocks (LQ45 shortlist)... Please wait 10-15 seconds.", parse_mode=ParseMode.MARKDOWN)

    scanned = []
    for symbol in POPULAR_TICKERS:
        try:
            results, err = _run_full_analysis(symbol, period="1y")
            if not err and results:
                tech = results["tech"]
                valid_c = results["data"]["history"]["Close"].dropna()
                close = float(valid_c.iloc[-1]) if not valid_c.empty else 0

                scanned.append({
                    "ticker": symbol,
                    "score": tech.get("technical_score", 0),
                    "rec": tech.get("recommendation", "N/A"),
                    "price": close,
                })
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")

    scanned.sort(key=lambda x: x["score"], reverse=True)

    lines = ["🔎 *IDX Market Scanner — Top Setup Rankings*\n"]
    for i, item in enumerate(scanned, 1):
        emoji = "🟢" if item["score"] >= 60 else ("🟡" if item["score"] >= 45 else "🔴")
        lines.append(
            f"{i}. {emoji} *{item['ticker']}*: `{item['score']:.1f}/100` — Rp {item['price']:,.0f}\n"
            f"   └ _{item['rec']}_"
        )

    lines.append("\n_Use `/ta <ticker>` or `/chart <ticker>` for deep dive._")
    msg = "\n".join(lines)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


def main():
    logger.info("Starting PastiCuan Telegram Bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler(["ta", "analyze"], ta_command))
    app.add_handler(CommandHandler(["decision"], decision_command))
    app.add_handler(CommandHandler(["chart"], chart_command))
    app.add_handler(CommandHandler(["scan"], scan_command))

    print("🚀 PastiCuan Telegram Bot is running! Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
