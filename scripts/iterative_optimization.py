#!/usr/bin/env python3
"""
Optimización iterativa de estrategia sobre BCH/USDT H1.
Evalúa combinaciones de parámetros y registra métricas en CSV.
Se detiene temprano si encuentra PF > 1.0 y Max DD < 15%.
"""

import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import itertools
import pandas as pd
from datetime import datetime
from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals as generate_ema_signals
from strategies.vwap_mean_reversion import generate_signals as generate_vwap_signals
from strategies.donchian_breakout import generate_signals as generate_donchian_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
CAPITAL = 200.0
OUT_CSV = "/workspaces/TradingAIProject/iteration_history_bch_h1.csv"


def detect_timeframe(df: pd.DataFrame) -> str:
    diffs = df["timestamp"].diff().dropna().dt.total_seconds().div(60)
    mode = diffs.value_counts().idxmax()
    if mode <= 10:
        return "m5"
    elif mode <= 60:
        return "h1"
    elif mode <= 1440:
        return "d1"
    return "unknown"


def run_backtest_iteration(
    csv_path: str,
    initial_capital: float = 200.0,
    session_hours_utc: list = None,
    adx_threshold: float = 20.0,
    atr_sl_mult: float = 1.0,
    atr_tp_mult: float = 2.0,
    time_stop_bars: int = None,
    use_vwap: bool = False,
    use_donchian: bool = False,
    trend_filter_h4: bool = False,
) -> dict:
    df = load_from_csv(csv_path)
    if df is None:
        return {"error": "no_csv"}

    tf = detect_timeframe(df)
    if tf != "h1":
        return {"error": f"unexpected_tf:{tf}"}

    from dataclasses import replace
    cfg = replace(
        STRATEGY,
        adx_threshold=adx_threshold,
        atr_sl_mult=atr_sl_mult,
        atr_tp_mult=atr_tp_mult,
        session_hours_utc=session_hours_utc if session_hours_utc is not None else list(range(0, 24)),
        trading_days=[0, 1, 2, 3, 4],
        use_trailing_stop=True,
        trailing_atr_mult=0.8,
        risk_per_trade=0.01,
        max_daily_loss=0.03,
        max_drawdown_total=0.12,
        cooldown_bars_after_loss=3,
        min_atr_pct=0.005,
    )
    cfg.time_stop_bars = time_stop_bars

    # Trend filter H4: cargar datos H4 y calcular EMA50/EMA200
    h4_trend = None
    if trend_filter_h4:
        try:
            h4_df = df.copy()
            h4_df = h4_df.set_index("timestamp").resample("4H").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna().reset_index()
            h4_df = add_all_indicators(h4_df, cfg)
            h4_df["h4_bullish"] = h4_df["ema_fast"] > h4_df["ema_slow"]
            h4_df["h4_bearish"] = h4_df["ema_fast"] < h4_df["ema_slow"]
            h4_trend = h4_df[["timestamp", "h4_bullish", "h4_bearish"]].copy()
        except Exception as e:
            h4_trend = None

    data = add_all_indicators(df, cfg)
    data = generate_ema_signals(data, cfg)
    if use_vwap:
        data_vwap = generate_vwap_signals(df.copy(), cfg)
        data["signal_vwap"] = data_vwap["signal_vwap"]
        data["vwap"] = data_vwap["vwap"]
    if use_donchian:
        data_don = generate_donchian_signals(df.copy(), cfg)
        data["signal_donchian"] = data_don["signal_donchian"]

    data = data.dropna(subset=["ema_fast", "ema_slow", "adx", "atr", "close", "signal"]).reset_index(drop=True)
    if len(data) < 50:
        return {"error": "insufficient_data", "rows": len(data)}

    rm = RiskManager(cfg, initial_capital)
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

        # Gestionar posición abierta
        if position is not None:
            position = rm.update_trailing_stop(position, row.close, row.atr)

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

            hit_stop = (row.low <= position.stop_price) if position.side == 1 else (row.high >= position.stop_price)
            hit_tp = (row.high >= position.take_profit) if position.side == 1 else (row.low <= position.take_profit)

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
            if rm.daily_loss_hit() or rm.cooldown_active(i) or not row.in_session:
                continue
            cb = rm.check_circuit_breakers()
            if cb:
                continue

            sig = 0
            strategy_name = "EMA"
            if row.signal != 0:
                sig = row.signal
                strategy_name = "EMA_Trend"
            elif use_vwap and getattr(row, "signal_vwap", 0) != 0:
                sig = row.signal_vwap
                strategy_name = "VWAP_MR"
            elif use_donchian and getattr(row, "signal_donchian", 0) != 0:
                sig = row.signal_donchian
                strategy_name = "Donchian"

            if sig == 0:
                continue

            # Trend filter H4
            if trend_filter_h4 and h4_trend is not None:
                ts_h4 = pd.Timestamp(ts).floor("4H")
                h4_row = h4_trend[h4_trend["timestamp"] == ts_h4]
                if not h4_row.empty:
                    if sig == 1 and not h4_row.iloc[0]["h4_bullish"]:
                        continue
                    if sig == -1 and not h4_row.iloc[0]["h4_bearish"]:
                        continue

            side = 1 if sig == 1 else -1
            atr_val = getattr(row, "atr", 0)
            if atr_val <= 0:
                continue

            if strategy_name == "VWAP_MR":
                tp_val = getattr(row, "vwap", None)
                if tp_val is None or pd.isna(tp_val):
                    continue
                stop = row.close - atr_val * 1.0 if side == 1 else row.close + atr_val * 1.0
                tp = tp_val
            else:
                stop = row.close - atr_val * atr_sl_mult if side == 1 else row.close + atr_val * atr_sl_mult
                tp = row.close + atr_val * atr_tp_mult if side == 1 else row.close - atr_val * atr_tp_mult

            size = rm.calc_position_size(row.close, stop)
            if size <= 0:
                continue

            position = rm.open_position(
                side=side, entry_price=row.close, atr_value=atr_val,
                entry_bar=i, entry_time=ts,
                regime=getattr(row, "regime", "UNKNOWN"),
                signal_quality=getattr(row, "signal_quality", 0),
                strategy=strategy_name,
            )
            if position is None:
                continue

            position.stop_price = stop
            position.take_profit = tp

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
    metrics["params"] = f"ADX{adx_threshold}_SL{atr_sl_mult}_TP{atr_tp_mult}_TS{time_stop_bars}_SES{len(session_hours_utc)}"
    metrics["use_vwap"] = use_vwap
    metrics["use_donchian"] = use_donchian
    metrics["trend_filter_h4"] = trend_filter_h4
    return metrics


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
    bars_per_year = 252 * 24
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
    print("=" * 60)
    print("  OPTIMIZACIÓN ITERATIVA — BCH/USDT H1")
    print("=" * 60)

    iterations = []

    # Iteration 1: Baseline H1 con SL 1.5, TP 2.5, sesión 8-20
    print("\nIteración 1: Baseline H1 (ADX20, SL1.5, TP2.5, sesión 8-20)")
    m1 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=list(range(8, 21)), adx_threshold=20.0, atr_sl_mult=1.5, atr_tp_mult=2.5, time_stop_bars=8)
    m1["iteration"] = 1
    m1["description"] = "Baseline H1"
    iterations.append(m1)
    print(f"  -> Trades: {m1.get('total_trades',0)} | PF: {m1.get('profit_factor',0)} | Ret: {m1.get('total_return_pct',0)}% | DD: {m1.get('max_drawdown_pct',0)}%")

    # Iteration 2: ADX 25 (tendencias más fuertes)
    print("\nIteración 2: ADX 25 + SL 1.5 + TP 3.0")
    m2 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=list(range(8, 21)), adx_threshold=25.0, atr_sl_mult=1.5, atr_tp_mult=3.0, time_stop_bars=8)
    m2["iteration"] = 2
    m2["description"] = "ADX25 + TP3.0"
    iterations.append(m2)
    print(f"  -> Trades: {m2.get('total_trades',0)} | PF: {m2.get('profit_factor',0)} | Ret: {m2.get('total_return_pct',0)}% | DD: {m2.get('max_drawdown_pct',0)}%")

    # Iteration 3: ADX 25 + trend filter H4
    print("\nIteración 3: ADX25 + TP3.0 + Filtro H4")
    m3 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=list(range(8, 21)), adx_threshold=25.0, atr_sl_mult=1.5, atr_tp_mult=3.0, time_stop_bars=8, trend_filter_h4=True)
    m3["iteration"] = 3
    m3["description"] = "ADX25 + TP3.0 + H4"
    iterations.append(m3)
    print(f"  -> Trades: {m3.get('total_trades',0)} | PF: {m3.get('profit_factor',0)} | Ret: {m3.get('total_return_pct',0)}% | DD: {m3.get('max_drawdown_pct',0)}%")

    # Iteration 4: VWAP MR standalone
    print("\nIteración 4: VWAP MR standalone")
    m4 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=list(range(8, 21)), adx_threshold=22.0, atr_sl_mult=1.0, atr_tp_mult=2.0, time_stop_bars=8, use_vwap=True)
    m4["iteration"] = 4
    m4["description"] = "VWAP_MR"
    iterations.append(m4)
    print(f"  -> Trades: {m4.get('total_trades',0)} | PF: {m4.get('profit_factor',0)} | Ret: {m4.get('total_return_pct',0)}% | DD: {m4.get('max_drawdown_pct',0)}%")

    # Iteration 5: Donchian standalone
    print("\nIteración 5: Donchian Breakout standalone")
    m5 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=list(range(8, 21)), adx_threshold=25.0, atr_sl_mult=1.5, atr_tp_mult=3.0, time_stop_bars=8, use_donchian=True)
    m5["iteration"] = 5
    m5["description"] = "Donchian"
    iterations.append(m5)
    print(f"  -> Trades: {m5.get('total_trades',0)} | PF: {m5.get('profit_factor',0)} | Ret: {m5.get('total_return_pct',0)}% | DD: {m5.get('max_drawdown_pct',0)}%")

    # Iteration 6: Ensemble EMA + VWAP + Donchian con selección por régimen
    print("\nIteración 6: Ensemble (EMA+VWAP+Donchian) por régimen")
    m6 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=list(range(8, 21)), adx_threshold=20.0, atr_sl_mult=1.0, atr_tp_mult=2.0, time_stop_bars=8, use_vwap=True, use_donchian=True, trend_filter_h4=True)
    m6["iteration"] = 6
    m6["description"] = "Ensemble"
    iterations.append(m6)
    print(f"  -> Trades: {m6.get('total_trades',0)} | PF: {m6.get('profit_factor',0)} | Ret: {m6.get('total_return_pct',0)}% | DD: {m6.get('max_drawdown_pct',0)}%")

    # Iteration 7: Sesión premium 13-17 UTC + ADX25 + TP3.0
    print("\nIteración 7: Sesión 13-17 UTC + ADX25 + TP3.0")
    m7 = run_backtest_iteration(CSV, CAPITAL, session_hours_utc=[13, 14, 15, 16, 17], adx_threshold=25.0, atr_sl_mult=1.5, atr_tp_mult=3.0, time_stop_bars=8, trend_filter_h4=True)
    m7["iteration"] = 7
    m7["description"] = "Premium_Session + H4"
    iterations.append(m7)
    print(f"  -> Trades: {m7.get('total_trades',0)} | PF: {m7.get('profit_factor',0)} | Ret: {m7.get('total_return_pct',0)}% | DD: {m7.get('max_drawdown_pct',0)}%")

    # Guardar historial
    results = pd.DataFrame(iterations)
    results.to_csv(OUT_CSV, index=False)
    print(f"\nHistorial guardado en {OUT_CSV}")

    # Seleccionar mejores configuraciones
    viable = results[
        (results["profit_factor"] > 1.0) &
        (results["max_drawdown_pct"] > -15.0) &
        (results["total_trades"] >= 5)
    ].copy()

    if not viable.empty:
        viable["score"] = viable["profit_factor"] + (viable["total_return_pct"] / 100.0) - (abs(viable["max_drawdown_pct"]) / 100.0)
        best = viable.sort_values("score", ascending=False).iloc[0]
        print("\n" + "=" * 60)
        print("  CONFIGURACIÓN ÓPTIMA ENCONTRADA")
        print("=" * 60)
        print(f"Iteración : {best['iteration']} - {best['description']}")
        print(f"Trades    : {best['total_trades']}")
        print(f"Win Rate  : {best['win_rate_pct']:.2f}%")
        print(f"PF        : {best['profit_factor']:.2f}")
        print(f"Retorno   : {best['total_return_pct']:.2f}%")
        print(f"Max DD    : {best['max_drawdown_pct']:.2f}%")
        print(f"Sharpe    : {best['sharpe_approx']:.2f}")
        print(f"Capital final: ${best['final_equity']:.2f}")
        print(f"Avg Win/Loss: ${best['avg_win_usd']:.4f} / ${best['avg_loss_usd']:.4f}")
    else:
        print("\n" + "=" * 60)
        print("  NO SE ENCONTRÓ CONFIGURACIÓN RENTABLE")
        print("=" * 60)
        print("Se recomienda revisar el activo/timeframe o la lógica de entrada/salida.")

    print("\nResumen de todas las iteraciones:")
    print(results[["iteration", "description", "total_trades", "win_rate_pct", "profit_factor", "total_return_pct", "max_drawdown_pct", "sharpe_approx"]].to_string(index=False))


if __name__ == "__main__":
    main()
