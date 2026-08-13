import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from analysis.quant import compute_quant_factors
from analysis.portfolio import optimize_portfolio


def render_quant_tab(data: dict, tech: dict, fund: dict, ticker: str) -> None:
    st.markdown("## 🔬 Level 2 Quant & Portfolio Lab")
    st.caption("Multi-Factor Factor Models & Markowitz Mean-Variance Portfolio Optimization")
    st.divider()

    # SECTION 1: MULTI-FACTOR QUANT SCORE FOR ANALYZED TICKER
    st.markdown(f"### 📊 Multi-Factor Equity Model — **{ticker}**")

    history = data.get("history")
    info = data.get("info")
    sector = data.get("basic", {}).get("sector")

    quant = compute_quant_factors(
        info=info,
        history=history,
        sector=sector,
        quarterly_income=data.get("quarterly_income"),
        quarterly_balance=data.get("quarterly_balance"),
    )

    comp_score = quant.get("composite_score", 0)
    grade = quant.get("grade", "N/A")
    factors = quant.get("factors", {})

    col_score, col_radar = st.columns([0.45, 0.55])

    with col_score:
        st.markdown(f"""
        <div style="background:#1C1C1E;padding:24px;border-radius:16px;border:1px solid #38383A;">
            <div style="font-size:0.75rem;color:#8E8E93;text-transform:uppercase;letter-spacing:0.1em;">
                Composite Multi-Factor Quant Rating
            </div>
            <div style="font-size:2.8rem;font-weight:700;color:#F5F5F7;margin:8px 0;">
                {comp_score:.1f} <span style="font-size:1.4rem;color:#30D158;">/ 100</span>
            </div>
            <div style="font-size:1.1rem;font-weight:600;color:#30D158;">
                Factor Grade: <span style="background:#30D158;color:#000;padding:2px 10px;border-radius:8px;">{grade}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")

        # 4 Factor summary metrics
        v_s = factors.get("value", {}).get("score", 0)
        q_s = factors.get("quality", {}).get("score", 0)
        m_s = factors.get("momentum", {}).get("score", 0)
        l_s = factors.get("low_volatility", {}).get("score", 0)

        m1, m2 = st.columns(2)
        m1.metric("Value Factor", f"{v_s:.1f} / 100", help="Earnings Yield, Book Yield, Div Yield")
        m2.metric("Quality Factor", f"{q_s:.1f} / 100", help="ROE, ROA, Net Margin, Debt Safety")

        m3, m4 = st.columns(2)
        m3.metric("Momentum Factor", f"{m_s:.1f} / 100", help="1M, 3M, 6M Risk-Adjusted Momentum")
        m4.metric("Low Volatility Factor", f"{l_s:.1f} / 100", help="Realized Volatility, Downside Vol, Beta")

    with col_radar:
        categories = ["Value", "Quality", "Momentum", "Low Volatility"]
        scores = [v_s, q_s, m_s, l_s]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=categories + [categories[0]],
            fill='toself',
            name=ticker,
            line=dict(color='#10B981', width=2),
            fillcolor='rgba(16, 185, 129, 0.25)'
        ))
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], gridcolor='#38383A', tickfont=dict(color='#8E8E93')),
                angularaxis=dict(gridcolor='#38383A', tickfont=dict(color='#F5F5F7', size=11)),
                bgcolor='rgba(0,0,0,0)',
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=320,
            margin=dict(l=40, r=40, t=30, b=30),
            showlegend=False
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    st.divider()

    # SECTION 2: MARKOWITZ MEAN-VARIANCE PORTFOLIO OPTIMIZER
    st.markdown("### 🧮 Markowitz Mean-Variance Portfolio Optimizer")
    st.caption("Computes mathematically optimal capital allocation weights (%) to maximize Sharpe Ratio for a custom basket of stocks.")

    default_basket = f"{ticker}, BBRI, TLKM, ICBP, ASII"
    basket_input = st.text_input("Enter Ticker Basket (comma-separated)", value=default_basket, help="Enter 2 to 10 ticker symbols")

    opt_period = st.selectbox("Historical Lookback Period for Covariance & Returns", options=["6 Months", "1 Year", "2 Years", "3 Years"], index=1)
    period_map = {"6 Months": "6m", "1 Year": "1y", "2 Years": "2y", "3 Years": "3y"}

    if st.button("🚀 Optimize Portfolio Allocation", type="primary", use_container_width=True):
        tickers_list = [t.strip() for t in basket_input.split(",") if t.strip()]

        with st.spinner("Computing optimal portfolio weights & Efficient Frontier..."):
            res = optimize_portfolio(tickers_list, period=period_map[opt_period])

        if res.get("error"):
            st.error(res["error"])
        else:
            max_s = res["max_sharpe"]
            min_v = res["min_volatility"]
            eq_w = res["equal_weight"]

            st.success("✅ Portfolio Optimization Complete!")

            c1, c2, c3 = st.columns(3)
            c1.metric("Max Sharpe Expected Return", f"{max_s['expected_return']:.2f}%")
            c2.metric("Max Sharpe Annual Volatility", f"{max_s['volatility']:.2f}%")
            c3.metric("Max Sharpe Ratio", f"{max_s['sharpe_ratio']:.2f}")

            p_col1, p_col2 = st.columns(2)

            with p_col1:
                st.markdown("#### 🎯 Max Sharpe Optimal Weights")
                w_df = pd.DataFrame({
                    "Ticker": list(max_s["weights"].keys()),
                    "Optimal Weight (%)": list(max_s["weights"].values())
                })
                fig_pie = px.pie(
                    w_df, values="Optimal Weight (%)", names="Ticker",
                    color_discrete_sequence=px.colors.sequential.Darkmint_r,
                    hole=0.4
                )
                fig_pie.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#F5F5F7"),
                    height=300
                )
                st.plotly_chart(fig_pie, use_container_width=True)
                st.dataframe(w_df, use_container_width=True, hide_index=True)

            with p_col2:
                st.markdown("#### 📉 Efficient Frontier Risk / Return Curve")
                ef_data = res.get("efficient_frontier", [])
                if ef_data:
                    ef_df = pd.DataFrame(ef_data)
                    fig_ef = px.line(ef_df, x="volatility", y="return", labels={"volatility": "Volatility (%)", "return": "Expected Return (%)"})
                    fig_ef.add_trace(go.Scatter(
                        x=[max_s["volatility"]], y=[max_s["expected_return"]],
                        mode="markers+text", name="Max Sharpe",
                        text=["⭐ Max Sharpe"], textposition="top center",
                        marker=dict(size=14, color="#30D158")
                    ))
                    fig_ef.add_trace(go.Scatter(
                        x=[min_v["volatility"]], y=[min_v["expected_return"]],
                        mode="markers+text", name="Min Volatility",
                        text=["🛡️ Min Vol"], textposition="bottom center",
                        marker=dict(size=12, color="#64748B")
                    ))
                    fig_ef.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#F5F5F7"),
                        height=300,
                        margin=dict(l=20, r=20, t=20, b=20)
                    )
                    st.plotly_chart(fig_ef, use_container_width=True)
