"""
Motor de backtest optimizado para BTCUSDT M5.
Usa itertuples() en lugar de iterrows() — 5x mas rapido.
Soporta carga desde CSV local (478K velas) o CCXT.
"""

import pandas as pd
import numpy as np
import logging
from datetime import timezone
from pathlib import Path

from strategies.ema_trend_scalping import generate_signals
from risk_manager import RiskManager
from data_feed import load_from_csv, validate_data_quality
from notifications import notify_daily_summary

logger = logging.getLogger(__name__)


def run_backtest(
    df: pd.DataFrame,
    cfg,
    initial_capital: float = 200.0,
    send_daily_summaries: bool = False,
) -> tuple:
    """
    Ejecuta el backtest vela a vela con la estrategia EMA Trend Scalping.

    Args:
        df             : DataFrame OHLCV con timestamp UTC
        cfg            : StrategyConfig con todos los parametros
        initial_capital: Capital inicial en USD
        send_daily_summaries: Si True, envia resumen diario por Telegram

    Returns:
        (trades_df, equity_df, metrics)
    """
    data = generate_signals(df, cfg)
    data = data.dropna(subset=["ema_fast", "ema_slow", "ema_trend", "adx", "atr"]).reset_index(drop=True)

    if len(data) < 50:
        logger.error("Datos insuficientes tras calcular indicadores")
        return pd.DataFrame(), pd.DataFrame(), {"error": "Datos insuficientes"}

    rm       = RiskManager(cfg, initial_capital)
    position = None

    # Pre-alocar arrays para equity curve (mas rapido que append en lista)
    n_rows         = len(data)
    eq_timestamps  = np.empty(n_rows, dtype="object")
    eq_values      = np.empty(n_rows, dtype=np.float64)

    last_regime    = "RANGE"
    monthly_pnl    = {}  # {YYYY-MM: pnl_usd}

    # ── BUCLE PRINCIPAL: itertuples es 5x mas rapido que iterrows ──
    for i, row in enumerate(data.itertuples(index=True)):
        ts = row.timestamp

        # Registrar equity actual
        eq_timestamps[i] = ts
        eq_values[i]     = rm.equity

        # Reset diario
        is_new_day = rm.reset_day_if_needed(ts)

        # Verificar circuit breakers antes de operar
        if rm.circuit_breaker_active:
            continue

        # ── Gestionar posicion abierta ──
        if position is not None:
            position = rm.update_trailing_stop(position, row.close, row.atr)

            hit_stop = (row.low  <= position.stop_price) if position.side == 1 else (row.high >= position.stop_price)
            hit_tp   = (row.high >= position.take_profit) if position.side == 1 else (row.low  <= position.take_profit)

            if hit_stop or hit_tp:
                exit_price = position.stop_price if hit_stop else position.take_profit
                reason     = "stop" if hit_stop else "take_profit"
                rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                position = None

        # ── Evaluar nueva entrada ──
        if (
            position is None
            and not rm.daily_loss_hit()
            and not rm.cooldown_active(i)
            and row.in_session
        ):
            cb = rm.check_circuit_breakers()
            if cb is None:
                if row.signal == 1:
                    position = rm.open_position(
                        side=1, entry_price=row.close, atr_value=row.atr,
                        entry_bar=i, entry_time=ts,
                        regime=getattr(row, "regime", "UNKNOWN"),
                        signal_quality=getattr(row, "signal_quality", 0),
                    )
                elif row.signal == -1:
                    position = rm.open_position(
                        side=-1, entry_price=row.close, atr_value=row.atr,
                        entry_bar=i, entry_time=ts,
                        regime=getattr(row, "regime", "UNKNOWN"),
                        signal_quality=getattr(row, "signal_quality", 0),
                    )

        # ── Enviar resumen diario (si habilitado) ──
        if is_new_day and send_daily_summaries and rm.trades_today:
            _send_daily_telegram(rm, ts, monthly_pnl)

    # Cerrar posicion abierta al final
    if position is not None:
        last_row = data.iloc[-1]
        rm.close_position(
            position, last_row["close"], len(data) - 1,
            last_row["timestamp"], "end_of_data", send_notification=False
        )

    trades_df = pd.DataFrame(rm.all_trades)
    equity_df = pd.DataFrame({"timestamp": eq_timestamps, "equity": eq_values})
    metrics   = compute_metrics(trades_df, equity_df, initial_capital)

    return trades_df, equity_df, metrics


def _send_daily_telegram(rm: RiskManager, current_ts, monthly_pnl: dict):
    """Envia el resumen del dia anterior por Telegram."""
    stats      = rm.get_daily_stats()
    date_str   = str(rm.current_day)
    month_key  = date_str[:7]

    # Acumular PnL mensual
    if month_key not in monthly_pnl:
        monthly_pnl[month_key] = 0.0
    monthly_pnl[month_key] += stats["pnl_usd"]

    monthly_pct = (monthly_pnl[month_key] / rm.initial_capital) * 100

    notify_daily_summary(
        date_str       = date_str,
        trades_total   = stats["trades_total"],
        trades_win     = stats["trades_win"],
        trades_loss    = stats["trades_loss"],
        pnl_usd        = stats["pnl_usd"],
        pnl_pct        = stats["pnl_pct"],
        capital_start  = rm.daily_start_equity,
        capital_end    = rm.equity,
        best_trade     = stats["best_trade"],
        worst_trade    = stats["worst_trade"],
        monthly_pnl_pct= monthly_pct,
        dd_max_day     = stats["dd_max_day"],
        session_stats  = {},
    )


