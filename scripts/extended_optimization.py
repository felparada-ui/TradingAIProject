#!/usr/bin/env python3
"""
Optimización ampliada para M5 y M15.
Evalúa más combinaciones de parámetros.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import itertools
import pandas as pd
from config import STRATEGY
from scripts.iterative_optimization import run_backtest_iteration

CSV_M5 = "/workspaces/TradingAIProject/data/bch_usdt_m5.csv"
CSV_M15 = "/workspaces/TradingAIProject/data/bch_usdt_m15.csv"
CAPITAL = 200.0
OUT = "/workspaces/TradingAIProject/iteration_history_extended.csv"

configs = []

# M5 amplio
for adx in [18, 20, 22, 25]:
    for sl in [1.0, 1.5, 2.0]:
        for tp in [1.5, 2.0, 2.5, 3.0]:
            for ts in [8, 16, 24, None]:
                configs.append({
                    "csv": CSV_M5, "tf": "M5", "adx": adx, "sl": sl, "tp": tp, "ts": ts,
                    "session": list(range(0, 24)), "vwap": False, "don": False, "h4": False
                })

# M15 amplio
for adx in [18, 20, 22, 25]:
    for sl in [1.0, 1.5, 2.0]:
        for tp in [1.5, 2.0, 2.5, 3.0]:
            for ts in [4, 8, 12, None]:
                configs.append({
                    "csv": CSV_M15, "tf": "M15", "adx": adx, "sl": sl, "tp": tp, "ts": ts,
                    "session": list(range(8, 21)), "vwap": False, "don": False, "h4": False
                })

print(f"Total configuraciones a evaluar: {len(configs)}")
results = []
for i, cfg in enumerate(configs, 1):
    m = run_backtest_iteration(
        csv_path=cfg["csv"], initial_capital=CAPITAL,
        session_hours_utc=cfg["session"], adx_threshold=cfg["adx"],
        atr_sl_mult=cfg["sl"], atr_tp_mult=cfg["tp"], time_stop_bars=cfg["ts"],
        use_vwap=cfg["vwap"], use_donchian=cfg["don"], trend_filter_h4=cfg["h4"],
    )
    m["iteration"] = i
    m["timeframe"] = cfg["tf"]
    m["config"] = f"{cfg['tf']}_ADX{cfg['adx']}_SL{cfg['sl']}_TP{cfg['tp']}_TS{cfg['ts']}"
    results.append(m)
    if i % 20 == 0 or i == len(configs):
        print(f"  {i}/{len(configs)} completados")

results_df = pd.DataFrame(results)
results_df.to_csv(OUT, index=False)
print(f"\nResultados guardados en {OUT}")

# Filtrar viables
viable = results_df[
    (results_df["profit_factor"] > 1.0) &
    (results_df["total_return_pct"] > 0) &
    (results_df["max_drawdown_pct"] > -15.0) &
    (results_df["total_trades"] >= 5)
].copy()

if not viable.empty:
    viable["score"] = viable["profit_factor"] + (viable["total_return_pct"] / 100.0) - (abs(viable["max_drawdown_pct"]) / 100.0)
    best = viable.sort_values("score", ascending=False).iloc[0]
    print("\n" + "=" * 60)
    print("  CONFIGURACIÓN RENTABLE ENCONTRADA")
    print("=" * 60)
    print(f"Iteración : {best['iteration']}")
    print(f"Timeframe : {best.get('timeframe', 'N/A')}")
    print(f"Config    : {best.get('config', 'N/A')}")
    print(f"Trades    : {best.get('total_trades', 0)}")
    print(f"Win Rate  : {best.get('win_rate_pct', 0):.2f}%")
    print(f"PF        : {best.get('profit_factor', 0):.2f}")
    print(f"Retorno   : {best.get('total_return_pct', 0):.2f}%")
    print(f"Max DD    : {best.get('max_drawdown_pct', 0):.2f}%")
    print(f"Sharpe    : {best.get('sharpe_approx', 0):.2f}")
else:
    print("\n" + "=" * 60)
    print("  NINGUNA CONFIGURACIÓN RENTABLE EN M5/M15")
    print("=" * 60)
    best_h1 = results_df[results_df["timeframe"] == "H1"].sort_values("profit_factor", ascending=False).iloc[0]
    print("Mejor configuración global:")
    print(best_h1[["iteration", "timeframe", "config", "total_trades", "win_rate_pct", "profit_factor", "total_return_pct", "max_drawdown_pct"]])
