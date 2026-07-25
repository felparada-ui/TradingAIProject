#!/usr/bin/env python3
"""
Análisis de por qué la estrategia falla en BCH H1.
1. Distribución de régimen en el dataset.
2. Subperiodos de tendencia clara.
3. Impacto de costos de transacción.
4. Análisis de distribución de PnL.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
import numpy as np
from datetime import datetime

from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
CAPITAL = 200.0

# 1. Distribución de régimen
print("=" * 60)
print("ANÁLISIS DE DIAGNÓSTICO — BCH/USDT H1")
print("=" * 60)

df = load_from_csv(CSV)
data = add_all_indicators(df, STRATEGY)
data = generate_signals(data, STRATEGY)

print(f"\nTotal velas: {len(data)}")
print("Distribución de régimen:")
print(data["regime"].value_counts(normalize=True) * 100)

print("\nDistribución de señales por régimen:")
print(data[data["signal"] != 0]["regime"].value_counts())

signals = data[data["signal"] != 0]
print(f"\nTotal señales: {len(signals)}")
print(f"En sesión: {signals['in_session'].sum()}")

# 2. Análisis de calidad de señal
print("\nCalidad de señal (0-5):")
print(signals["signal_quality"].value_counts().sort_index())

# 3. Duración teórica de los trades
print("\nDistancia SL/TP en ATRs:")
if len(signals) > 0:
    signals_copy = signals.copy()
    signals_copy["sl_dist_atr"] = (signals_copy["close"] - signals_copy["ema_trend"]).abs() / signals_copy["atr"]
    print(signals_copy["sl_dist_atr"].describe())

# 4. Probar con costos de transacción
print("\n" + "=" * 60)
print("ANÁLISIS CON COSTOS DE TRANSACCIÓN")
print("=" * 60)

slippage_bps = 0.1  # 0.1% slippage
commission_bps = 0.05  # 0.05% comisión

# Simular costos en el backtest
# Para simplificar, calcularPnL neto = gross PnL - costos
trades_df = pd.read_csv("/workspaces/TradingAIProject/trades_backtest_generic.csv")
if not trades_df.empty:
    trades_df["cost_entry"] = trades_df["entry_price"] * (slippage_bps / 10000) + trades_df["entry_price"] * trades_df["size"] * (commission_bps / 10000)
    trades_df["cost_exit"] = trades_df["exit_price"] * (slippage_bps / 10000) + trades_df["exit_price"] * trades_df["size"] * (commission_bps / 10000)
    trades_df["pnl_net"] = trades_df["pnl_usd"] - trades_df["cost_entry"] - trades_df["cost_exit"]
    
    print(f"\nCostos por trade: slippage {slippage_bps}% + comisión {commission_bps}%")
    print(f"PnL bruto total: ${trades_df['pnl_usd'].sum():.2f}")
    print(f"Costo total: ${trades_df['cost_entry'].sum() + trades_df['cost_exit'].sum():.2f}")
    print(f"PnL neto total: ${trades_df['pnl_net'].sum():.2f}")
    print(f"Trades que cambian de ganancia a pérdida con costos: {((trades_df['pnl_usd'] > 0) & (trades_df['pnl_net'] <= 0)).sum()}")
else:
    print("No hay trades en el baseline.")

# 5. Análisis por subperiodos (bull/bear/rango)
print("\n" + "=" * 60)
print("ANÁLISIS POR SUBPERIODO")
print("=" * 60)

data["year"] = data["timestamp"].dt.year
data["month"] = data["timestamp"].dt.month

for year in sorted(data["year"].unique()):
    year_data = data[data["year"] == year]
    signals_year = year_data[year_data["signal"] != 0]
    print(f"\n{year}: {len(year_data)} velas, {len(signals_year)} señales")
    
    # Simular backtest rápido del año
    if len(signals_year) == 0:
        continue
    
    rm = RiskManager(STRATEGY, CAPITAL)
    for i, row in signals_year.iterrows():
        side = 1 if row["signal"] == 1 else -1
        atr_val = row["atr"]
        sl = row["close"] - atr_val * 1.5 if side == 1 else row["close"] + atr_val * 1.5
        tp = row["close"] + atr_val * 2.5 if side == 1 else row["close"] - atr_val * 2.5
        # Valor aproximado del PnL
        if side == 1:
            pnl = (tp - row["close"]) if tp <= year_data.loc[i+1, "high"] else (sl - row["close"]) if sl >= year_data.loc[i+1, "low"] else 0
        else:
            pnl = (row["close"] - tp) if tp >= year_data.loc[i+1, "low"] else (row["close"] - sl) if sl <= year_data.loc[i+1, "high"] else 0
        # Esto es muy simplificado, solo para diagnóstico

print("\n" + "=" * 60)
print("CONCLUSIÓN DIAGNÓSTICO")
print("=" * 60)
print("1. La distribución de régimen muestra si el mercado pasó suficiente tiempo en tendencia.")
print("2. Los costos de transacción empeoran aún más un PF ya negativo.")
print("3. Si las señales son escasas y de baja calidad, la optimización de parámetros no alcanza.")
print("Se recomienda considerar cambio de estrategia o activo/timeframe.")
