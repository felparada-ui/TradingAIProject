"""
Diagnostico rapido: cuantas señales genera la estrategia
y por que el backtest tiene tan pocos trades.
"""
import pandas as pd
import sys
sys.path.insert(0, ".")

from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators

CSV = r"C:\Users\felpa\Downloads\BTCUSDm_M5_202201010000_202607221645.csv"

df = load_from_csv(CSV)
print(f"Velas cargadas: {len(df)}")
print(f"Columnas: {list(df.columns)}")
print(f"Muestra timestamp: {df['timestamp'].head(3).tolist()}")

out = add_all_indicators(df, STRATEGY)

print(f"\nVelas en sesion (in_session=True): {out['in_session'].sum():,} de {len(out):,}")
print(f"  Horas UTC en el dataset: {df['timestamp'].dt.hour.value_counts().sort_index().to_dict()}")
print(f"\nADX > 22: {(out['adx'] > 22).sum():,} velas")
print(f"ATR% > min: {(out['atr_pct'] > STRATEGY.min_atr_pct).sum():,} velas")

# Cruces de EMA sin filtro de sesion
cross_up   = (out["ema_fast"] > out["ema_slow"]) & (out["ema_fast"].shift(1) <= out["ema_slow"].shift(1))
cross_down = (out["ema_fast"] < out["ema_slow"]) & (out["ema_fast"].shift(1) >= out["ema_slow"].shift(1))
print(f"\nCruces EMA 9/21 al alza  : {cross_up.sum():,}")
print(f"Cruces EMA 9/21 a la baja: {cross_down.sum():,}")

bull_macro = out["close"] > out["ema_trend"]
bear_macro = out["close"] < out["ema_trend"]
trend_ok   = out["adx"] > STRATEGY.adx_threshold
vol_ok     = out["atr_pct"] > STRATEGY.min_atr_pct

long_raw  = cross_up  & bull_macro & trend_ok & vol_ok
short_raw = cross_down & bear_macro & trend_ok & vol_ok
print(f"\nSeñales LONG  sin filtro sesion: {long_raw.sum():,}")
print(f"Señales SHORT sin filtro sesion: {short_raw.sum():,}")

long_filtered  = long_raw  & out["in_session"]
short_filtered = short_raw & out["in_session"]
print(f"\nSeñales LONG  CON filtro sesion: {long_filtered.sum():,}")
print(f"Señales SHORT CON filtro sesion: {short_filtered.sum():,}")

print(f"\nConfig sesion: horas={STRATEGY.session_hours_utc}, dias={STRATEGY.trading_days}")

# Mostrar distribucion horaria de señales long sin filtro
print("\nDistribucion horaria señales LONG (sin filtro sesion):")
if long_raw.sum() > 0:
    hours = out.loc[long_raw, "timestamp"].dt.hour.value_counts().sort_index()
    for h, c in hours.items():
        print(f"  {h:02d}:00 UTC -> {c} señales")
