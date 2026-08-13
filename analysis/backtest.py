"""Causal, next-session execution backtest for completed-session signals."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from analysis.risk import calculate_position_size
from analysis.technical import analyze_technical


@dataclass(frozen=True)
class BrokerCostProfile:
    """All rates are fractions of traded notional."""

    name: str
    buy_commission: float
    sell_commission: float
    sell_tax_levy: float = 0.0
    half_spread: float = 0.0
    slippage_bps: float = 0.0
    max_volume_participation: float = 0.05

    def validate(self) -> None:
        values = (
            self.buy_commission, self.sell_commission, self.sell_tax_levy,
            self.half_spread, self.slippage_bps, self.max_volume_participation,
        )
        if any(v < 0 for v in values) or not 0 < self.max_volume_participation <= 1:
            raise ValueError("Broker costs must be non-negative and volume participation in (0, 1].")


def _empty_result(message: str, gross_only: bool = True) -> dict:
    return {
        "error": message, "summary": {}, "trades": pd.DataFrame(),
        "equity_curve": pd.DataFrame(), "signal_stats": {},
        "setup_confidence": None, "costs_configured": not gross_only,
        "research_only": gross_only, "formula_version": "causal-backtest-v2",
    }


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float((equity / equity.cummax() - 1).min() * 100)


def _summary(trades: pd.DataFrame, curve: pd.DataFrame, initial_cash: float) -> dict:
    equity = curve["Equity"] if not curve.empty else pd.Series(dtype=float)
    final = float(equity.iloc[-1]) if not equity.empty else initial_cash
    returns = equity.pct_change().dropna()
    years = max(len(equity) / 252, 1 / 252)
    total = final / initial_cash - 1 if initial_cash else 0.0
    cagr = (final / initial_cash) ** (1 / years) - 1 if final > 0 and initial_cash > 0 else -1
    vol = float(returns.std(ddof=1) * math.sqrt(252)) if len(returns) >= 2 else None
    downside = returns[returns < 0]
    downside_dev = float(np.sqrt((downside**2).mean()) * math.sqrt(252)) if len(downside) else None
    sharpe = float(returns.mean() * 252 / vol) if vol and vol > 0 else None
    sortino = float(returns.mean() * 252 / downside_dev) if downside_dev and downside_dev > 0 else None
    if trades.empty:
        trade_values = {"total_trades": 0, "win_rate": 0.0, "average_return": 0.0,
                        "profit_factor": None, "expectancy": None, "average_holding_days": 0.0,
                        "tp_hit_rate": 0.0, "sl_hit_rate": 0.0, "turnover": 0.0}
    else:
        wins = trades[trades["PnL"] > 0]
        losses = trades[trades["PnL"] <= 0]
        gp, gl = float(wins["PnL"].sum()), abs(float(losses["PnL"].sum()))
        trade_values = {
            "total_trades": int(len(trades)),
            "win_rate": float(len(wins) / len(trades) * 100),
            "average_return": float(trades["Return %"].mean()),
            "profit_factor": float(gp / gl) if gl else (None if gp == 0 else float("inf")),
            "expectancy": float(trades["PnL"].mean()),
            "average_holding_days": float(trades["Holding Days"].mean()),
            "tp_hit_rate": float((trades["Exit Reason"] == "Take Profit").mean() * 100),
            "sl_hit_rate": float((trades["Exit Reason"] == "Stop Loss").mean() * 100),
            "turnover": float(trades[["Entry Notional", "Exit Notional"]].sum(axis=1).sum() / initial_cash),
        }
    return {
        **trade_values, "max_drawdown": _max_drawdown(equity),
        "total_return": total * 100, "cagr": cagr * 100,
        "volatility": vol * 100 if vol is not None else None,
        "sharpe": sharpe, "sortino": sortino,
        "sample_sessions": int(len(equity)),
    }


def _setup_confidence(summary: dict) -> float | None:
    # This is descriptive evidence only; eligibility is decided by external
    # untouched-holdout validation, never by optimizing this number.
    if summary.get("total_trades", 0) < 30 or summary.get("sample_sessions", 0) < 5 * 252:
        return None
    pf = summary.get("profit_factor")
    if pf is None:
        return None
    return float(max(0, min(100, 50 + (summary["win_rate"] - 50) * 0.3 + (min(pf, 2) - 1) * 25)))


def backtest_technical_strategy(
    history: pd.DataFrame,
    sector=None,
    info=None,
    initial_cash=100_000_000,
    risk_per_trade=0.01,
    broker_costs: BrokerCostProfile | None = None,
) -> dict:
    """Signal at completed close, execute no earlier than next tradable open.

    When ``broker_costs`` is absent, results are gross research output and are
    forbidden from passing the decision engine's cost gate.
    """
    gross_only = broker_costs is None
    costs = broker_costs or BrokerCostProfile("gross-research", 0, 0, 0, 0, 0, 0.05)
    try:
        costs.validate()
    except ValueError as exc:
        return _empty_result(str(exc), gross_only)
    required = {"Open", "High", "Low", "Close", "Volume"}
    if history is None or history.empty or not required.issubset(history.columns):
        return _empty_result("Insufficient OHLCV data for backtesting.", gross_only)
    df = history.copy().sort_index().dropna(subset=list(required))
    if len(df) < 120:
        return _empty_result("At least 120 completed sessions are required.", gross_only)

    cash = float(initial_cash)
    position = None
    pending = None
    trades: list[dict] = []
    rows: list[dict] = []
    evaluated = signals = 0
    min_bars, max_holding = min(220, max(80, len(df) // 3)), 60

    for i in range(min_bars, len(df)):
        bar, when = df.iloc[i], df.index[i]
        volume = float(bar["Volume"])

        # A close signal from i-1 may fill only at this (or a later tradable) open.
        if pending and position is None and volume > 0:
            raw_entry = float(bar["Open"])
            entry = raw_entry * (1 + costs.half_spread + costs.slippage_bps / 10_000)
            sizing = calculate_position_size(entry, pending["stop_loss"], cash, risk_per_trade)
            affordable = int(cash / (entry * (1 + costs.buy_commission)) // 100 * 100)
            liquid = int(volume * costs.max_volume_participation // 100 * 100)
            shares = min(sizing.get("shares", 0), affordable, liquid)
            if shares > 0:
                notional = shares * entry
                fee = notional * costs.buy_commission
                cash -= notional + fee
                position = {**pending, "entry_i": i, "entry_date": when, "entry": entry,
                            "shares": shares, "lots": shares // 100, "buy_fee": fee,
                            "entry_notional": notional}
            pending = None

        if position:
            split = float(bar.get("Stock Splits", 0) or 0)
            if split > 0 and position["entry_i"] < i:
                position["shares"] = int(position["shares"] * split)
                position["entry"] /= split
                position["stop_loss"] /= split
                position["take_profit"] /= split
            dividend = float(bar.get("Dividends", 0) or 0)
            if dividend > 0 and position["entry_i"] < i:
                cash += dividend * position["shares"]

            exit_price = reason = None
            if volume > 0:
                # Gap-through stops fill at the worse open; targets remain limit fills.
                if float(bar["Open"]) <= position["stop_loss"]:
                    exit_price, reason = float(bar["Open"]), "Stop Loss"
                elif float(bar["Low"]) <= position["stop_loss"]:
                    exit_price, reason = position["stop_loss"], "Stop Loss"
                elif float(bar["Open"]) >= position["take_profit"]:
                    exit_price, reason = position["take_profit"], "Take Profit"
                elif float(bar["High"]) >= position["take_profit"]:
                    exit_price, reason = position["take_profit"], "Take Profit"
                elif i - position["entry_i"] >= max_holding:
                    exit_price, reason = float(bar["Close"]), "Max Holding"

            if exit_price is not None:
                exit_price *= 1 - costs.half_spread - costs.slippage_bps / 10_000
                notional = position["shares"] * exit_price
                sell_fee = notional * (costs.sell_commission + costs.sell_tax_levy)
                cash += notional - sell_fee
                pnl = (notional - sell_fee) - (position["entry_notional"] + position["buy_fee"])
                trades.append({
                    "Signal Date": position["signal_date"], "Entry Date": position["entry_date"], "Exit Date": when,
                    "Entry": position["entry"], "Exit": exit_price,
                    "Stop Loss": position["stop_loss"], "Take Profit": position["take_profit"],
                    "Shares": position["shares"], "Lots": position["lots"], "PnL": pnl,
                    "Return %": pnl / (position["entry_notional"] + position["buy_fee"]) * 100,
                    "Holding Days": i - position["entry_i"], "Exit Reason": reason,
                    "Entry Score": position["score"], "Entry Notional": position["entry_notional"],
                    "Exit Notional": notional, "Costs": position["buy_fee"] + sell_fee,
                })
                position = None

        mark = cash + (position["shares"] * float(bar["Close"]) if position else 0)
        rows.append({"Date": when, "Equity": mark})

        # Compute after this close; never use it for today's execution.
        if position is None and pending is None:
            tech = analyze_technical(df.iloc[: i + 1], sector=sector, info=info or {})
            evaluated += 1
            score = tech.get("technical_score")
            if (score is not None and score >= 58 and
                    (tech.get("risk_reward") is None or tech["risk_reward"] >= 1) and
                    tech.get("stop_loss") is not None and tech.get("take_profit") is not None):
                signals += 1
                pending = {"signal_date": when, "stop_loss": float(tech["stop_loss"]),
                           "take_profit": float(tech["take_profit"]), "score": float(score)}

    # Forced liquidation uses the last tradable close and is always disclosed.
    if position:
        last = df.iloc[-1]
        price = float(last["Close"]) * (1 - costs.half_spread - costs.slippage_bps / 10_000)
        notional = position["shares"] * price
        fee = notional * (costs.sell_commission + costs.sell_tax_levy)
        cash += notional - fee
        pnl = (notional - fee) - (position["entry_notional"] + position["buy_fee"])
        trades.append({"Signal Date": position["signal_date"], "Entry Date": position["entry_date"], "Exit Date": df.index[-1],
                       "Entry": position["entry"], "Exit": price, "Stop Loss": position["stop_loss"],
                       "Take Profit": position["take_profit"], "Shares": position["shares"],
                       "Lots": position["lots"], "PnL": pnl,
                       "Return %": pnl / (position["entry_notional"] + position["buy_fee"]) * 100,
                       "Holding Days": len(df) - 1 - position["entry_i"], "Exit Reason": "End of Test",
                       "Entry Score": position["score"], "Entry Notional": position["entry_notional"],
                       "Exit Notional": notional, "Costs": position["buy_fee"] + fee})
        if rows:
            rows[-1]["Equity"] = cash

    trades_df = pd.DataFrame(trades)
    curve = pd.DataFrame(rows).drop_duplicates("Date", keep="last").set_index("Date")
    summary = _summary(trades_df, curve, float(initial_cash))
    return {
        "error": None, "summary": summary, "trades": trades_df, "equity_curve": curve,
        "signal_stats": {"evaluated_bars": evaluated, "buy_signals": signals,
                         "buy_signal_rate": signals / evaluated * 100 if evaluated else 0,
                         "min_bars": min_bars, "max_holding_days": max_holding,
                         "execution": "signal close -> next tradable open"},
        "setup_confidence": _setup_confidence(summary),
        "costs_configured": not gross_only, "cost_profile": costs.name,
        "research_only": gross_only, "formula_version": "causal-backtest-v2",
    }
