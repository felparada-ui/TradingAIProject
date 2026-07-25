#!/usr/bin/env python3
"""
Backtest ATFS (Adaptive Trend-Following System) sobre BCH/USDT H1.
Compara baseline EMA Trend vs ATFS rediseñado.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
from datetime import datetime
from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals as generate_ema_signals
from strategies.atfs import generate_signals as generate_atfs_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
CAPITAL = 200.0


def detect_timeframe(df):
    diffs = df["timestamp"].diff().dropna().dt.total_seconds().div(60)
    mode = diffs.value_counts().idxmax()
    if mode <= 10:
        return "m5"
    elif mode <= 60:
        return "h1"
    elif mode <= 1440:
        return "d1"
    return "unknown"


def run_backtest(df, strategy_name="ATFS", use_atfs=False, session_hours_utc=None, adx_threshold=20.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=12, use_trailing=True, trailing_mult=1.0, tp_activation_mult=1.5):
    tf = detect_timeframe(df)
    if tf == "h1":
        session_hours_utc = session_hours_utc or list(range(8, 21))
    elif tf == "m5":
        session_hours_utc = session_hours_utc or list(range(0, 24))
    else:
        session_hours_utc = session_hours_utc or list(range(8, 21))

    from dataclasses import replace
    cfg = replace(
        STRATEGY,
        adx_threshold=adx_threshold,
        atr_sl_mult=atr_sl_mult,
        atr_tp_mult=atr_tp_mult,
        session_hours_utc=session_hours_utc,
        trading_days=[0, 1, 2, 3, 4],
        use_trailing_stop=use_trailing,
        trailing_atr_mult=trailing_mult,
        risk_per_trade=0.01,
        max_daily_loss=0.03,
        max_drawdown_total=0.12,
        cooldown_bars_after_loss=3,
        min_atr_pct=0.005,
    )
    cfg.time_stop_bars = time_stop_bars

    data = add_all_indicators(df, cfg)
    if use_atfs:
        data = generate_atfs_signals(data, cfg)
        signal_col = "signal_atfs"
    else:
        data = generate_ema_signals(data, cfg)
        signal_col = "signal"

    data = data.dropna(subset=["ema_fast", "ema_slow", "adx", "atr", "close", signal_col]).reset_index(drop=True)
    if len(data) < 50:
        return pd.DataFrame(), pd.DataFrame(), {"error": "insufficient_data"}

    rm = RiskManager(cfg, CAPITAL)
    position = None
    trades = []
    eq_values = []
    eq_ts = []

    for i, row in enumerate(data.itertuples(index=True)):
        ts = row.timestamp
        eq_ts.append(ts)
        eq_values.append(rm.equity)

        rm.reset_day_if_needed(ts)
        if rm.circuit_breaker_active:
            continue

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
                    "strategy": strategy_name,
                })
                position = None
                continue

            # SL/TP hit
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
                    "strategy": strategy_name,
                })
                position = None

        # Entrada
        if position is None:
            if rm.daily_loss_hit() or rm.cooldown_active(i) or not getattr(row, "in_session", False):
                continue
            cb = rm.check_circuit_breakers()
            if cb:
                continue

            sig = getattr(row, signal_col, 0)
            if sig == 0:
                continue

            side = 1 if sig == 1 else -1
            atr_val = getattr(row, "atr", 0)
            if atr_val <= 0:
                continue

            # SL/TP para ATFS: trailing puro, sin TP fijo obligatorio
            stop = row.close - atr_val * atr_sl_mult if side == 1 else row.close + atr_val * atr_sl_mult
            # Inicializar TP muy lejos; el trailing stop se encargará de la salida
            tp = row.close + atr_val * atr_tp_mult if side == 1 else row.close - atr_val * atr_tp_mult

            size = rm.calc_position_size(row.close, stop)
            if size <= 0:
                continue

            position = rm.open_position(
                side=side, entry_price=row.close, atr_value=atr_val,
                entry_bar=i, entry_time=ts,
                regime=getattr(row, "regime", "UNKNOWN"),
                signal_quality=getattr(row, "signal_quality_atfs" if use_atfs else "signal_quality", 0),
                strategy=strategy_name,
            )
            if position is None:
                continue

            position.stop_price = stop
            position.take_profit = tp
            position._tp_activation = tp_activation_mult * atr_val
            position._trailing_mult = trailing_mult

    if position is not None:
        last = data.iloc[-1]
        pnl = rm.close_position(position, last["close"], len(data) - 1, last["timestamp"], "end_of_data", send_notification=False)
        trades.append({
            "entry_time": position.entry_time, "exit_time": last["timestamp"],
            "side": "long" if position.side == 1 else "short",
            "entry_price": position.entry_price, "exit_price": last["close"],
            "size": position.size, "pnl_usd": pnl, "reason": "end_of_data",
            "regime": position.regime, "duration_bars": len(data) - 1 - position.entry_bar,
            "strategy": strategy_name,
        })

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame({"timestamp": eq_ts, "equity": eq_values})
    metrics = compute_metrics(trades_df, equity_df, CAPITAL)
    metrics["timeframe"] = tf
    metrics["total_bars"] = len(data)
    metrics["strategy"] = strategy_name
    metrics["use_atfs"] = use_atfs
    metrics["params"] = f"ADX{adx_threshold}_SL{atr_sl_mult}_TP{atr_tp_mult}_TS{time_stop_bars}_TRAIL{trailing_mult}_ACT{tp_activation_mult}"
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
    bars_per_year = 252 * 24 if detect_timeframe(load_from_csv(CSV)) == "h1" else 252 * 24 * 12
    sharpe = (returns.mean() / returns.std() * bars_per_year**0.5) if returns.std() > 0 else 0
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


def main():
    print("=" * 70)
    print("  BACKTEST ATFS — Rediseño Estructural")
    print("=" * 70)

    df = load_from_csv(CSV)
    if df is None:
        print("No se pudo cargar el CSV.")
        return

    results = []

    # 1. Baseline EMA Trend H1
    print("\n1. Baseline EMA Trend H1")
    t1, e1, m1 = run_backtest(df, strategy_name="EMA_Trend_Baseline", use_atfs=False, session_hours_utc=list(range(8, 21)), adx_threshold=20.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=8)
    results.append({"iter": 1, "name": "EMA_Trend_Baseline", **m1})
    print(f"  Trades: {m1.get('total_trades',0)} | PF: {m1.get('profit_factor',0)} | Ret: {m1.get('total_return_pct',0)}% | DD: {m1.get('max_drawdown_pct',0)}%")

    # 2. ATFS v1: Trailing puro sin TP fijo
    print("\n2. ATFS v1 (trailing puro 1.0*ATR, activación 1.5*ATR)")
    t2, e2, m2 = run_backtest(df, strategy_name="ATFS_v1", use_atfs=True, session_hours_utc=list(range(8, 21)), adx_threshold=20.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=12, use_trailing=True, trailing_mult=1.0, tp_activation_mult=1.5)
    results.append({"iter": 2, "name": "ATFS_v1_TrailPure", **m2})
    print(f"  Trades: {m2.get('total_trades',0)} | PF: {m2.get('profit_factor',0)} | Ret: {m2.get('total_return_pct',0)}% | DD: {m2.get('max_drawdown_pct',0)}%")

    # 3. ATFS v2: Trailing 0.8*ATR, activación 1.0*ATR
    print("\n3. ATFS v2 (trailing 0.8*ATR, activación 1.0*ATR)")
    t3, e3, m3 = run_backtest(df, strategy_name="ATFS_v2", use_atfs=True, session_hours_utc=list(range(8, 21)), adx_threshold=20.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=12, use_trailing=True, trailing_mult=0.8, tp_activation_mult=1.0)
    results.append({"iter": 3, "name": "ATFS_v2_Trail08", **m3})
    print(f"  Trades: {m3.get('total_trades',0)} | PF: {m3.get('profit_factor',0)} | Ret: {m3.get('total_return_pct',0)}% | DD: {m3.get('max_drawdown_pct',0)}%")

    # 4. ATFS v3: ADX 22 + trailing 1.0*ATR
    print("\n4. ATFS v3 (ADX22, trailing 1.0*ATR)")
    t4, e4, m4 = run_backtest(df, strategy_name="ATFS_v3", use_atfs=True, session_hours_utc=list(range(8, 21)), adx_threshold=22.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=12, use_trailing=True, trailing_mult=1.0, tp_activation_mult=1.5)
    results.append({"iter": 4, "name": "ATFS_v3_ADX22", **m4})
    print(f"  Trades: {m4.get('total_trades',0)} | PF: {m4.get('profit_factor',0)} | Ret: {m4.get('total_return_pct',0)}% | DD: {m4.get('max_drawdown_pct',0)}%")

    # 5. ATFS v4: Sesión premium 13-17 UTC
    print("\n5. ATFS v4 (sesión 13-17 UTC)")
    t5, e5, m5 = run_backtest(df, strategy_name="ATFS_v4", use_atfs=True, session_hours_utc=[13, 14, 15, 16, 17], adx_threshold=22.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=12, use_trailing=True, trailing_mult=1.0, tp_activation_mult=1.5)
    results.append({"iter": 5, "name": "ATFS_v4_Premium", **m5})
    print(f"  Trades: {m5.get('total_trades',0)} | PF: {m5.get('profit_factor',0)} | Ret: {m5.get('total_return_pct',0)}% | DD: {m5.get('max_drawdown_pct',0)}%")

    # Guardar resultados
    results_df = pd.DataFrame(results)
    results_df.to_csv("/workspaces/TradingAIProject/iteration_history_atfs.csv", index=False)
    print("\nResultados guardados en iteration_history_atfs.csv")

    # Ranking
    print("\n" + "=" * 70)
    print("  RANKING DE CONFIGURACIONES")
    print("=" * 70)
    print(results_df[["iter", "name", "total_trades", "win_rate_pct", "profit_factor", "total_return_pct", "max_drawdown_pct"]].to_string(index=False))

    best = results_df.sort_values(by=["profit_factor", "total_return_pct"], ascending=False).iloc[0]
    print("\n" + "=" * 70)
    print("  CONFIGURACIÓN GANADORA")
    print("=" * 70)
    print(f"Iteración : {best['iter']} — {best['name']}")
    print(f"Trades    : {best['total_trades']}")
    print(f"Win Rate  : {best['win_rate_pct']:.2f}%")
    print(f"PF        : {best['profit_factor']:.2f}")
    print(f"Retorno   : {best['total_return_pct']:.2f}%")
    print(f"Max DD    : {best['max_drawdown_pct']:.2f}%")
    print(f"Sharpe    : {best['sharpe_approx']:.2f}")
    print(f"Capital   : ${best['final_equity']:.2f}")
    print(f"TP Hits   : {best.get('tp_exits', 0)} | SL Hits: {best.get('stop_exits',0)} | TimeStop: {best.get('time_stop_exits',0)}")


if __name__ == "__main__":
    main()
