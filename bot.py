import os
import sys
import logging
import asyncio
from dotenv import load_dotenv
import pandas as pd

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from data.extended import get_extended_data
from analysis.engine import run_analysis_bundle
from analysis.presentation import decision_view, display_number, scan_view
from analysis.scanner import DEFAULT_SCAN_TICKERS, run_scan
from analysis.snapshots import get_research_snapshot


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

POPULAR_TICKERS = DEFAULT_SCAN_TICKERS


def _clean_ticker(text: str) -> str:
    if not text:
        return ""
    ticker = text.strip().split()[0].upper()
    ticker = ticker.replace(".JK", "")
    return ticker


def _escape_markdown_text(value: str) -> str:
    return str(value).replace("_", "\\_")


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

    snapshot = get_research_snapshot()
    analysis = run_analysis_bundle(
        data, include_backtest=include_backtest,
        model_evidence={
            "snapshot_id": snapshot.snapshot_id,
            "model_version": snapshot.model_version,
            "model_status": snapshot.model_status,
            "validation_run_id": snapshot.validation_run_id,
        },
    )

    return {
        "data": data,
        "tech": analysis["tech"],
        "fund": analysis["fund"],
        "bands": analysis["bands"],
        "seasonality": analysis["seasonality"],
        "backtest": analysis["backtest"],
        "liquidity": analysis["liquidity"],
        "decision": analysis["decision"],
        "buy_range": analysis["buy_range"],
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
        "• `/range <ticker>` — Technical + valuation buy-range research (e.g. `/range BBCA`)\n"
        "• `/chart <ticker>` — Technical Candlestick & Indicator Chart (e.g. `/chart ASII`)\n"
        "• `/scan [5–10 tickers]` — Combined research ranking; arguments are optional\n"
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

    results, error = await asyncio.to_thread(_run_full_analysis, ticker_symbol)
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
    results, error = await asyncio.to_thread(
        _run_full_analysis, ticker_symbol, include_backtest=include_backtest,
    )
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
    bullet_text = "\n".join(f"• {_escape_markdown_text(w)}" for w in view["warnings"][:4]) or f"• {view['reason']}"

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


def _format_range(value: dict | None) -> str:
    if not value:
        return "N/A"
    return f"Rp {value['low']:,.0f} – Rp {value['high']:,.0f}"


def _format_price(value) -> str:
    return f"Rp {value:,.0f}" if isinstance(value, (int, float)) else "N/A"


async def range_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the auditable overlap of technical and valuation references."""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Please specify a ticker symbol. Example: `/range BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(
        f"⏳ Calculating price ranges for *{ticker_symbol}.JK*...",
        parse_mode=ParseMode.MARKDOWN,
    )
    results, error = await asyncio.to_thread(_run_full_analysis, ticker_symbol)
    if error:
        await update.message.reply_text(
            f"❌ *Error evaluating {ticker_symbol}:*\n{error}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    report = results["buy_range"]
    bundle = results["bundle"]
    stop = report.get("stop_loss")
    target = report.get("technical_target")
    rr = report.get("risk_reward")
    confirmation = "Present" if report.get("technical_confirmation") else "Not present / incomplete"
    warning_text = "\n".join(f"• {item}" for item in report.get("warnings", [])[:4])
    msg = (
        f"🎯 *{results['data']['ticker']} — Price Range Research*\n"
        f"💰 *Current:* {_format_price(report.get('current_price'))}\n"
        f"🕒 *As of:* {bundle.get('as_of', 'N/A')}\n"
        f"───────────────\n"
        f"📉 *Technical accumulation zone:* `{_format_range(report.get('technical_range'))}`\n"
        f"🏛️ *Valuation reference:* `{_format_range(report.get('valuation_reference_range'))}`\n"
        f"⭐ *Preferred overlap:* `{_format_range(report.get('preferred_range'))}`\n\n"
        f"🛑 *Technical invalidation:* `{_format_price(stop)}`\n"
        f"🎯 *Technical target:* `{_format_price(target)}`\n"
        f"⚖️ *Risk/reward:* `{f'{rr:.2f}R' if rr is not None else 'N/A'}`\n"
        f"✅ *Trend confirmation:* `{confirmation}`\n\n"
        f"📋 *Status:* `{report.get('status')}` · Policy `{report.get('policy_label')}`\n"
        f"📚 *Fundamental source:* {report.get('source')}\n"
        f"🧮 *Formula:* `{report.get('formula_version')}`\n\n"
        f"⚠️ *Important:*\n{warning_text}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def fund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Fundamental Analysis for a given ticker."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/fund BBCA`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    await update.message.reply_text(f"⏳ Evaluating fundamentals for *{ticker_symbol}.JK*...", parse_mode=ParseMode.MARKDOWN)

    results, error = await asyncio.to_thread(_run_full_analysis, ticker_symbol)
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
    statement_currency = data.get("info", {}).get("financialCurrency") or "reported currency"
    ocf = fund.get("operating_cash_flow_ttm")
    fcf = fund.get("free_cash_flow_ttm")
    cash_conversion = fund.get("cash_conversion")
    fcf_yield = fund.get("fcf_yield")
    ocf_str = f"{statement_currency} {ocf:,.0f}" if isinstance(ocf, (int, float)) else "N/A"
    fcf_str = f"{statement_currency} {fcf:,.0f}" if isinstance(fcf, (int, float)) else "N/A"
    conversion_str = f"{cash_conversion:.2f}x" if isinstance(cash_conversion, (int, float)) else "N/A"
    fcf_yield_str = f"{fcf_yield * 100:.2f}%" if isinstance(fcf_yield, (int, float)) else "N/A"

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
        f"💵 *Cash Flow Quality:*\n"
        f"• *TTM Operating Cash Flow:* `{ocf_str}`\n"
        f"• *TTM Reported Free Cash Flow:* `{fcf_str}`\n"
        f"• *Cash Conversion:* `{conversion_str}`\n"
        f"• *FCF Yield:* `{fcf_yield_str}`\n\n"
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

    results, error = await asyncio.to_thread(_run_full_analysis, ticker_symbol)
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
    """Rank a bounded custom watchlist using the shared research contract."""
    scan_limit = max(5, min(10, int(os.getenv("BOT_SCAN_LIMIT", "10"))))
    requested = [_clean_ticker(value) for value in context.args] if context.args else POPULAR_TICKERS
    await update.message.reply_text(
        f"🔎 Scanning {len(requested)} IDX stocks across technical, fundamental, quant, range, and liquidity evidence...",
        parse_mode=ParseMode.MARKDOWN,
    )
    bundle = scan_view(await asyncio.to_thread(run_scan, requested, max_tickers=scan_limit))
    lines = ["🔎 *IDX Research Scanner — Top 5*", "_Policy: RESEARCH\\_ONLY · Swing horizon 5–20 sessions_\n"]
    for item in bundle["candidates"][:5]:
        preferred = _format_range(item.get("preferred_range"))
        quant = display_number(item.get("quant_percentile"))
        rr = f"{item['risk_reward']:.2f}R" if item.get("risk_reward") is not None else "N/A"
        lines.append(
            f"{item['rank']}. *{item['ticker']}* · `{item['composite_score']:.1f}/100` · Rp {item['current_price']:,.0f}\n"
            f"   T `{display_number(item.get('technical_score'))}` · F `{display_number(item.get('fundamental_score'))}` · Q `{quant}`\n"
            f"   Range `{preferred}` · R/R `{rr}` · Coverage `{item['coverage_pct']:.0f}%`"
        )
    if not bundle["candidates"]:
        lines.append("No ticker passed the mandatory data, coverage, and liquidity gates.")
    if bundle["excluded"]:
        excluded_text = "; ".join(f"{row['ticker']}: {row['reason']}" for row in bundle["excluded"][:5])
        lines.append(f"\n⚠️ *Excluded:* {_escape_markdown_text(excluded_text)}")
    if bundle["warnings"]:
        lines.append(f"\nℹ️ {_escape_markdown_text(bundle['warnings'][0])}")
    lines.append("\n_Use `/range <ticker>` or `/decision <ticker>` for detail._")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def quant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a ticker's relative percentile in a bounded comparison universe."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/quant BBCA`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    snapshot = get_research_snapshot()
    approved = snapshot.ticker(ticker_symbol)
    if approved:
        percentile = approved.get("composite_percentile", approved.get("quant_percentile"))
        factor_lines = []
        for name in ("value", "quality", "momentum", "low_volatility"):
            if approved.get(name) is not None:
                factor_lines.append(f"• *{name.replace('_', ' ').title()}:* `{display_number(approved[name])}`")
        msg = (
            f"🔬 *{ticker_symbol}.JK — Approved LQ45 Quant Snapshot*\n"
            f"Effective `{snapshot.effective_at}` · Model `{snapshot.model_version}`\n"
            f"───────────────\n"
            f"📊 *Composite percentile:* `{display_number(percentile)}`\n"
            f"🌐 *Ranking scope:* `{approved.get('ranking_scope', 'historical_lq45')}`\n"
            f"📋 *Coverage:* `{float(approved.get('coverage_pct', 0)):.0f}%`\n"
            + ("\n".join(factor_lines) + "\n" if factor_lines else "")
            + f"🏷️ *Status:* `{snapshot.model_status}` · `RESEARCH_ONLY`\n\n"
            f"_Snapshot `{snapshot.snapshot_id}`; rankings use information available at the stated cutoff._"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text(f"⏳ Ranking *{ticker_symbol}.JK* in the default comparison universe...", parse_mode=ParseMode.MARKDOWN)
    comparison = [ticker_symbol, *[item for item in POPULAR_TICKERS if item != ticker_symbol]][:10]
    bundle = scan_view(await asyncio.to_thread(run_scan, comparison))
    item = next((row for row in bundle["candidates"] if row["ticker"] == ticker_symbol), None)
    if item is None:
        reason = next((row["reason"] for row in bundle["excluded"] if row["ticker"] == ticker_symbol), "Insufficient comparison evidence.")
        await update.message.reply_text(f"⚪ *{ticker_symbol} quant unavailable:* {reason}", parse_mode=ParseMode.MARKDOWN)
        return
    components = item.get("components", {})
    msg = (
        f"🔬 *{item['display_ticker']} — Cross-Sectional Quant*\n"
        f"Compared with `{len(bundle['requested_tickers'])}` current scan names\n"
        f"───────────────\n"
        f"📊 *Quant percentile:* `{display_number(item.get('quant_percentile'))}`\n"
        f"🌐 *Ranking scope:* `{item.get('quant_scope', 'unavailable')}`\n"
        f"📈 *Technical evidence:* `{display_number(components.get('technical'))}`\n"
        f"🏛️ *Fundamental evidence:* `{display_number(components.get('fundamental'))}`\n"
        f"💧 *Liquidity evidence:* `{display_number(components.get('liquidity'))}`\n"
        f"📋 *Coverage:* `{item['coverage_pct']:.0f}%` · `RESEARCH_ONLY`\n\n"
        f"_Percentiles are relative to this small current universe; they are not absolute investment quality._"
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

    # SciPy is intentionally lazy-loaded to keep webhook cold-start memory low.
    from analysis.portfolio import optimize_portfolio

    res = await asyncio.to_thread(optimize_portfolio, tickers_list, period="1y")
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
    # Validate and cache the approved snapshot once. Any Supabase failure falls
    # back to the bundled snapshot without preventing bot startup.
    get_research_snapshot()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler(["ta", "analyze"], ta_command))
    app.add_handler(CommandHandler(["fund", "fundamental"], fund_command))
    app.add_handler(CommandHandler(["quant"], quant_command))
    app.add_handler(CommandHandler(["portfolio"], portfolio_command))
    app.add_handler(CommandHandler(["decision"], decision_command))
    app.add_handler(CommandHandler(["range", "buyrange"], range_command))
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
