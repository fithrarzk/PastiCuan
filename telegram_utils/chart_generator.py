import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np


def generate_telegram_chart(tech: dict, ticker: str) -> io.BytesIO:
    """
    Generates a dark-themed multi-panel chart (Price + Moving Averages + Support/Resistance, RSI, MACD)
    formatted specifically for Telegram chat view, and returns a BytesIO PNG buffer.
    """
    df = tech.get("df")
    if df is None or df.empty:
        return None

    # Filter to recent 120 trading days for clear mobile viewing
    plot_df = df.tail(min(len(df), 120)).copy()
    
    # Configure dark theme aesthetic matching PastiCuan UI
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(10, 8), dpi=140)
    fig.patch.set_facecolor('#111113')

    # Grid layout: 3 rows (Price: 50%, RSI: 25%, MACD: 25%)
    gs = fig.add_gridspec(3, 1, height_ratios=[2.2, 1, 1], hspace=0.15)
    
    ax_price = fig.add_subplot(gs[0])
    ax_rsi = fig.add_subplot(gs[1], sharex=ax_price)
    ax_macd = fig.add_subplot(gs[2], sharex=ax_price)

    for ax in [ax_price, ax_rsi, ax_macd]:
        ax.set_facecolor('#1C1C1E')
        ax.grid(True, color='#2C2C2E', linestyle='--', linewidth=0.5, alpha=0.7)
        ax.tick_params(colors='#8E8E93', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#38383A')

    # 1. Price Panel (Candlestick / Close + MAs)
    dates = plot_df.index
    
    # Plot candlestick representations
    up = plot_df[plot_df['Close'] >= plot_df['Open']]
    down = plot_df[plot_df['Close'] < plot_df['Open']]
    
    col_up = '#10B981'
    col_down = '#EF4444'

    # High / Low wicks
    ax_price.vlines(up.index, up['Low'], up['High'], color=col_up, linewidth=0.8, alpha=0.8)
    ax_price.vlines(down.index, down['Low'], down['High'], color=col_down, linewidth=0.8, alpha=0.8)

    # Open / Close bodies (approximated by vlines with thicker width or bar)
    ax_price.vlines(up.index, up['Open'], up['Close'], color=col_up, linewidth=2.8)
    ax_price.vlines(down.index, down['Open'], down['Close'], color=col_down, linewidth=2.8)

    # Moving Averages
    fast_ma = tech.get("fast_ma_period", 50)
    slow_ma = tech.get("slow_ma_period", 200)
    
    if "MA_Fast" in plot_df.columns and not plot_df["MA_Fast"].isna().all():
        ax_price.plot(plot_df.index, plot_df["MA_Fast"], label=f"MA {fast_ma}", color='#64748B', linewidth=1.2)
    if "MA_Slow" in plot_df.columns and not plot_df["MA_Slow"].isna().all():
        ax_price.plot(plot_df.index, plot_df["MA_Slow"], label=f"MA {slow_ma}", color='#A78BFA', linewidth=1.2)

    # Support / Resistance lines
    support = tech.get("support")
    resistance = tech.get("resistance")
    if support:
        ax_price.axhline(support, color='#10B981', linestyle=':', linewidth=1.0, label=f'Sup: Rp {support:,.0f}')
    if resistance:
        ax_price.axhline(resistance, color='#EF4444', linestyle=':', linewidth=1.0, label=f'Res: Rp {resistance:,.0f}')

    latest_close = plot_df['Close'].iloc[-1]
    ax_price.set_title(f"{ticker.upper()} — Rp {latest_close:,.0f} | Technical Overview", color='#F5F5F7', fontsize=12, fontweight='bold', pad=10)
    ax_price.set_ylabel("Price (IDR)", color='#8E8E93', fontsize=9)
    ax_price.legend(loc='upper left', fontsize=8, facecolor='#111113', edgecolor='#38383A', labelcolor='#F5F5F7')

    # 2. RSI Panel
    rsi_period = tech.get("rsi_period", 14)
    if "RSI" in plot_df.columns:
        ax_rsi.plot(plot_df.index, plot_df["RSI"], color='#8E8E93', linewidth=1.2)
        ax_rsi.axhline(70, color='#EF4444', linestyle='--', linewidth=0.8, alpha=0.7)
        ax_rsi.axhline(30, color='#10B981', linestyle='--', linewidth=0.8, alpha=0.7)
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_ylabel(f"RSI ({rsi_period})", color='#8E8E93', fontsize=9)

    # 3. MACD Panel
    if "MACD" in plot_df.columns and "MACD_Signal" in plot_df.columns:
        ax_macd.plot(plot_df.index, plot_df["MACD"], label="MACD", color='#F5F5F7', linewidth=1.1)
        ax_macd.plot(plot_df.index, plot_df["MACD_Signal"], label="Signal", color='#64748B', linewidth=1.1)
        
        if "MACD_Hist" in plot_df.columns:
            hist = plot_df["MACD_Hist"]
            colors = [col_up if val >= 0 else col_down for val in hist]
            ax_macd.bar(plot_df.index, hist, color=colors, alpha=0.6, width=0.8)

        ax_macd.axhline(0, color='#38383A', linewidth=0.8)
        ax_macd.set_ylabel("MACD", color='#8E8E93', fontsize=9)
        ax_macd.legend(loc='upper left', fontsize=7, facecolor='#111113', edgecolor='#38383A', labelcolor='#F5F5F7')

    # Format X-axis dates cleanly
    ax_macd.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    fig.autofmt_xdate(rotation=30)
    plt.setp(ax_price.get_xticklabels(), visible=False)
    plt.setp(ax_rsi.get_xticklabels(), visible=False)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf
