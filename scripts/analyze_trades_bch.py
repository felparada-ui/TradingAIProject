#!/usr/bin/env python3
"""Analisis detallado de trades baseline BCH H1."""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")
import pandas as pd
import numpy as np

trades = pd.read_csv("trades_backtest_generic.csv")
print(f"Trades: {len(trades)}")
print(f"Columns: {trades.columns.tolist()}")
print(trades.head())
print("\n=== Duracion barras ===")
print(trades["duration_bars"].describe())
print("\n=== PnL por lado ===")
print(trades.groupby("side")["pnl_usd"].describe())
print("\n=== PnL por regimen ===")
print(trades.groupby("regime")["pnl_usd"].agg(["count","sum","mean"]))
print("\n=== Top 10 peores trades ===")
print(trades.nsmallest(10, "pnl_usd")[["entry_time","side","pnl_usd","duration_bars"]])
print("\n=== Top 10 mejores trades ===")
print(trades.nlargest(10, "pnl_usd")[["entry_time","side","pnl_usd","duration_bars"]])
print("\n=== Salidas ===")
print(trades["reason"].value_counts())
