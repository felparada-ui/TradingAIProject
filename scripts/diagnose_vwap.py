#!/usr/bin/env python3
"""Diagnóstico rápido de señales VWAP MR generadas sobre el dataset."""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
import numpy as np
from config import STRATEGY
from indicators import add_all_indicators
from strategies.vwap_mean_reversion import generate_signals as generate_vwap_signals

CSV = "/workspaces/TradingAIProject/data/btc_usdt_m5.csv"
df = pd.read_csv(CSV)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp").reset_index(drop=True)

data = generate_vwap_signals(df, STRATEGY)
signals = data[data["signal_vwap"] != 0].copy()

print(f"Señales VWAP MR totales: {len(signals)}")
print(f"  Longs : {(signals['signal_vwap']==1).sum()}")
print(f"  Shorts: {(signals['signal_vwap']==-1).sum()}")

if not signals.empty:
    signals["hour"] = signals["timestamp"].dt.hour
    print("\nSeñales por hora UTC (top 10):")
    print(signals["hour"].value_counts().sort_index().head(15))

    print("\nADX promedio en señales:", signals["adx"].mean())
    print("ADX < 20:", (signals["adx"] < 20).sum())
    print("ADX < 22:", (signals["adx"] < 22).sum())
    print("ADX < 25:", (signals["adx"] < 25).sum())

    print("\nRSI promedio en señales:", signals["rsi"].mean())
    print("RSI en señales long:", signals.loc[signals["signal_vwap"]==1, "rsi"].mean())
    print("RSI en señales short:", signals.loc[signals["signal_vwap"]==-1, "rsi"].mean())

    print("\nDistancia a VWAP en señales (close - vwap) / atr:")
    signals["dist_vwap_atr"] = (signals["close"] - signals["vwap"]) / signals["atr"]
    print("  Long  (esperado < -1.0):", signals.loc[signals["signal_vwap"]==1, "dist_vwap_atr"].mean())
    print("  Short (esperado > +1.0):", signals.loc[signals["signal_vwap"]==-1, "dist_vwap_atr"].mean())

    print("\nCalidad de señal (0-4):")
    print(signals["signal_quality_vwap"].value_counts().sort_index())
else:
    print("Sin señales.")
