import os
import sys
import logging
import asyncio
import html
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
from analysis.scan_snapshots import get_scan_snapshot


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
    return ticker if ticker and len(ticker) <= 12 and ticker.replace("-", "").isalnum() else ""


def _readonly_repository():
    if not os.getenv("SUPABASE_DATABASE_URL"):
        return None
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository
    return SnapshotRepository(connect_from_env)


def _snapshot_only() -> bool:
    return os.getenv("BOT_SNAPSHOT_ONLY", "true").lower() == "true"


def _v4_evidence(ticker: str) -> tuple[dict | None, dict | None, object, object]:
    quant = get_research_snapshot()
    scan = get_scan_snapshot()
    quant_row = quant.ticker(ticker)
    bundle = scan.to_bundle([ticker]).to_dict()
    scan_row = next((row for row in bundle.get("candidates", []) if row.get("ticker") == ticker), None)
    return quant_row, scan_row, quant, scan


async def _snapshot_unavailable(update: Update, ticker: str, section: str) -> None:
    await update.message.reply_text(
        f"⚪ {section} for {ticker} is unavailable in the latest verified snapshot. "
        "The bot will not substitute a live provider calculation."
    )


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
        "Welcome! Get snapshot-based business evidence, technical setups, and stock scans for Indonesian equities directly in Telegram.\n\n"
        "*Available Commands:*\n"
        "• `/ta <ticker>` — Stored technical setup evidence (e.g. `/ta BBCA`)\n"
        "• `/fund <ticker>` — Point-in-time business evidence (e.g. `/fund TLKM`)\n"
        "• `/quant <ticker>` — Approved LQ45 factor percentile (e.g. `/quant BBCA`)\n"
        "• `/portfolio <t1> <t2> ...` — Minimum-volatility risk research (e.g. `/portfolio BBCA TLKM BMRI ICBP`)\n"
        "• `/decision <ticker>` — Business and setup states, kept separate (e.g. `/decision BMRI`)\n"
        "• `/evidence <ticker>` — Point-in-time sources and calculation coverage\n"
        "• `/history <ticker>` — Previous immutable research snapshots\n"
        "• `/status` — Data, provider, and model health\n"
        "• `/market` — Latest LQ45 research breadth\n"
        "• `/events <ticker>` — Official stored disclosure events\n"
        "• `/range <ticker>` — Stored entry, stop, target, and R/R evidence (e.g. `/range BBCA`)\n"
        "• `/chart <ticker>` — Unavailable in strict snapshot-only production mode\n"
        "• `/scan [ticker ...]` — Latest full-LQ45 EOD snapshot; optional filter\n"
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
    if _snapshot_only():
        _quant, row, _qs, scan = _v4_evidence(ticker_symbol)
        if not row:
            await _snapshot_unavailable(update, ticker_symbol, "Technical evidence")
            return
        components = row.get("technical_components") or {}
        lines = [f"📈 <b>{ticker_symbol} Technical Setup</b>",
                 f"Session <code>{html.escape(scan.session_date)}</code> · <code>{html.escape(scan.model_status)}</code>",
                 f"Setup score <code>{display_number(row.get('technical_score'))}</code> · coverage <code>{float((row.get('component_coverage') or {}).get('technical') or 0):.0f}%</code>"]
        lines.extend(f"{html.escape(name.title())}: <code>{display_number(value)}</code>" for name, value in components.items())
        lines.append(f"Entry state <code>{html.escape(row.get('entry_state', 'NO_RELIABLE_SETUP'))}</code> · RESEARCH_ONLY")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return
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
        f"• *Volume Evidence:* {tech.get('smart_money', '')}\n\n"
        f"💡 _Send `/chart {ticker_symbol}` to get the visual candlestick chart!_"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def decision_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Multi-factor Decision Matrix analysis."""
    if not context.args:
        await update.message.reply_text("ℹ️ Please specify a ticker symbol. Example: `/decision TLKM`", parse_mode=ParseMode.MARKDOWN)
        return

    ticker_symbol = _clean_ticker(context.args[0])
    if _snapshot_only():
        quant_row, row, quant, scan = _v4_evidence(ticker_symbol)
        if not quant_row and not row:
            await _snapshot_unavailable(update, ticker_symbol, "Decision evidence")
            return
        lines = [f"🏛️ <b>{ticker_symbol} Research Decision</b>",
                 f"Business <code>{display_number((quant_row or {}).get('business_score'))}</code> · <code>{html.escape((quant_row or {}).get('business_state', 'LIMITED_HISTORY'))}</code>",
                 f"Technical <code>{display_number((row or {}).get('technical_score'))}</code> · entry <code>{html.escape((row or {}).get('entry_state', 'NO_RELIABLE_SETUP'))}</code>",
                 f"Quant <code>{display_number((quant_row or {}).get('composite_percentile'))}</code>",
                 f"Effective <code>{html.escape(quant.effective_at)}</code> · scan <code>{html.escape(scan.session_date)}</code>",
                 "Action <code>None</code> · Policy <code>RESEARCH_ONLY</code>"]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return
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


def _render_scan_message(bundle: dict) -> str:
    """Render scanner output as escaped Telegram HTML."""
    escape = lambda value: html.escape(str(value), quote=False)
    mode = bundle.get("mode", "UNAVAILABLE")
    title = {
        "PRIMARY": "🏛️ <b>LQ45 Quality Research — Point-in-Time</b>",
        "DEGRADED": "⚠️ <b>LQ45 Quality Research — Limited Evidence</b>",
        "UNAVAILABLE": "⚪ <b>LQ45 Scanner Unavailable</b>",
    }.get(mode, "⚪ <b>LQ45 Scanner Unavailable</b>")
    lines = [title, "<i>Business horizon 12–36+ months · Entry timing 5–20 sessions · RESEARCH_ONLY</i>"]
    lines.append(
        f"Session <code>{escape(bundle.get('session_date') or 'N/A')}</code> · "
        f"Universe coverage <code>{float(bundle.get('universe_coverage_pct') or 0):.0f}%</code>"
    )
    if bundle.get("snapshot_id"):
        lines.append(f"Snapshot <code>{escape(bundle['snapshot_id'])}</code>\n")

    def candidate_line(item: dict) -> str:
        rank = f"#{int(item['rank'])} " if item.get("rank") is not None else ""
        score = (
            f" · Business <code>{item['ranking_score']:.1f}/100</code>"
            if item.get("ranking_score") is not None else ""
        )
        rr = f"{item['risk_reward']:.2f}R" if item.get("risk_reward") is not None else "N/A"
        return (
            f"• {rank}<b>{escape(item['ticker'])}</b>{score} · Rp {float(item['current_price']):,.0f}\n"
            f"  State <code>{escape(item.get('business_state', 'LIMITED_HISTORY'))}</code> · "
            f"Entry <code>{escape(item.get('entry_state', 'NO_RELIABLE_SETUP'))}</code>\n"
            f"  T <code>{escape(display_number(item.get('technical_score')))}</code> · "
            f"Quant <code>{escape(display_number(item.get('quant_percentile')))}</code> · "
            f"R/R <code>{escape(rr)}</code>\n"
            f"  Entry <code>{escape(_format_range(item.get('entry_zone')))}</code> "
            f"({escape(item.get('entry_zone_type', 'unavailable'))}) · "
            f"Fund coverage <code>{float(item.get('raw_fundamental_coverage_pct') or 0):.0f}%</code>"
        )

    ready = [row for row in bundle["candidates"] if row.get("entry_state") == "FAVORABLE_ENTRY"]
    ranked = [row for row in bundle["candidates"] if row.get("ranking_score") is not None]
    limited = [row for row in bundle["candidates"] if row.get("ranking_score") is None]
    lines.append(
        f"\nCoverage detail: <code>{len(ranked)}/45</code> business-scored · "
        f"<code>{len(ready)}</code> favorable entries"
    )
    if ready:
        lines.append("\n✅ <b>FAVORABLE ENTRY — quality gates also pass</b>")
        lines.extend(candidate_line(item) for item in ready[:3])
    shown = {item["ticker"] for item in ready[:3]}
    remaining = [item for item in ranked if item["ticker"] not in shown][:max(0, 5 - len(shown))]
    if remaining:
        lines.append("\n🏛️ <b>BUSINESS RANK — entry may still require patience</b>")
        lines.extend(candidate_line(item) for item in remaining)
    if not ranked and limited:
        lines.append("\n⚪ No issuer has enough point-in-time business history for a v4 Business Score.")
        lines.extend(candidate_line(item) for item in limited[:3])
    if not ready and not ranked and not limited:
        lines.append("\nNo ticker passed the current evidence and risk/reward gates.")
    if bundle["excluded"]:
        excluded = "; ".join(
            f"{row['ticker']}: {str(row['reason'])[:100]}" for row in bundle["excluded"][:3]
        )
        lines.append(f"\n⚠️ <b>Excluded:</b> {escape(excluded)}")
    for warning in bundle["warnings"][:2]:
        lines.append(f"\nℹ️ {escape(str(warning)[:160])}")
    if len(bundle["warnings"]) > 2:
        lines.append(f"<i>…and {len(bundle['warnings']) - 2} more warning(s).</i>")
    lines.append(
        "\n<i>Use <code>/range &lt;ticker&gt;</code> or "
        "<code>/decision &lt;ticker&gt;</code> for detail.</i>"
    )
    return "\n".join(lines)


async def range_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the auditable overlap of technical and valuation references."""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Please specify a ticker symbol. Example: `/range BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker_symbol = _clean_ticker(context.args[0])
    if _snapshot_only():
        _quant, row, _qs, scan = _v4_evidence(ticker_symbol)
        if not row:
            await _snapshot_unavailable(update, ticker_symbol, "Price-range evidence")
            return
        rr_text = f"{row['risk_reward']:.2f}R" if row.get("risk_reward") is not None else "N/A"
        await update.message.reply_text(
            f"🎯 <b>{ticker_symbol} Verified Range</b>\nSession <code>{html.escape(scan.session_date)}</code>\n"
            f"Entry <code>{html.escape(_format_range(row.get('entry_zone')))}</code> · <code>{html.escape(row.get('entry_zone_type', 'unavailable'))}</code>\n"
            f"Stop <code>{html.escape(_format_price(row.get('stop_loss')))}</code> · Target <code>{html.escape(_format_price(row.get('target')))}</code>\n"
            f"R/R <code>{rr_text}</code>\nRESEARCH_ONLY",
            parse_mode=ParseMode.HTML,
        )
        return
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
    if _snapshot_only():
        row, _scan_row, snapshot, _scan = _v4_evidence(ticker_symbol)
        if not row:
            await _snapshot_unavailable(update, ticker_symbol, "Fundamental evidence")
            return
        lines = [f"🏛️ <b>{ticker_symbol} Business Evidence</b>",
                 f"Business <code>{display_number(row.get('business_score'))}</code> · <code>{html.escape(row.get('business_state', 'LIMITED_HISTORY'))}</code>"]
        for name in ("quality", "valuation", "durability", "resilience"):
            lines.append(f"{name.title()} <code>{display_number(row.get(name + '_score'))}</code>")
        lines.extend([f"Raw fundamental coverage <code>{float(row.get('raw_fundamental_coverage_pct') or 0):.0f}%</code>",
                      f"Effective <code>{html.escape(snapshot.effective_at)}</code> · <code>{html.escape(snapshot.formula_version)}</code>"])
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return
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
    if _snapshot_only():
        await _snapshot_unavailable(update, ticker_symbol, "Chart")
        return
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
        f"Technical evidence: {results['tech'].get('recommendation', 'N/A')}"
    )
    await update.message.reply_photo(photo=buf, caption=caption, parse_mode=ParseMode.MARKDOWN)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read the immutable full-LQ45 scan; never call a provider here."""
    scan_limit = max(5, min(10, int(os.getenv("BOT_SCAN_LIMIT", "10"))))
    mode_filter = context.args[0].lower() if context.args and context.args[0].lower() in {"ready", "value", "defensive"} else None
    ticker_args = context.args[1:] if mode_filter else context.args
    requested = [_clean_ticker(value) for value in ticker_args[:scan_limit]] if ticker_args else None
    await update.message.reply_text(
        "🔎 Loading the latest full-LQ45 end-of-day research snapshot...",
        parse_mode=ParseMode.MARKDOWN,
    )
    snapshot = await asyncio.to_thread(get_scan_snapshot)
    bundle = scan_view(snapshot.to_bundle(requested))
    if mode_filter == "ready":
        bundle["candidates"] = [row for row in bundle["candidates"] if row.get("entry_state") == "FAVORABLE_ENTRY"]
    elif mode_filter == "value":
        bundle["candidates"].sort(key=lambda row: (-(row.get("business_components", {}).get("valuation") or -1), row["ticker"]))
    elif mode_filter == "defensive":
        bundle["candidates"].sort(key=lambda row: (-(row.get("business_components", {}).get("resilience") or -1), row["ticker"]))
    if len(context.args) > scan_limit:
        bundle["warnings"].insert(0, f"Only the first {scan_limit} ticker filters were used.")
    await update.message.reply_text(_render_scan_message(bundle), parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quant, scan = get_research_snapshot(refresh=True), get_scan_snapshot(refresh=True)
    operational = None
    repository = _readonly_repository()
    if repository:
        try:
            operational = await asyncio.to_thread(repository.operational_status)
        except Exception as exc:
            logger.warning("Status database query failed: %s", type(exc).__name__)
    lines = [
        "🩺 <b>PastiCuan Research Status</b>",
        f"Model <code>{html.escape(quant.model_version)}</code> · <code>{html.escape(quant.model_status)}</code>",
        f"Quant effective <code>{html.escape(quant.effective_at)}</code>",
        f"Scan session <code>{html.escape(scan.session_date)}</code> · mode <code>{html.escape(scan.mode)}</code>",
        f"Market coverage <code>{scan.universe_coverage_pct:.0f}%</code>",
    ]
    if operational:
        lines.extend([
            f"Latest completed session <code>{html.escape(str(operational['latest_session']))}</code>",
            f"Open ingestion issues <code>{operational['open_issues']}</code>",
            f"Provider failures (24h) <code>{operational['provider_failures_24h']}</code>",
        ])
    for warning in [*quant.warnings[:1], *scan.warnings[:1]]:
        lines.append(f"⚠️ {html.escape(str(warning)[:180])}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def evidence_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = _clean_ticker(context.args[0]) if context.args else ""
    if not ticker:
        await update.message.reply_text("Use /evidence <ticker>.")
        return
    quant = get_research_snapshot()
    row = quant.ticker(ticker)
    if not row:
        await update.message.reply_text(f"No approved point-in-time evidence exists for {ticker}.")
        return
    fields = ("business_state", "business_score", "quality_score", "valuation_score",
              "durability_score", "resilience_score", "composite_percentile",
              "raw_fundamental_coverage_pct", "raw_component_coverage_pct", "ranking_scope")
    lines = [f"🔎 <b>{ticker} Evidence</b>",
             f"Effective <code>{html.escape(quant.effective_at)}</code>",
             f"Formula <code>{html.escape(quant.formula_version)}</code>"]
    lines.extend(f"{html.escape(name)}: <code>{html.escape(display_number(row.get(name)))}</code>" for name in fields)
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = _clean_ticker(context.args[0]) if context.args else ""
    repository = _readonly_repository()
    if not ticker or not repository:
        await update.message.reply_text("History requires /history <ticker> and configured read-only Supabase access.")
        return
    try:
        rows = await asyncio.to_thread(repository.ticker_snapshot_history, ticker)
    except Exception:
        logger.exception("History query failed")
        rows = []
    if not rows:
        await update.message.reply_text(f"No immutable scan history is available for {ticker}.")
        return
    lines = [f"🕰️ <b>{ticker} Research History</b>"]
    for row in rows:
        item = row["candidate"]
        lines.append(f"<code>{row['session_date']}</code> · Business {html.escape(display_number(item.get('business_score')))} · {html.escape(item.get('entry_state', 'N/A'))}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bundle = get_scan_snapshot().to_bundle().to_dict()
    candidates = bundle.get("candidates", [])
    quality = sum(row.get("business_state") == "QUALITY_CANDIDATE" for row in candidates)
    ready = sum(row.get("entry_state") == "FAVORABLE_ENTRY" for row in candidates)
    await update.message.reply_text(
        f"🌐 <b>LQ45 Research Breadth</b>\nSession <code>{html.escape(str(bundle.get('session_date')))}</code>\n"
        f"Market coverage <code>{float(bundle.get('universe_coverage_pct') or 0):.0f}%</code>\n"
        f"Quality candidates <code>{quality}</code> · Favorable entries <code>{ready}</code>",
        parse_mode=ParseMode.HTML,
    )


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = _clean_ticker(context.args[0]) if context.args else ""
    repository = _readonly_repository()
    if not ticker or not repository:
        await update.message.reply_text("Events require /events <ticker> and configured read-only Supabase access.")
        return
    try:
        rows = await asyncio.to_thread(repository.disclosure_events_for_ticker, ticker)
    except Exception:
        logger.exception("Event query failed")
        rows = []
    if not rows:
        await update.message.reply_text(f"No stored official events are available for {ticker}.")
        return
    lines = [f"📣 <b>{ticker} Official Events</b>"]
    for row in rows:
        lines.append(f"• <code>{html.escape(str(row['published_at'])[:10])}</code> {html.escape(row['event_type'])}: {html.escape(row['title'][:100])}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


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
    price_history = None
    if _snapshot_only():
        repository = _readonly_repository()
        if not repository:
            await update.message.reply_text("Portfolio research requires configured read-only Supabase history.")
            return
        price_history = await asyncio.to_thread(
            repository.portfolio_price_history, tickers_list, pd.Timestamp.now(tz="UTC").isoformat(),
        )
    res = await asyncio.to_thread(optimize_portfolio, tickers_list, period="3y", price_history=price_history)
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
        f"\n📊 *Risk estimates ({res.get('observations', 0)} sessions):*\n"
        f"• *Annualized Volatility:* `{allocation['volatility']:.2f}%`\n"
        f"• *Expected Return / Sharpe:* `N/A — not estimated without a validated return model`"
    )

    msg = "\n".join(lines)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log unexpected handler failures and give the user a parse-safe response."""
    error = context.error
    logger.error(
        "Unhandled Telegram command failure: %s (cause=%r)",
        error, getattr(error, "__cause__", None),
        exc_info=(type(error), error, error.__traceback__) if error else None,
    )
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "⚠️ The command failed safely. Please try again; if it repeats, check the deployment logs."
            )
        except Exception:
            logger.error("Could not deliver Telegram error notice", exc_info=True)



def build_application():
    """Build the shared Telegram application for polling or webhook delivery."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")
    # Validate and cache the approved snapshot once. Any Supabase failure falls
    # back to the bundled snapshot without preventing bot startup.
    get_research_snapshot()
    get_scan_snapshot()
    request_timeout = max(
        5.0, min(60.0, float(os.getenv("TELEGRAM_REQUEST_TIMEOUT", "20")))
    )
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .connection_pool_size(8)
        .connect_timeout(request_timeout)
        .read_timeout(request_timeout)
        .write_timeout(request_timeout)
        .pool_timeout(5.0)
        .media_write_timeout(max(30.0, request_timeout))
        .build()
    )
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler(["ta", "analyze"], ta_command))
    app.add_handler(CommandHandler(["fund", "fundamental"], fund_command))
    app.add_handler(CommandHandler(["quant"], quant_command))
    app.add_handler(CommandHandler(["portfolio"], portfolio_command))
    app.add_handler(CommandHandler(["decision"], decision_command))
    app.add_handler(CommandHandler(["range", "buyrange"], range_command))
    app.add_handler(CommandHandler(["chart"], chart_command))
    app.add_handler(CommandHandler(["scan"], scan_command))
    app.add_handler(CommandHandler(["status"], status_command))
    app.add_handler(CommandHandler(["evidence"], evidence_command))
    app.add_handler(CommandHandler(["history"], history_command))
    app.add_handler(CommandHandler(["market"], market_command))
    app.add_handler(CommandHandler(["events"], events_command))
    app.add_error_handler(telegram_error_handler)
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
