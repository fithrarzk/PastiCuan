"""Simple historical validation for the adaptive technical strategy."""

from __future__ import annotations

import pandas as pd

from analysis.risk import calculate_position_size
from analysis.technical import analyze_technical


def _empty_result(message: str) -> dict:
    return {
        "error": message,
        "summary": {},
        "trades": pd.DataFrame(),
        "equity_curve": pd.DataFrame(),
        "signal_stats": {},
        "setup_confidence": None,
    }


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    return float(drawdown.min() * 100)


def _summarize_trades(trades: pd.DataFrame, equity_curve: pd.DataFrame, initial_cash: float) -> dict:
    if trades.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "average_holding_days": 0.0,
            "max_drawdown": _max_drawdown(equity_curve["Equity"]) if not equity_curve.empty else 0.0,
            "total_return": 0.0,
            "tp_hit_rate": 0.0,
            "sl_hit_rate": 0.0,
        }

    wins = trades[trades["Return %"] > 0]
    losses = trades[trades["Return %"] <= 0]
    gross_profit = wins["PnL"].sum()
    gross_loss = abs(losses["PnL"].sum())
    final_equity = float(equity_curve["Equity"].iloc[-1]) if not equity_curve.empty else initial_cash

    return {
        "total_trades": int(len(trades)),
        "win_rate": float(len(wins) / len(trades) * 100),
        "average_return": float(trades["Return %"].mean()),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        "expectancy": float(trades["PnL"].mean()),
        "average_holding_days": float(trades["Holding Days"].mean()),
        "max_drawdown": _max_drawdown(equity_curve["Equity"]) if not equity_curve.empty else 0.0,
        "total_return": float((final_equity / initial_cash - 1) * 100) if initial_cash else 0.0,
        "tp_hit_rate": float((trades["Exit Reason"] == "Take Profit").mean() * 100),
        "sl_hit_rate": float((trades["Exit Reason"] == "Stop Loss").mean() * 100),
    }


def _setup_confidence(summary: dict) -> float | None:
    if not summary or summary.get("total_trades", 0) < 3:
        return None
    win_rate = summary.get("win_rate", 0.0)
    avg_return = summary.get("average_return", 0.0)
    profit_factor = summary.get("profit_factor", 0.0)
    if profit_factor == float("inf"):
        profit_factor_score = 20
    else:
        profit_factor_score = max(-20, min(20, (profit_factor - 1) * 25))
    trade_depth = min(15, summary.get("total_trades", 0) * 2)
    confidence = 45 + (win_rate - 50) * 0.45 + avg_return * 2.2 + profit_factor_score + trade_depth
    return float(max(20, min(90, confidence)))


def backtest_technical_strategy(
    history: pd.DataFrame,
    sector=None,
    info=None,
    initial_cash=100_000_000,
    risk_per_trade=0.01,
) -> dict:
    """
    Backtest the current adaptive technical rules.

    The simulation is intentionally conservative: entries happen at the signal
    close, stop loss is assumed before take profit when both are touched in the
    same candle, and only one long position is open at a time.
    """
    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if history is None or history.empty or not required_cols.issubset(history.columns):
        return _empty_result("Insufficient OHLCV data for backtesting.")

    df = history.copy().sort_index().dropna(subset=["High", "Low", "Close"])
    if len(df) < 120:
        return _empty_result("At least 120 bars are recommended for a useful backtest.")

    info = info or {}
    cash = float(initial_cash)
    equity = cash
    position = None
    trades = []
    equity_rows = []
    signal_count = 0
    buy_signal_count = 0
    min_bars = min(220, max(80, len(df) // 3))
    max_holding_days = 60

    for i in range(min_bars, len(df)):
        current = df.iloc[i]
        current_date = df.index[i]

        if position:
            exit_price = None
            exit_reason = None
            if current["Low"] <= position["stop_loss"]:
                exit_price = position["stop_loss"]
                exit_reason = "Stop Loss"
            elif current["High"] >= position["take_profit"]:
                exit_price = position["take_profit"]
                exit_reason = "Take Profit"
            elif i - position["entry_i"] >= max_holding_days:
                exit_price = float(current["Close"])
                exit_reason = "Max Holding"
            else:
                lookback = df.iloc[: i + 1]
                tech_now = analyze_technical(lookback, sector=sector, info=info)
                if tech_now.get("technical_score", 50) < 45:
                    exit_price = float(current["Close"])
                    exit_reason = "Signal Deterioration"

            mark_price = float(current["Close"])
            equity_rows.append({
                "Date": current_date,
                "Equity": cash + position["shares"] * (mark_price - position["entry"]),
            })

            if exit_price is not None:
                pnl = (exit_price - position["entry"]) * position["shares"]
                cash += pnl
                holding_days = i - position["entry_i"]
                trades.append({
                    "Entry Date": position["entry_date"],
                    "Exit Date": current_date,
                    "Entry": position["entry"],
                    "Exit": exit_price,
                    "Stop Loss": position["stop_loss"],
                    "Take Profit": position["take_profit"],
                    "Shares": position["shares"],
                    "Lots": position["lots"],
                    "PnL": pnl,
                    "Return %": (exit_price / position["entry"] - 1) * 100,
                    "Holding Days": holding_days,
                    "Exit Reason": exit_reason,
                    "Entry Score": position["score"],
                })
                equity = cash
                position = None
            continue

        lookback = df.iloc[: i + 1]
        tech = analyze_technical(lookback, sector=sector, info=info)
        score = tech.get("technical_score")
        signal_count += 1
        equity_rows.append({"Date": current_date, "Equity": equity})

        if score is None or score < 58:
            continue
        if tech.get("risk_reward") is not None and tech["risk_reward"] < 1.0:
            continue
        if tech.get("stop_loss") is None or tech.get("take_profit") is None:
            continue

        entry = float(current["Close"])
        stop_loss = float(tech["stop_loss"])
        take_profit = float(tech["take_profit"])
        sizing = calculate_position_size(entry, stop_loss, equity, risk_per_trade)
        if sizing.get("error") or sizing["shares"] <= 0:
            continue

        buy_signal_count += 1
        position = {
            "entry_i": i,
            "entry_date": current_date,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "shares": sizing["shares"],
            "lots": sizing["lots"],
            "score": score,
        }

    trades_df = pd.DataFrame(trades)
    equity_curve = pd.DataFrame(equity_rows)
    if not equity_curve.empty:
        equity_curve = equity_curve.drop_duplicates("Date", keep="last").set_index("Date")
    summary = _summarize_trades(trades_df, equity_curve, float(initial_cash))
    confidence = _setup_confidence(summary)

    return {
        "error": None,
        "summary": summary,
        "trades": trades_df,
        "equity_curve": equity_curve,
        "signal_stats": {
            "evaluated_bars": signal_count,
            "buy_signals": buy_signal_count,
            "buy_signal_rate": buy_signal_count / signal_count * 100 if signal_count else 0.0,
            "min_bars": min_bars,
            "max_holding_days": max_holding_days,
        },
        "setup_confidence": confidence,
    }
