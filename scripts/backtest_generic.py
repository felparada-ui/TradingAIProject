#!/usr/bin/env python3
"""
Backtest genérico para cualquier CSV OHLCV y timeframe.
Uso:
  python scripts/backtest_generic.py --csv ruta/archivo.csv [--timeframe h1] [--capital 200]
"""

import sys
import argparse
import pandas as pd
import numpy as np
import logging
from pathlib import Path

sys.path.insert(0, "/workspaces/TradingAIProject")

from data_feed import load_from_csv
from indicators import add_all_indicators
from risk_manager import RiskManager, Position

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def detect_timeframe(df: pd.DataFrame) -> str:
    diffs = df["timestamp"].diff().dropna().dt.total_seconds().div(60)
    mode = diffs.value_counts().idxmax()
    if mode <= 10:
        return "m5"
    elif mode <= 60:
        return "h1"
    elif mode <= 1440:
        return "d1"
    else:
        return "unknown"


def run_backtest(
    csv_path: str,
    initial_capital: float = 200.0,
    session_hours_utc: list = None,
    trading_days: list = None,
    adx_threshold: float = 20.0,
    atr_sl_mult: float = 1.0,
    atr_tp_mult: float = 2.0,
    trailing_atr_mult: float = 0.8,
    cooldown_bars: int = 3,
    max_daily_loss: float = 0.05,
    max_drawdown_total: float = 0.15,
    risk_per_trade: float = 0.01,
    time_stop_bars: int = None,
    min_atr_pct: float = 0.0,
) -> tuple:
    df = load_from_csv(csv_path)
    if df is None:
        logger.error("No se pudo cargar el CSV.")
        return pd.DataFrame(), pd.DataFrame(), {}

    tf = detect_timeframe(df)
    logger.info(f"Timeframe detectado: {tf} | Filas: {len(df)}")
    if tf == "unknown":
        logger.warning("No se pudo detectar el timeframe. Se usará configuración por defecto.")

    from dataclasses import replace
    from config import STRATEGY as _BASE_CFG

    cfg_params = {
        "timeframe": tf,
        "adx_threshold": adx_threshold,
        "atr_sl_mult": atr_sl_mult,
        "atr_tp_mult": atr_tp_mult,
        "use_trailing_stop": True,
        "trailing_atr_mult": trailing_atr_mult,
        "session_hours_utc": session_hours_utc,
        "trading_days": trading_days,
        "cooldown_bars_after_loss": cooldown_bars,
        "max_daily_loss": max_daily_loss,
        "max_drawdown_total": max_drawdown_total,
        "risk_per_trade": risk_per_trade,
        "min_atr_pct": min_atr_pct,
    }
    cfg_params = {k: v for k, v in cfg_params.items() if v is not None}
    try:
        cfg = replace(_BASE_CFG, **cfg_params)
    except Exception as e:
        logger.warning(f"No se pudo usar replace StrategyConfig: {e}")
        cfg = _BASE_CFG
    cfg.time_stop_bars = time_stop_bars
    if not hasattr(cfg, "time_stop_bars") or getattr(cfg, "time_stop_bars") is None:
        cfg.time_stop_bars = time_stop_bars

    data = add_all_indicators(df, cfg)
    try:
        from strategies.ema_trend_scalping import generate_signals as _gen_signals
        data = _gen_signals(data, cfg)
    except Exception as e:
        logger.warning(f"No se pudo generar señales de estrategia: {e}")
    data = data.dropna(subset=["ema_fast", "ema_slow", "ema_trend", "adx", "atr", "close"]).reset_index(drop=True)
    if len(data) < 50:
        logger.error("Datos insuficientes tras calcular indicadores.")
        return pd.DataFrame(), pd.DataFrame(), {}

    logger.info(f"Filas válidas post-indicadores: {len(data)}")

    rm = RiskManager(cfg, initial_capital)
    position = None
    trades = []
    eq_values = np.empty(len(data), dtype=np.float64)
    eq_ts = np.empty(len(data), dtype="object")

    for i, row in enumerate(data.itertuples(index=True)):
        ts = row.timestamp
        eq_ts[i] = ts
        eq_values[i] = rm.equity

        rm.reset_day_if_needed(ts)
        if rm.circuit_breaker_active:
            continue

        # Gestionar posición abierta
        if position is not None:
            position = rm.update_trailing_stop(position, row.close, row.atr)

            # Time stop
            if time_stop_bars and (i - position.entry_bar) >= time_stop_bars:
                exit_price = row.close
                reason = "time_stop"
                pnl = rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                trades.append({
                    "entry_time": position.entry_time, "exit_time": ts,
                    "side": "long" if position.side == 1 else "short",
                    "entry_price": position.entry_price, "exit_price": exit_price,
                    "size": position.size, "pnl_usd": pnl, "reason": reason,
                    "regime": position.regime, "duration_bars": i - position.entry_bar,
                })
                position = None
                continue

            # Hit SL/TP
            if position.side == 1:
                hit_stop = row.low <= position.stop_price
                hit_tp = row.high >= position.take_profit
            else:
                hit_stop = row.high >= position.stop_price
                hit_tp = row.low <= position.take_profit

            if hit_stop or hit_tp:
                exit_price = position.stop_price if hit_stop else position.take_profit
                reason = "stop" if hit_stop else "take_profit"
                pnl = rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                trades.append({
                    "entry_time": position.entry_time, "exit_time": ts,
                    "side": "long" if position.side == 1 else "short",
                    "entry_price": position.entry_price, "exit_price": exit_price,
                    "size": position.size, "pnl_usd": pnl, "reason": reason,
                    "regime": position.regime, "duration_bars": i - position.entry_bar,
                })
                position = None

        # Evaluar entrada
        if position is None:
            if rm.daily_loss_hit() or rm.cooldown_active(i) or not getattr(row, "in_session", False):
                continue
            cb = rm.check_circuit_breakers()
            if cb:
                continue
            if getattr(row, "atr_pct", 0) < min_atr_pct:
                continue

            sig = getattr(row, "signal", 0)
            if sig == 0:
                continue

            side = 1 if sig == 1 else -1
            atr_val = getattr(row, "atr", 0)
            if atr_val <= 0:
                continue

            stop = row.close - atr_val * atr_sl_mult if side == 1 else row.close + atr_val * atr_sl_mult
            tp = row.close + atr_val * atr_tp_mult * side if side == 1 else row.close - atr_val * atr_tp_mult

            size = rm.calc_position_size(row.close, stop)
            if size <= 0:
                continue

            position = rm.open_position(
                side=side, entry_price=row.close, atr_value=atr_val,
                entry_bar=i, entry_time=ts,
                regime=getattr(row, "regime", "UNKNOWN"),
                signal_quality=getattr(row, "signal_quality", 0),
                strategy="EMA_Trend_H1",
            )
            if position is None:
                continue

            position.stop_price = stop
            position.take_profit = tp

    # Cerrar posición abierta al final
    if position is not None:
        last = data.iloc[-1]
        pnl = rm.close_position(position, last["close"], len(data) - 1, last["timestamp"], "end_of_data", send_notification=False)
        trades.append({
            "entry_time": position.entry_time, "exit_time": last["timestamp"],
            "side": "long" if position.side == 1 else "short",
            "entry_price": position.entry_price, "exit_price": last["close"],
            "size": position.size, "pnl_usd": pnl, "reason": "end_of_data",
            "regime": position.regime, "duration_bars": len(data) - 1 - position.entry_bar,
        })

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame({"timestamp": eq_ts, "equity": eq_values})
    metrics = compute_metrics(trades_df, equity_df, initial_capital)
    metrics["timeframe"] = tf
    metrics["total_bars"] = len(data)
    return trades_df, equity_df, metrics


