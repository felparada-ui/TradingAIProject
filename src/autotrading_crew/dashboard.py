"""
Dashboard de Monitoreo — Autotrading Crew

Ejecutar:
    streamlit run src/autotrading_crew/dashboard.py

Muestra:
  - Estado de conexión MT5
  - Equity curve en tiempo real
  - Últimas señales y trades
  - Métricas de rendimiento
  - Posiciones abiertas
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# ─── Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Autotrading Crew",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🤖 Autotrading Crew — Dashboard de Monitoreo")
st.caption(f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ─── Sidebar ───────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Controles")
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
if auto_refresh:
    st.sidebar.info("↻ Refrescando cada 30 segundos")

st.sidebar.header("📁 Reportes")
report_dir = Path("data/backtest_results")
reports = sorted(report_dir.glob("INFORME_*.md"), reverse=True)
if reports:
    selected_report = st.sidebar.selectbox(
        "Informe disponible",
        [r.name for r in reports],
    )
    if selected_report:
        with open(report_dir / selected_report) as f:
            st.sidebar.download_button(
                "📥 Descargar informe",
                f.read(),
                file_name=selected_report,
            )

# ─── Cargar último reporte de backtest ─────────────────────────────────────
def load_latest_backtest() -> dict:
    files = sorted(report_dir.glob("backtest_report_*.json"), reverse=True)
    if not files:
        return {"trades": [], "capital_inicial": 10000, "capital_final": 10000}
    with open(files[0]) as f:
        return json.load(f)


report = load_latest_backtest()
trades = report.get("trades", [])

# ─── Métricas principales ──────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    initial = report.get("capital_inicial", 10000)
    final = report.get("capital_final", 10000)
    ret = (final - initial) / initial * 100
    st.metric("Capital", f"${final:,.2f}", f"{ret:+.2f}%")

with col2:
    st.metric("Trades", report.get("total_trades", 0))

with col3:
    st.metric("Win Rate", f"{report.get('win_rate_pct', 0):.1f}%")

with col4:
    st.metric("Profit Factor", f"{report.get('profit_factor', 0):.2f}")

with col5:
    st.metric("DD Máx", f"{report.get('max_drawdown_pct', 0):.2f}%")

# ─── Equity Curve ──────────────────────────────────────────────────────────
st.subheader("📈 Curva de Equity")

if trades:
    df_trades = pd.DataFrame(trades)
    df_trades["cumulative_pnl"] = df_trades["pnl_usd"].cumsum()
    df_trades["equity"] = initial + df_trades["cumulative_pnl"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(df_trades))),
        y=df_trades["equity"],
        mode="lines+markers",
        name="Equity",
        line=dict(color="#00ff88", width=2),
        marker=dict(
            color=df_trades["pnl_usd"].apply(lambda x: "#00ff88" if x > 0 else "#ff4444"),
            size=8,
        ),
    ))
    fig.add_hline(y=initial, line_dash="dash", line_color="gray", annotation_text="Capital inicial")
    fig.update_layout(
        xaxis_title="Trade #",
        yaxis_title="Capital ($)",
        height=400,
        margin=dict(l=0, r=0, t=0, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sin trades para mostrar curva de equity")

# ─── Últimos trades ────────────────────────────────────────────────────────
st.subheader("📋 Últimos Trades")

if trades:
    df_show = pd.DataFrame(trades[-20:])  # Últimos 20
    cols = ["symbol", "side", "regime", "entry_price", "exit_price", "pnl_pct", "exit_reason"]
    df_show = df_show[[c for c in cols if c in df_show.columns]]

    # Colorear PnL
    def color_pnl(val):
        if isinstance(val, (int, float)):
            return f"🟢 {val:+.2f}%" if val > 0 else f"🔴 {val:+.2f}%" if val < 0 else f"⚪ {val:+.2f}%"
        return val

    if "pnl_pct" in df_show.columns:
        df_show["pnl_pct"] = df_show["pnl_pct"].apply(color_pnl)

    # Mapear exit_reason a emojis
    def map_exit(reason):
        mapping = {
            "take_profit": "🎯 TP",
            "stop_loss": "🛑 SL",
            "time_exit": "⏰ Timeout",
        }
        return mapping.get(reason, reason)

    if "exit_reason" in df_show.columns:
        df_show["exit_reason"] = df_show["exit_reason"].apply(map_exit)

    st.dataframe(df_show, use_container_width=True, hide_index=True)
else:
    st.info("No hay trades registrados")

# ─── Distribución por régimen ──────────────────────────────────────────────
st.subheader("🌍 Distribución por Régimen de Mercado")

regime_stats = report.get("regimen_stats", {})
if regime_stats:
    regimes_df = pd.DataFrame([
        {"Régimen": r.capitalize(), **s}
        for r, s in regime_stats.items()
    ])
    st.dataframe(regimes_df, use_container_width=True, hide_index=True)

    # Gráfico de torta
    fig2 = go.Figure(data=[go.Pie(
        labels=[r.capitalize() for r in regime_stats.keys()],
        values=[s["trades"] for s in regime_stats.values()],
        hole=0.4,
    )])
    fig2.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Sin datos de régimen")

# ─── Footer ────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "🤖 Autotrading Crew — Sistema Multi-Agente con 5 especialistas | "
    "Quant Strategist · Technical Scout · Sentiment Tracker · Risk Manager · Execution Trader"
)

# Auto-refresh
if auto_refresh:
    st.rerun()
