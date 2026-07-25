#!/usr/bin/env python3
"""
Optimización específica BTC/USDT H1 con ATFS.
Busca PF > 1.2 y retorno positivo.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import itertools
import pandas as pd
from config import STRATEGY
from data_feed import load_from_csv
from strategies.atfs import generate_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/btc_usdt_h1.csv"
CAPITAL = 200.0

def run_atfs_opt(adx_threshold=22, atr_sl_mult=1.5, trailing_mult=1.0, tp_activation=1.5, time_stop_bars=12, session_hours=list(range(8,21))):
    df = load_from_csv(CSV)
    if df is None:
        return {}
    
    from dataclasses import replace
    cfg = replace(
        STRATEGY,
        adx_threshold=adx_threshold,
        atr_sl_mult=atr_sl_mult,
        atr_tp_mult=3.0,
        session_hours_utc=session_hours,
        trading_days=[0,1,2,3,4],
        use_trailing_stop=True,
        trailing_atr_mult=trailing_mult,
        risk_per_trade=0.01,
        max_daily_loss=0.03,
        max_drawdown_total=0.12,
        cooldown_bars_after_loss=3,
        min_atr_pct=0.005,
    )
    cfg.time_stop_bars = time_stop_bars
    
    data = generate_signals(df, cfg)
    sig_col = "signal_atfs"
    data = data.dropna(subset=["ema_fast","ema_slow","adx","atr","close",sig_col,"in_session"]).reset_index(drop=True)
    if len(data) < 50:
        return {}
    
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
            if (i - position.entry_bar) >= time_stop_bars:
                pnl = rm.close_position(position, row.close, i, ts, "time_stop", send_notification=False)
                trades.append({"pnl_usd": pnl, "reason": "time_stop", "bars": i-position.entry_bar})
                position = None
                continue
            hit_stop = (row.low <= position.stop_price) if position.side==1 else (row.high >= position.stop_price)
            hit_tp = (row.high >= position.take_profit) if position.side==1 else (row.low <= position.take_profit)
            if hit_stop or hit_tp:
                exit_price = position.stop_price if hit_stop else position.take_profit
                reason = "stop" if hit_stop else "take_profit"
                pnl = rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                trades.append({"pnl_usd": pnl, "reason": reason, "bars": i-position.entry_bar})
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
            stop = row.close - atr_val * atr_sl_mult if side == 1 else row.close + atr_val * atr_sl_mult
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
        trades.append({"pnl_usd": pnl, "reason": "end_of_data", "bars": len(data)-1-position.entry_bar})
    
    if not trades:
        return {}
    
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
    
    return {
        "adx": adx_threshold, "sl": atr_sl_mult, "trail": trailing_mult,
        "activation": tp_activation, "ts": time_stop_bars,
        "trades": len(trades_df), "win_rate": round(wr, 2),
        "pf": round(pf, 2), "ret": round(ret, 2), "dd": round(max_dd, 2),
        "final_eq": round(final_eq, 2)
    }

print("="*80)
print("OPTIMIZACIÓN ESPECÍFICA — BTC/USDT H1 con ATFS")
print("="*80)

configs = []
for adx in [20, 22, 25]:
    for sl in [1.0, 1.5, 2.0]:
        for trail in [0.8, 1.0, 1.2]:
            for act in [1.0, 1.5, 2.0]:
                for ts in [8, 12, 16]:
                    configs.append((adx, sl, trail, act, ts))

best_pf = -999
best_ret = -999
best_params = None
all_results = []

for i, (adx, sl, trail, act, ts) in enumerate(configs, 1):
    m = run_atfs_opt(adx, sl, trail, act, ts)
    if not m:
        continue
    all_results.append(m)
    if m["pf"] > best_pf or (m["pf"] == best_pf and m["ret"] > best_ret):
        best_pf = m["pf"]
        best_ret = m["ret"]
        best_params = m
    if i % 20 == 0:
        print(f"  {i}/{len(configs)} | mejor PF: {best_pf:.2f}, ret: {best_ret:.2f}%")

res_df = pd.DataFrame(all_results)
res_df.to_csv("/workspaces/TradingAIProject/iteration_history_btc_h1_atfs.csv", index=False)

print("\n" + "="*80)
print("MEJOR CONFIGURACIÓN BTC/USDT H1")
print("="*80)
if best_params:
    print(f"ADX threshold : {best_params['adx']}")
    print(f"SL mult       : {best_params['sl']}")
    print(f"Trailing mult : {best_params['trail']}")
    print(f"Activación    : {best_params['activation']}")
    print(f"Time stop     : {best_params['ts']} barras")
    print(f"Trades        : {best_params['trades']}")
    print(f"Win Rate      : {best_params['win_rate']:.2f}%")
    print(f"PF            : {best_params['pf']:.2f}")
    print(f"Retorno       : {best_params['ret']:.2f}%")
    print(f"Max DD        : {best_params['dd']:.2f}%")
    print(f"Capital final : ${best_params['final_eq']:.2f}")
else:
    print("No se encontró ninguna configuración válida.")

print("\nTop 10 por Profit Factor:")
print(res_df.nlargest(10, "pf")[["adx","sl","trail","activation","ts","trades","win_rate","pf","ret","dd"]].to_string(index=False))
