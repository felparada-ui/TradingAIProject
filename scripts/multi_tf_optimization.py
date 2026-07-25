#!/usr/bin/env python3
"""
Optimización multi-timeframe para BCH/USDT.
Ejecuta backtest en M5, M15 y H1 y guarda resultados comparativos.
"""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

from datetime import datetime
from config import STRATEGY
from scripts.iterative_optimization import run_backtest_iteration

CSV_M5 = "/workspaces/TradingAIProject/data/bch_usdt_m5.csv"
CSV_M15 = "/workspaces/TradingAIProject/data/bch_usdt_m15.csv"
CSV_H1 = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
CAPITAL = 200.0
OUT = "/workspaces/TradingAIProject/iteration_history_multi_tf.csv"

configs = [
    {"csv": CSV_H1, "tf": "H1", "session_hours_utc": list(range(8, 21)), "adx_threshold": 20.0, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "time_stop_bars": 8, "use_vwap": False, "use_donchian": False, "trend_filter_h4": False},
    {"csv": CSV_M5, "tf": "M5", "session_hours_utc": list(range(0, 24)), "adx_threshold": 20.0, "atr_sl_mult": 1.0, "atr_tp_mult": 2.0, "time_stop_bars": 16, "use_vwap": False, "use_donchian": False, "trend_filter_h4": False},
    {"csv": CSV_M5, "tf": "M5", "session_hours_utc": list(range(0, 24)), "adx_threshold": 25.0, "atr_sl_mult": 1.0, "atr_tp_mult": 2.5, "time_stop_bars": 16, "use_vwap": False, "use_donchian": False, "trend_filter_h4": True},
    {"csv": CSV_M15, "tf": "M15", "session_hours_utc": list(range(0, 24)), "adx_threshold": 20.0, "atr_sl_mult": 1.0, "atr_tp_mult": 2.0, "time_stop_bars": 8, "use_vwap": False, "use_donchian": False, "trend_filter_h4": False},
    {"csv": CSV_M15, "tf": "M15", "session_hours_utc": list(range(8, 21)), "adx_threshold": 22.0, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5, "time_stop_bars": 8, "use_vwap": False, "use_donchian": False, "trend_filter_h4": True},
    {"csv": CSV_M5, "tf": "M5", "session_hours_utc": list(range(8, 21)), "adx_threshold": 25.0, "atr_sl_mult": 1.0, "atr_tp_mult": 2.5, "time_stop_bars": 16, "use_vwap": True, "use_donchian": False, "trend_filter_h4": False},
    {"csv": CSV_M15, "tf": "M15", "session_hours_utc": list(range(8, 21)), "adx_threshold": 25.0, "atr_sl_mult": 1.5, "atr_tp_mult": 3.0, "time_stop_bars": 8, "use_vwap": False, "use_donchian": True, "trend_filter_h4": False},
]

results = []
for i, cfg in enumerate(configs, 1):
    print(f"\nIteración {i}: {cfg['tf']} | ADX{cfg['adx_threshold']} | SL{cfg['atr_sl_mult']} | TP{cfg['atr_tp_mult']} | TS{cfg['time_stop_bars']} | VWAP:{cfg['use_vwap']} | DON:{cfg['use_donchian']} | H4:{cfg['trend_filter_h4']}")
    m = run_backtest_iteration(
        csv_path=cfg["csv"],
        initial_capital=CAPITAL,
        session_hours_utc=cfg["session_hours_utc"],
        adx_threshold=cfg["adx_threshold"],
        atr_sl_mult=cfg["atr_sl_mult"],
        atr_tp_mult=cfg["atr_tp_mult"],
        time_stop_bars=cfg["time_stop_bars"],
        use_vwap=cfg["use_vwap"],
        use_donchian=cfg["use_donchian"],
        trend_filter_h4=cfg["trend_filter_h4"],
    )
    m["iteration"] = i
    m["timeframe"] = cfg["tf"]
    m["config"] = f"{cfg['tf']}_ADX{cfg['adx_threshold']}_SL{cfg['atr_sl_mult']}_TP{cfg['atr_tp_mult']}_TS{cfg['time_stop_bars']}"
    results.append(m)
    print(f"  -> Trades: {m.get('total_trades',0)} | PF: {m.get('profit_factor',0)} | Ret: {m.get('total_return_pct',0)}% | DD: {m.get('max_drawdown_pct',0)}%")

import pandas as pd
results_df = pd.DataFrame(results)
results_df.to_csv(OUT, index=False)
print(f"\nResultados guardados en {OUT}")
print("\nResumen comparativo:")
print(results_df[["iteration", "timeframe", "total_trades", "win_rate_pct", "profit_factor", "total_return_pct", "max_drawdown_pct", "sharpe_approx"]].to_string(index=False))

# Seleccionar la mejor configuración
best = results_df.sort_values(by=["profit_factor", "total_return_pct"], ascending=False).iloc[0]
print("\n" + "=" * 60)
print("  CONFIGURACIÓN ÓPTIMA POR SCORE")
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
