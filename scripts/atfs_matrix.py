#!/usr/bin/env python3
"""
Backtest ATFS en múltiples activos/timeframes.
Genera matriz comparativa 2x3: BCH y BTC en H1, M15, M5.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
from config import STRATEGY
from data_feed import load_from_csv
from strategies.atfs import generate_signals as generate_atfs_signals
from risk_manager import RiskManager

CAPITAL = 200.0

CONFIGS = [
    # Activo, TF, CSV, sesión, ADX, SL, TP/time_stop
    ("BCH", "H1", "/workspaces/TradingAIProject/data/bch_usdt_h1.csv", list(range(8,21)), 22, 1.5, 12),
    ("BCH", "M15", "/workspaces/TradingAIProject/data/bch_usdt_m15.csv", list(range(8,21)), 22, 1.5, 8),
    ("BCH", "M5", "/workspaces/TradingAIProject/data/bch_usdt_m5.csv", list(range(8,21)), 22, 1.5, 16),
    ("BTC", "H1", "/workspaces/TradingAIProject/data/btc_usdt_h1.csv", list(range(8,21)), 22, 1.5, 12),
    ("BTC", "M15", "/workspaces/TradingAIProject/data/btc_usdt_m15.csv", list(range(8,21)), 22, 1.5, 8),
    ("BTC", "M5", "/workspaces/TradingAIProject/data/btc_usdt_m5.csv", list(range(8,21)), 22, 1.5, 16),
]

def detect_tf(df):
    diffs = df["timestamp"].diff().dropna().dt.total_seconds().div(60)
    mode = diffs.value_counts().idxmax()
    if mode <= 10: return "m5"
    if mode <= 60: return "h1"
    if mode <= 1440: return "d1"
    return "unknown"

def run_atfs(csv_path, session_hours, adx, sl_mult, ts_bars):
    df = load_from_csv(csv_path)
    if df is None:
        return {"error": "no_csv"}
    
    tf = detect_tf(df)
    from dataclasses import replace
    cfg = replace(
        STRATEGY,
        adx_threshold=adx,
        atr_sl_mult=sl_mult,
        atr_tp_mult=3.0,
        session_hours_utc=session_hours,
        trading_days=[0,1,2,3,4],
        use_trailing_stop=True,
        trailing_atr_mult=1.0,
        risk_per_trade=0.01,
        max_daily_loss=0.03,
        max_drawdown_total=0.12,
        cooldown_bars_after_loss=3,
        min_atr_pct=0.005,
    )
    cfg.time_stop_bars = ts_bars

    data = generate_atfs_signals(df, cfg)
    sig_col = "signal_atfs"
    data = data.dropna(subset=["ema_fast","ema_slow","adx","atr","close",sig_col,"in_session"]).reset_index(drop=True)
    if len(data) < 50:
        return {"error": "insufficient_data", "rows": len(data)}
    
    rm = RiskManager(cfg, CAPITAL)
    position = None
    trades = []
    eq = []
    eq_ts = []

    for i, row in enumerate(data.itertuples(index=True)):
        ts = row.timestamp
        eq_ts.append(ts)
        eq.append(rm.equity)
        rm.reset_day_if_needed(ts)
        if rm.circuit_breaker_active:
            continue

        if position is not None:
            position = rm.update_trailing_stop(position, row.close, row.atr)
            if (i - position.entry_bar) >= ts_bars:
                pnl = rm.close_position(position, row.close, i, ts, "time_stop", send_notification=False)
                trades.append({"pnl_usd": pnl, "reason": "time_stop", "bars": i-position.entry_bar, "side": position.side})
                position = None
                continue
            hit_stop = (row.low <= position.stop_price) if position.side==1 else (row.high >= position.stop_price)
            hit_tp = (row.high >= position.take_profit) if position.side==1 else (row.low <= position.take_profit)
            if hit_stop or hit_tp:
                exit_price = position.stop_price if hit_stop else position.take_profit
                reason = "stop" if hit_stop else "take_profit"
                pnl = rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                trades.append({"pnl_usd": pnl, "reason": reason, "bars": i-position.entry_bar, "side": position.side})
                position = None

        if position is None:
            if rm.daily_loss_hit() or rm.cooldown_active(i) or not getattr(row, "in_session", False):
                continue
            cb = rm.check_circuit_breakers()
            if cb:
                continue
            
            sig = getattr(row, sig_col, 0)
            if sig == 0:
                continue
            side = 1 if sig == 1 else -1
            atr_val = getattr(row, "atr", 0)
            if atr_val <= 0:
                continue
            
            stop = row.close - atr_val * sl_mult if side == 1 else row.close + atr_val * sl_mult
            tp = row.close + atr_val * 3.0 if side == 1 else row.close - atr_val * 3.0
            
            size = rm.calc_position_size(row.close, stop)
            if size <= 0:
                continue
            
            position = rm.open_position(side=side, entry_price=row.close, atr_value=atr_val,
                                       entry_bar=i, entry_time=ts, regime=getattr(row, "regime", "UNKNOWN"),
                                       signal_quality=getattr(row, "signal_quality_atfs", 0), strategy="ATFS")
            if position is None:
                continue
            position.stop_price = stop
            position.take_profit = tp
    
    if position is not None:
        last = data.iloc[-1]
        pnl = rm.close_position(position, last["close"], len(data)-1, last["timestamp"], "end_of_data", send_notification=False)
        trades.append({"pnl_usd": pnl, "reason": "end_of_data", "bars": len(data)-1-position.entry_bar, "side": position.side})
    
    if not trades:
        return {
            "asset": "?", "tf": tf, "rows": len(data), "trades": 0,
            "win_rate_pct": 0, "profit_factor": 0, "total_return_pct": 0,
            "max_drawdown_pct": 0, "sharpe_approx": 0, "final_equity": CAPITAL,
            "stop_exits": 0, "time_stop_exits": 0, "tp_exits": 0, "avg_bars": 0
        }
    
    trades_df = pd.DataFrame(trades)
    final_eq = eq[-1] if eq else CAPITAL
    wins = trades_df[trades_df["pnl_usd"] > 0]
    losses = trades_df[trades_df["pnl_usd"] <= 0]
    pf = wins["pnl_usd"].sum() / abs(losses["pnl_usd"].sum()) if len(losses) else float("inf")
    ret = (final_eq - CAPITAL) / CAPITAL * 100
    wr = len(wins) / len(trades_df) * 100
    running = pd.Series(eq).cummax()
    dd = (pd.Series(eq) - running) / running
    max_dd = dd.min() * 100
    returns = pd.Series(eq).pct_change().dropna()
    bars_per_year = {"m5": 252*24*12, "h1": 252*24, "m15": 252*24*4}.get(tf, 252*24)
    sharpe = (returns.mean() / returns.std() * bars_per_year**0.5) if returns.std() > 0 else 0
    
    return {
        "asset": "?", "tf": tf, "rows": len(data), "trades": len(trades_df),
        "win_rate_pct": round(wr, 2), "profit_factor": round(pf, 2),
        "total_return_pct": round(ret, 2), "max_drawdown_pct": round(max_dd, 2),
        "sharpe_approx": round(sharpe, 2), "final_equity": round(final_eq, 2),
        "stop_exits": int((trades_df["reason"]=="stop").sum()),
        "time_stop_exits": int((trades_df["reason"]=="time_stop").sum()),
        "tp_exits": int((trades_df["reason"]=="take_profit").sum()),
        "avg_bars": round(trades_df["bars"].mean(), 1)
    }

print("="*90)
print("MATRIZ COMPARATIVA ATFS — Multi-Activo / Multi-Timeframe")
print("="*90)

results=[]
for asset, tf, csv, session, adx, sl, ts in CONFIGS:
    print(f"\nEjecutando: {asset} {tf} ...")
    m = run_atfs(csv, session, adx, sl, ts)
    m["asset"] = asset
    m["timeframe"] = tf
    results.append(m)
    print(f"  -> Trades: {m.get('trades',0)} | PF: {m.get('profit_factor',0)} | Ret: {m.get('total_return_pct',0)}% | DD: {m.get('max_drawdown_pct',0)}%")

res_df = pd.DataFrame(results)
res_df.to_csv("/workspaces/TradingAIProject/iteration_history_atfs_matrix.csv", index=False)

print("\n" + "="*90)
print("RESULTADOS CONSOLIDADOS")
print("="*90)
print(res_df[["asset","timeframe","trades","win_rate_pct","profit_factor","total_return_pct","max_drawdown_pct","sharpe_approx","final_equity"]].to_string(index=False))

best = res_df.loc[res_df["profit_factor"].idxmax()]
print("\n" + "="*90)
print("CONFIGURACIÓN GANADORA")
print("="*90)
print(f"Activo    : {best['asset']}/USDT")
print(f"Timeframe : {best['timeframe']}")
print(f"Trades    : {best['trades']}")
print(f"Win Rate  : {best['win_rate_pct']:.2f}%")
print(f"PF        : {best['profit_factor']:.2f}")
print(f"Retorno   : {best['total_return_pct']:.2f}%")
print(f"Max DD    : {best['max_drawdown_pct']:.2f}%")
print(f"Sharpe    : {best['sharpe_approx']:.2f}")
print(f"Capital   : ${best['final_equity']:.2f}")
