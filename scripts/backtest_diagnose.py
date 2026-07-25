#!/usr/bin/env python3
"""Backtest con contadores de rechazo para diagnosticar por qué hay tan pocos trades."""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
import numpy as np
from config import STRATEGY
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/btc_usdt_m5.csv"
df = pd.read_csv(CSV)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp").reset_index(drop=True)

data = generate_signals(df, STRATEGY)
data = data.dropna(subset=["ema_fast","ema_slow","ema_trend","adx","atr"]).reset_index(drop=True)
print(f"Filas válidas: {len(data)}")

rm = RiskManager(STRATEGY, 200.0)
position = None

counters = {
    "eval_entry": 0,
    "open_succ": 0,
    "open_reject_cb": 0,
    "open_reject_cooldown": 0,
    "open_reject_session": 0,
    "open_reject_daily_loss": 0,
    "open_reject_size": 0,
    "close_stop": 0,
    "close_tp": 0,
    "close_eod": 0,
}

for i, row in enumerate(data.itertuples(index=True)):
    # Cerrar posición si corresponde
    if position is not None:
        position = rm.update_trailing_stop(position, row.close, row.atr)
        hit_stop = (row.low <= position.stop_price) if position.side == 1 else (row.high >= position.stop_price)
        hit_tp   = (row.high >= position.take_profit) if position.side == 1 else (row.low <= position.take_profit)
        if hit_stop:
            rm.close_position(position, position.stop_price, i, row.timestamp, "stop", send_notification=False)
            position = None
            counters["close_stop"] += 1
        elif hit_tp:
            rm.close_position(position, position.take_profit, i, row.timestamp, "take_profit", send_notification=False)
            position = None
            counters["close_tp"] += 1

    if position is None:
        counters["eval_entry"] += 1
        if rm.daily_loss_hit():
            counters["open_reject_daily_loss"] += 1
            continue
        if rm.cooldown_active(i):
            counters["open_reject_cooldown"] += 1
            continue
        if not row.in_session:
            counters["open_reject_session"] += 1
            continue
        cb = rm.check_circuit_breakers()
        if cb:
            counters["open_reject_cb"] += 1
            continue
        if row.signal == 1:
            pos = rm.open_position(side=1, entry_price=row.close, atr_value=row.atr, entry_bar=i, entry_time=row.timestamp, regime=getattr(row, "regime", "UNKNOWN"), signal_quality=getattr(row, "signal_quality", 0))
            if pos is None:
                counters["open_reject_size"] += 1
            else:
                position = pos
                counters["open_succ"] += 1
        elif row.signal == -1:
            pos = rm.open_position(side=-1, entry_price=row.close, atr_value=row.atr, entry_bar=i, entry_time=row.timestamp, regime=getattr(row, "regime", "UNKNOWN"), signal_quality=getattr(row, "signal_quality", 0))
            if pos is None:
                counters["open_reject_size"] += 1
            else:
                position = pos
                counters["open_succ"] += 1

if position is not None:
    last = data.iloc[-1]
    rm.close_position(position, last["close"], len(data)-1, last["timestamp"], "end_of_data", send_notification=False)
    counters["close_eod"] += 1

print("\nContadores:")
for k,v in counters.items():
    print(f"  {k}: {v}")
print(f"Equity final: {rm.equity:.2f}")
print(f"Trades totales: {len(rm.all_trades)}")
if rm.all_trades:
    pnls = [t["pnl_usd"] for t in rm.all_trades]
    print(f"Ganancia media: {np.mean([p for p in pnls if p>0]):.4f}")
    print(f"Perdida media: {np.mean([p for p in pnls if p<=0]):.4f}")
    print(f"Win rate: {len([p for p in pnls if p>0])/len(pnls)*100:.2f}%")
    print(f"Profit Factor: {sum([p for p in pnls if p>0])/abs(sum([p for p in pnls if p<=0])):.2f}")
