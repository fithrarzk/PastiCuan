import os
import sys
import logging
from dotenv import load_dotenv
import pandas as pd
import yfinance as yf

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from data.extended import get_extended_data
from analysis.engine import run_analysis_bundle
from analysis.quant import compute_quant_factors
from analysis.portfolio import optimize_portfolio
from analysis.presentation import decision_view, display_number


# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


class _SecretRedactionFilter(logging.Filter):
    """Prevent bot/webhook credentials from appearing in provider logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        for value in (TELEGRAM_BOT_TOKEN, os.getenv("TELEGRAM_WEBHOOK_SECRET")):
            if value:
                rendered = rendered.replace(value, "<redacted>")
        record.msg = rendered
        record.args = ()
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_SecretRedactionFilter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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


def _run_full_analysis(ticker_raw: str, period: str = "3y", *, include_backtest: bool = False):
    data = get_extended_data(ticker_raw, period=period)
    if data.get("error"):
        return None, data["error"]

    analysis = run_analysis_bundle(data, include_backtest=include_backtest)

    return {
        "data": data,
        "tech": analysis["tech"],
        "fund": analysis["fund"],
        "bands": analysis["bands"],
        "seasonality": analysis["seasonality"],
        "backtest": analysis["backtest"],
        "liquidity": analysis["liquidity"],
        "decision": analysis["decision"],
        "bundle": analysis["bundle"].to_dict(),
    }, None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies to /start and /help with the main menu and instructions."""
    msg = (
        "📈 *PastiCuan — IDX Equity Research Bot*\n\n"
        "Welcome! Get instant technical analysis, decision scores, charts, and stock scans for Indonesian equities directly in Telegram.\n\n"
        "*Available Commands:*\n"
        "• `/ta <ticker>` — Adaptive Technical Analysis (e.g. `/ta BBCA`)\n"
        "• `/fund <ticker>` — Detailed Fundamental & Valuation Report (e.g. `/fund TLKM`)\n"
        "• `/quant <ticker>` — Level 2 Multi-Factor Quant Model (e.g. `/quant BBCA`)\n"
        "• `/portfolio <t1> <t2> ...` — Markowitz Portfolio Optimizer (e.g. `/portfolio BBCA TLKM BMRI ICBP`)\n"
        "• `/decision <ticker>` — Multi-factor Decision Matrix (e.g. `/decision BMRI`)\n"
        "• `/chart <ticker>` — Technical Candlestick & Indicator Chart (e.g. `/chart ASII`)\n"
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

    include_backtest = os.getenv("BOT_ENABLE_BACKTEST", "false").lower() == "true"
    results, error = _run_full_analysis(ticker_symbol, include_backtest=include_backtest)
    if error:
        await update.message.reply_text(f"❌ *Error evaluating {ticker_symbol}:*\n{error}", parse_mode=ParseMode.MARKDOWN)
        return

    decision = results["decision"]
    bundle = results["bundle"]
    data = results["data"]
    history = data["history"]
    valid_close = history["Close"].dropna() if not history.empty else pd.Series()
    latest_close = float(valid_close.iloc[-1]) if not valid_close.empty else 0


    view = decision_view(decision)
    bullet_text = "\n".join(f"• {w}" for w in view["warnings"][:4]) or f"• {view['reason']}"

    msg = (
        f"🏛️ *Decision Matrix:* *{data['ticker']}*\n"
        f"💰 *Current Price:* Rp {latest_close:,.0f}\n"
        f"🕒 *As of:* {bundle.get('as_of', 'N/A')} · Model `{bundle.get('analysis_version', 'N/A')}`\n"
        f"───────────────\n"
        f"⚡ *Evidence Score:* `{display_number(view['score'])}` (Coverage: `{view['coverage_pct']:.0f}%`)\n"
        f"🎯 *Policy Label:* {view['label']}\n\n"
        f"📐 *Pillar Breakdown:*\n"
        f"• *Technical:* `{display_number(view['technical'])}`\n"
        f"• *Fundamental:* `{display_number(view['fundamental'])}`\n"
        f"• *Backtest:* `{display_number(view['backtest'])}`\n"
        f"• *Liquidity:* `{display_number(view['liquidity'])}`\n\n"
        f"📋 *Gates & Warnings:*\n"
        f"{bullet_text}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def fund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Fundamental Analysis for a given ticker."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/fund BBCA`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(f"⏳ Evaluating fundamentals for *{ticker_symbol}.JK*...", parse_mode=ParseMode.MARKDOWN)

    results, error = _run_full_analysis(ticker_symbol)
    if error:
        await update.message.reply_text(f"❌ *Error analyzing fundamentals for {ticker_symbol}:*\n{error}", parse_mode=ParseMode.MARKDOWN)
        return

    fund = results["fund"]
    data = results["data"]
    ratios = data.get("ratios", {})

    pe_val = fund.get("pe_value")
    pbv_val = fund.get("pbv_value")
    pe_str = f"{pe_val:.2f}" if isinstance(pe_val, (int, float)) else "N/A"
    pbv_str = f"{pbv_val:.2f}" if isinstance(pbv_val, (int, float)) else "N/A"

    div = fund.get("dividend_yield")
    div_str = f"{div * 100:.2f}%" if isinstance(div, (int, float)) else "N/A"

    roe = fund.get("roe")
    roe_str = f"{roe * 100:.2f}%" if isinstance(roe, (int, float)) else "N/A"

    margin = fund.get("net_margin")
    margin_str = f"{margin * 100:.2f}%" if isinstance(margin, (int, float)) else "N/A"

    q_flags = fund.get("quality_flags", [])
    r_flags = fund.get("risk_flags", [])

    q_text = "\n".join([f"• ✅ {flag}" for flag in q_flags]) if q_flags else "• No major quality flags."
    r_text = "\n".join([f"• ⚠️ {flag}" for flag in r_flags]) if r_flags else "• No major risk flags detected."

    msg = (
        f"🏛️ *{data['ticker']} — Fundamental Report*\n"
        f"Sector: *{data['basic'].get('sector', 'N/A')}*\n"
        f"───────────────\n"
        f"📊 *Fundamental Score:* `{display_number(fund.get('fundamental_score'))}`\n"
        f"🚦 *Verdict:* {fund.get('fundamental_verdict', 'N/A')}\n"
        f"🏷️ *Valuation:* {fund.get('overall', 'N/A')}\n\n"
        f"📈 *Key Financial Ratios:*\n"
        f"• *P/E Ratio:* `{pe_str}` ({fund.get('pe_label', 'N/A')})\n"
        f"• *P/B Ratio:* `{pbv_str}` ({fund.get('pbv_label', 'N/A')})\n"
        f"• *ROE:* `{roe_str}`\n"
        f"• *Net Profit Margin:* `{margin_str}`\n"
        f"• *Dividend Yield:* `{div_str}`\n"
        f"• *Debt-to-Equity:* `{ratios.get('Debt-to-Equity', 'N/A')}`\n\n"
        f"✨ *Quality Drivers:*\n"
        f"{q_text}\n\n"
        f"⚠️ *Risk Alerts:*\n"
        f"{r_text}"
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

    from telegram_utils.chart_generator import generate_telegram_chart

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
    scan_limit = max(1, min(len(POPULAR_TICKERS), int(os.getenv("BOT_SCAN_LIMIT", "5"))))
    for symbol in POPULAR_TICKERS[:scan_limit]:
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


async def quant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Multi-Factor Quant Analysis for a given ticker."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/quant BBCA`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(f"⏳ Running Level 2 Multi-Factor Quant Model for *{ticker_symbol}.JK*...", parse_mode=ParseMode.MARKDOWN)

    results, error = _run_full_analysis(ticker_symbol)
    if error:
        await update.message.reply_text(f"❌ *Error running Quant model for {ticker_symbol}:*\n{error}", parse_mode=ParseMode.MARKDOWN)
        return

    data = results["data"]
    quant = compute_quant_factors(
        info=data.get("info"),
        history=data.get("history"),
        sector=data.get("basic", {}).get("sector"),
        quarterly_income=data.get("quarterly_income"),
        quarterly_balance=data.get("quarterly_balance"),
    )

    factors = quant.get("factors", {})
    val_f = factors.get("value", {})
    qual_f = factors.get("quality", {})
    mom_f = factors.get("momentum", {})
    vol_f = factors.get("low_volatility", {})

    msg = (
        f"🔬 *{data['ticker']} — Level 2 Multi-Factor Quant Report*\n"
        f"Sector: *{data['basic'].get('sector', 'N/A')}*\n"
        f"───────────────\n"
        f"📊 *Composite Quant Score:* `{display_number(quant.get('composite_score'))}`\n"
        f"🎯 *Factor Grade:* `{quant.get('grade', 'N/A')}`\n\n"
        f"📐 *Sub-Factor Breakdown:*\n"
        f"• *Value Factor:* `{display_number(val_f.get('score'))}` (Grade `{val_f.get('grade', 'N/A')}`)\n"
        f"• *Quality Factor:* `{display_number(qual_f.get('score'))}` (Grade `{qual_f.get('grade', 'N/A')}`)\n"
        f"• *Momentum Factor:* `{display_number(mom_f.get('score'))}` (Grade `{mom_f.get('grade', 'N/A')}`)\n"
        f"• *Low Volatility Factor:* `{display_number(vol_f.get('score'))}` (Grade `{vol_f.get('grade', 'N/A')}`)\n\n"
        f"💡 _Try `/portfolio {ticker_symbol} TLKM BMRI ICBP` to optimize capital allocation!_"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs Markowitz Mean-Variance Portfolio Optimization."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "ℹ️ Please specify at least 2 ticker symbols. Example: `/portfolio BBCA TLKM BMRI ICBP`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    tickers_list = [_clean_ticker(t) for t in context.args]
    tickers_str = ", ".join(tickers_list)
    await update.message.reply_text(f"⏳ Running Markowitz Portfolio Optimization for: *{tickers_str}*...", parse_mode=ParseMode.MARKDOWN)

    res = optimize_portfolio(tickers_list, period="1y")
    if res.get("error"):
        await update.message.reply_text(f"❌ *Portfolio Optimization Error:*\n{res['error']}", parse_mode=ParseMode.MARKDOWN)
        return

    allocation = res["min_volatility"]
    weights = allocation["weights"]

    lines = [
        "🧮 *Shrinkage Portfolio Research*\n",
        "🛡️ *Default Risk-Aware Allocation (Minimum Volatility):*"
    ]

    for tk, w in weights.items():
        if w > 0:
            lines.append(f"• *{tk}*: `{w:.2f}%`")
        else:
            lines.append(f"• *{tk}*: `0.00%` (Excluded for risk optimization)")

    lines.append(
        f"\n📊 *Expected Performance metrics:*\n"
        f"• *Expected Annual Return:* `{allocation['expected_return']:+.2f}%`\n"
        f"• *Annualized Volatility:* `{allocation['volatility']:.2f}%`\n"
        f"• *Sharpe Ratio:* `N/A — dated BI rate required`"
    )

    msg = "\n".join(lines)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)



def build_application():
    """Build the shared Telegram application for polling or webhook delivery."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler(["ta", "analyze"], ta_command))
    app.add_handler(CommandHandler(["fund", "fundamental"], fund_command))
    app.add_handler(CommandHandler(["quant"], quant_command))
    app.add_handler(CommandHandler(["portfolio"], portfolio_command))
    app.add_handler(CommandHandler(["decision"], decision_command))
    app.add_handler(CommandHandler(["chart"], chart_command))
    app.add_handler(CommandHandler(["scan"], scan_command))
    return app


def main():
    """Local entry point. The free cloud deployment uses bot_webhook.py."""
    try:
        app = build_application()
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1
    print("🚀 PastiCuan Telegram Bot is running! Press Ctrl+C to stop.")
    app.run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
