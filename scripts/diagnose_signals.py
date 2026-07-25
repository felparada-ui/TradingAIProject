#!/usr/bin/env python3
"""Diagnóstico rápido de señales generadas sobre el dataset descargado."""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
import numpy as np
from datetime import timezone
from config import STRATEGY
from indicators import add_all_indicators, detect_regime
from strategies.ema_trend_scalping import generate_signals

df = pd.read_csv("/workspaces/TradingAIProject/data/btc_usdt_m5.csv")
print(f"CSV filas: {len(df)}")

# Parsear timestamp manejando posible timezone
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp").reset_index(drop=True)

data = generate_signals(df, STRATEGY)
data = data.dropna(subset=["ema_fast","ema_slow","ema_trend","adx","atr"]).reset_index(drop=True)
print(f"Filas tras dropna: {len(data)}")

signals = data[data["signal"] != 0].copy()
print(f"Señales totales: {len(signals)}")
print(f"Señales long: {(signals['signal']==1).sum()}")
print(f"Señales short: {(signals['signal']==-1).sum()}")

# Conteo por hora UTC
if not signals.empty:
    signals["hour_utc"] = signals["timestamp"].dt.hour
    print("\nSeñales por hora UTC (top 10):")
    print(signals["hour_utc"].value_counts().sort_index().head(20))

    signals["date"] = signals["timestamp"].dt.date
    print(f"\nDias con al menos 1 señal: {signals['date'].nunique()}")
    print("Señales por día (top 10):")
    print(signals["date"].value_counts().sort_values(ascending=False).head(10))

    print("\nDistribucion de régimen en señales:")
    print(signals["regime"].value_counts())

    print("\nDistribucion de calidad de señal (0-5):")
    print(signals["signal_quality"].value_counts().sort_index())
else:
    print("No se generaron señales.")