def compute_metrics(trades_df, equity_df, initial_capital):
    if trades_df.empty:
        return {
            "total_trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "total_return_pct": 0.0, "max_drawdown_pct": 0.0,
            "sharpe_approx": 0.0, "avg_win_usd": 0.0, "avg_loss_usd": 0.0,
            "final_equity": initial_capital, "avg_duration_bars": 0,
            "time_stop_exits": 0, "stop_exits": 0, "tp_exits": 0,
        }

    wins = trades_df[trades_df["pnl_usd"] > 0]
    losses = trades_df[trades_df["pnl_usd"] <= 0]
    final_equity = equity_df["equity"].iloc[-1]
    total_return = (final_equity - initial_capital) / initial_capital * 100
    gross_profit = wins["pnl_usd"].sum()
    gross_loss = abs(losses["pnl_usd"].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max) / running_max
    max_dd = drawdown.min() * 100

    returns = equity_df["equity"].pct_change().dropna()
    bars_per_year = {"m5": 252 * 24 * 12, "h1": 252 * 24, "d1": 252}.get(equity_df.get("timeframe", ["h1"])[0] if "timeframe" in equity_df.columns else "h1", 252 * 24)
    sharpe = (returns.mean() / returns.std() * np.sqrt(bars_per_year)) if returns.std() > 0 else 0

    win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) else 0
    avg_dur = trades_df["duration_bars"].mean() if "duration_bars" in trades_df.columns else 0

    return {
        "total_trades": len(trades_df),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_approx": round(sharpe, 2),
        "avg_win_usd": round(wins["pnl_usd"].mean(), 4) if len(wins) else 0,
        "avg_loss_usd": round(losses["pnl_usd"].mean(), 4) if len(losses) else 0,
        "final_equity": round(final_equity, 2),
        "avg_duration_bars": round(avg_dur, 1),
        "time_stop_exits": len(trades_df[trades_df["reason"] == "time_stop"]),
        "stop_exits": len(trades_df[trades_df["reason"] == "stop"]),
        "tp_exits": len(trades_df[trades_df["reason"] == "take_profit"]),
    }


