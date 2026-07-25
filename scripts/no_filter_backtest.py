#!/usr/bin/env python3
"""
Backtest de 'trading ideal': ejecuta TODAS las señales generadas,
sin filtros de sesión, circuit breakers ni cooldowns.
Objetivo: medir el potencial intrínseco de la lógica EMA Trend.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
import numpy as np
from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
CAPITAL = 200.0

df = load_from_csv(CSV)
data = generate_signals(df, STRATEGY)
data = data.dropna(subset=["ema_fast", "ema_slow", "adx", "atr", "close", "signal"]).reset_index(drop=True)

print(f"Total velas: {len(data)}")
print(f"Señales totales: {(data['signal']!=0).sum()}")

# Ejecutar backtest sin filtros (solo señal -> entrada)
rm = RiskManager(STRATEGY, CAPITAL)
position = None
trades = []
eq_values = []
eq_ts = []

for i, row in enumerate(data.itertuples(index=True)):
    ts = row.timestamp
    eq_ts.append(ts)
    eq_values.append(rm.equity)

    if position is not None:
        position = rm.update_trailing_stop(position, row.close, row.atr)
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

    if position is None and row.signal != 0:
        side = 1 if row.signal == 1 else -1
        atr_val = row.atr
        stop = row.close - atr_val * 1.5 if side == 1 else row.close + atr_val * 1.5
        tp = row.close + atr_val * 2.5 if side == 1 else row.close - atr_val * 2.5
        size = rm.calc_position_size(row.close, stop)
        if size <= 0:
            continue
        position = rm.open_position(
            side=side, entry_price=row.close, atr_value=atr_val,
            entry_bar=i, entry_time=ts,
            regime=getattr(row, "regime", "UNKNOWN"),
            signal_quality=getattr(row, "signal_quality", 0),
            strategy="EMA_Trend_NoFilter",
        )
        if position is None:
            continue
        position.stop_price = stop
        position.take_profit = tp

if position is not None:
    last = data.iloc[-1]
    pnl = rm.close_position(position, last["close"], len(data)-1, last["timestamp"], "end_of_data", send_notification=False)
    trades.append({
        "entry_time": position.entry_time, "exit_time": last["timestamp"],
        "side": "long" if position.side == 1 else "short",
        "entry_price": position.entry_price, "exit_price": last["close"],
        "size": position.size, "pnl_usd": pnl, "reason": "end_of_data",
        "regime": position.regime, "duration_bars": len(data)-1 - position.entry_bar,
    })

trades_df = pd.DataFrame(trades)
if trades_df.empty:
    print("No se generaron trades incluso sin filtros.")
    sys.exit(0)

wins = trades_df[trades_df["pnl_usd"] > 0]
losses = trades_df[trades_df["pnl_usd"] <= 0]
gross_profit = wins["pnl_usd"].sum() if len(wins) else 0
gross_loss = abs(losses["pnl_usd"].sum()) if len(losses) else 0
pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
wr = len(wins) / len(trades_df) * 100
ret = (rm.equity - CAPITAL) / CAPITAL * 100

running_max = pd.Series(eq_values).cummax()
dd = (pd.Series(eq_values) - running_max) / running_max
max_dd = dd.min() * 100

print(f"\n=== BACKTEST SIN FILTROS (potencial intrínseco) ===")
print(f"Trades: {len(trades_df)}")
print(f"Win Rate: {wr:.2f}%")
print(f"Profit Factor: {pf:.2f}")
print(f"Retorno total: {ret:.2f}%")
print(f"Max Drawdown: {max_dd:.2f}%")
print(f"Capital final: ${rm.equity:.2f}")
print(f"TP hits: {len(trades_df[trades_df['reason']=='take_profit'])}")
print(f"SL hits: {len(trades_df[trades_df['reason']=='stop'])}")
print(f"EOD: {len(trades_df[trades_df['reason']=='end_of_data'])}")

if len(wins) > 0 and len(losses) > 0:
    print(f"Avg Win: ${wins['pnl_usd'].mean():.4f}")
    print(f"Avg Loss: ${losses['pnl_usd'].mean():.4f}")
    print(f"Win/Loss ratio: {abs(wins['pnl_usd'].mean() / losses['pnl_usd'].mean()):.2f}")

print("\nDistribución de PnL:")
print(trades_df["pnl_usd"].describe())

print("\nPnL por régimen:")
print(trades_df.groupby("regime")["pnl_usd"].agg(["count","sum","mean"]))

# Guardar
trades_df.to_csv("trades_no_filter_bch_h1.csv", index=False)
print("\nCSV guardado: trades_no_filter_bch_h1.csv")