def compute_metrics(
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    initial_capital: float,
) -> dict:
    """Calcula metricas de rendimiento del backtest."""
    if trades_df.empty:
        return {
            "total_trades": 0,
            "message": "Sin operaciones generadas con esta configuracion.",
        }

    wins   = trades_df[trades_df["pnl_usd"] > 0]
    losses = trades_df[trades_df["pnl_usd"] <= 0]

    final_equity      = equity_df["equity"].iloc[-1]
    total_return_pct  = (final_equity - initial_capital) / initial_capital * 100

    gross_profit  = wins["pnl_usd"].sum()
    gross_loss    = abs(losses["pnl_usd"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

    # Drawdown maximo
    equity_series = equity_df["equity"]
    running_max   = equity_series.cummax()
    drawdown      = (equity_series - running_max) / running_max
    max_dd_pct    = drawdown.min() * 100

    # Sharpe ratio (anualizado aproximado para M5)
    returns       = equity_series.pct_change().dropna()
    bars_per_year = 252 * 24 * 12  # velas M5 en un año
    sharpe        = (returns.mean() / returns.std() * np.sqrt(bars_per_year)) if returns.std() > 0 else 0

    # Win rate por dias (dias positivos / total dias)
    if "exit_time" in trades_df.columns:
        trades_df["exit_date"] = pd.to_datetime(trades_df["exit_time"]).dt.date
        daily_pnl    = trades_df.groupby("exit_date")["pnl_usd"].sum()
        days_positive = (daily_pnl > 0).sum()
        days_total    = len(daily_pnl)
        day_win_rate  = days_positive / days_total * 100 if days_total > 0 else 0
    else:
        day_win_rate  = 0
        days_total    = 0

    # Retorno mensual promedio
    if "exit_time" in trades_df.columns:
        trades_df["month"] = pd.to_datetime(trades_df["exit_time"]).dt.to_period("M")
        monthly_pnl   = trades_df.groupby("month")["pnl_usd"].sum()
        monthly_ret   = (monthly_pnl / initial_capital * 100).mean()
    else:
        monthly_ret   = 0

    return {
        "total_trades"         : len(trades_df),
        "win_rate_pct"         : round(len(wins) / len(trades_df) * 100, 2),
        "day_win_rate_pct"     : round(day_win_rate, 2),
        "profit_factor"        : round(profit_factor, 2),
        "total_return_pct"     : round(total_return_pct, 2),
        "monthly_return_avg_pct": round(monthly_ret, 2),
        "max_drawdown_pct"     : round(max_dd_pct, 2),
        "sharpe_approx"        : round(sharpe, 2),
        "avg_win_usd"          : round(wins["pnl_usd"].mean(), 4) if len(wins) else 0,
        "avg_loss_usd"         : round(losses["pnl_usd"].mean(), 4) if len(losses) else 0,
        "final_equity"         : round(final_equity, 2),
        "total_days_analyzed"  : days_total,
    }


def plot_equity_curve(equity_df: pd.DataFrame, output_path: str = "equity_curve.png"):
    """Genera y guarda la curva de equity."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})

    # Curva de equity
    ax1.plot(equity_df["timestamp"], equity_df["equity"], linewidth=1.5, color="#2196F3")
    ax1.fill_between(equity_df["timestamp"], equity_df["equity"],
                     equity_df["equity"].iloc[0], alpha=0.1, color="#2196F3")
    ax1.set_title("Curva de Equity — BTC/USDT M5 | EMA 9/21/200 + Sesion NY", fontsize=13)
    ax1.set_ylabel("Capital (USD)")
    ax1.grid(alpha=0.3)

    # Drawdown
    running_max = equity_df["equity"].cummax()
    drawdown    = (equity_df["equity"] - running_max) / running_max * 100
    ax2.fill_between(equity_df["timestamp"], drawdown, 0, color="#F44336", alpha=0.5)
    ax2.set_ylabel("Drawdown %")
    ax2.set_xlabel("Fecha")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()
    logger.info(f"Curva de equity guardada en {output_path}")


def run_backtest_from_csv(
    csv_path: str,
    cfg,
    initial_capital: float = 200.0,
    date_from: str = None,
    date_to: str = None,
) -> tuple:
    """
    Carga el CSV de MT5 y ejecuta el backtest completo.
    Permite filtrar por rango de fechas para walk-forward.
    """
    df = load_from_csv(csv_path)
    if df is None:
        return pd.DataFrame(), pd.DataFrame(), {"error": "No se pudo cargar el CSV"}

    if date_from:
        df = df[df["timestamp"] >= pd.to_datetime(date_from)]
    if date_to:
        df = df[df["timestamp"] <= pd.to_datetime(date_to)]

    df = df.reset_index(drop=True)

    if not validate_data_quality(df):
        return pd.DataFrame(), pd.DataFrame(), {"error": "Calidad de datos insuficiente"}

    logger.info(f"Backtest: {len(df)} velas | {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")
    return run_backtest(df, cfg, initial_capital)