def print_metrics(name, m):
    print(f"\n[{name}]")
    print(f"  Timeframe            : {m.get('timeframe', 'N/A')}")
    print(f"  Total velas          : {m.get('total_bars', 'N/A')}")
    print(f"  Trades               : {m['total_trades']}")
    print(f"  Win Rate             : {m['win_rate_pct']:.2f}%")
    print(f"  Profit Factor        : {m['profit_factor']:.2f}")
    print(f"  Retorno total        : {m['total_return_pct']:.2f}%")
    print(f"  Max Drawdown         : {m['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe (approx)      : {m['sharpe_approx']:.2f}")
    print(f"  Avg Win/Loss         : ${m['avg_win_usd']:.4f} / ${m['avg_loss_usd']:.4f}")
    print(f"  Capital final        : ${m['final_equity']:.2f}")
    print(f"  Duracion promedio    : {m.get('avg_duration_bars', 0):.1f} barras")
    print(f"  Salidas              : TP={m.get('tp_exits',0)} | SL={m.get('stop_exits',0)} | TimeStop={m.get('time_stop_exits',0)}")


def main():
    parser = argparse.ArgumentParser(description="Backtest genérico CSV -> métricas")
    parser.add_argument("--csv", required=True, help="Ruta al CSV OHLCV")
    parser.add_argument("--capital", type=float, default=200.0)
    parser.add_argument("--adx", type=float, default=20.0)
    parser.add_argument("--sl-mult", type=float, default=1.0)
    parser.add_argument("--tp-mult", type=float, default=2.0)
    parser.add_argument("--trailing", type=float, default=0.8)
    parser.add_argument("--cooldown", type=int, default=3)
    parser.add_argument("--max-daily-loss", type=float, default=0.05)
    parser.add_argument("--max-dd", type=float, default=0.15)
    parser.add_argument("--risk", type=float, default=0.01)
    parser.add_argument("--time-stop", type=int, default=None)
    parser.add_argument("--min-atr-pct", type=float, default=0.0)
    args = parser.parse_args()

    print("\n" + "=" * 58)
    print("  BACKTEST GENERICO | CSV -> Metricas")
    print("=" * 58)

    trades_df, equity_df, metrics = run_backtest(
        csv_path=args.csv,
        initial_capital=args.capital,
        adx_threshold=args.adx,
        atr_sl_mult=args.sl_mult,
        atr_tp_mult=args.tp_mult,
        trailing_atr_mult=args.trailing,
        cooldown_bars=args.cooldown,
        max_daily_loss=args.max_daily_loss,
        max_drawdown_total=args.max_dd,
        risk_per_trade=args.risk,
        time_stop_bars=args.time_stop,
        min_atr_pct=args.min_atr_pct,
    )

    if trades_df.empty:
        print("\nNo se generaron trades con esta configuración.")
        return

    print_metrics("RESULTADOS", metrics)
    trades_df.to_csv("trades_backtest_generic.csv", index=False)
    print("\nCSV guardado: trades_backtest_generic.csv")


if __name__ == "__main__":
    main()
