#!/usr/bin/env python3
"""Grid search rápido de parámetros para BCH H1 baseline."""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import itertools
import pandas as pd
from datetime import datetime

from scripts.backtest_generic import run_backtest

CSV = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
CAPITAL = 200.0

grid = {
    "adx_threshold": [18, 20, 22, 25],
    "atr_sl_mult": [1.0, 1.5, 2.0],
    "atr_tp_mult": [1.5, 2.0, 2.5, 3.0],
    "time_stop_bars": [4, 8, 12, None],
    "session_hours_utc": [
        [8,9,10,11,12,13,14,15,16,17,18,19,20],  # todo el día
        [9,10,11,12,13,14,15,16,17,18,19],        # sin 08 y 20
        [10,11,12,13,14,15,16,17,18],              # 10-18
        [13,14,15,16,17],                          # 13-17 premium
    ],
}

rows = []
keys = list(grid.keys())
vals = list(grid.values())

print("Comenzando grid search...")
total = 1
for v in vals:
    total *= len(v)
print(f"Total combinaciones: {total}")

best_pf = -999
best_name = None
best_metrics = None

for i, combo in enumerate(itertools.product(*vals), 1):
    params = dict(zip(keys, combo))
    try:
        trades_df, equity_df, metrics = run_backtest(
            csv_path=CSV,
            initial_capital=CAPITAL,
            adx_threshold=params["adx_threshold"],
            atr_sl_mult=params["atr_sl_mult"],
            atr_tp_mult=params["atr_tp_mult"],
            time_stop_bars=params["time_stop_bars"],
            session_hours_utc=params["session_hours_utc"],
            max_daily_loss=0.03,
            risk_per_trade=0.01,
        )
    except Exception as e:
        print(f"Error en combo {i}: {e}")
        continue

    pf = metrics.get("profit_factor", 0)
    sr = metrics.get("sharpe_approx", 0)
    wr = metrics.get("win_rate_pct", 0)
    mdd = metrics.get("max_drawdown_pct", 0)
    ret = metrics.get("total_return_pct", 0)
    trades = metrics.get("total_trades", 0)
    name = f"ADX{params['adx_threshold']}_SL{params['atr_sl_mult']}_TP{params['atr_tp_mult']}_TS{params['time_stop_bars']}_SES{len(params['session_hours_utc'])}"

    row = {
        "name": name,
        "adx": params["adx_threshold"],
        "sl": params["atr_sl_mult"],
        "tp": params["atr_tp_mult"],
        "ts": params["time_stop_bars"],
        "ses_len": len(params["session_hours_utc"]),
        "trades": trades,
        "wr": wr,
        "pf": pf,
        "ret": ret,
        "mdd": mdd,
        "sharpe": sr,
    }
    rows.append(row)
    if pf > best_pf and trades >= 10:
        best_pf = pf
        best_name = name
        best_metrics = metrics

    if i % 20 == 0 or i == total:
        print(f"  {i}/{total} | mejor PF actual: {best_pf:.2f} ({best_name})")

results = pd.DataFrame(rows)
results.to_csv("grid_search_bch_h1.csv", index=False)
print(f"\nGrid search completado. Resultados guardados en grid_search_bch_h1.csv")
print(f"Mejor PF: {best_pf:.2f} -> {best_name}")
if best_metrics:
    print("Métricas del mejor escenario:")
    for k, v in best_metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.2f}")
        else:
            print(f"  {k}: {v}")
