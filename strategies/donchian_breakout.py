"""
Donchian Breakout Strategy — BTC/USDT M5
Régimen objetivo: HIGH_VOL (ATR% > percentil 80, ADX > 25)
Timeframe: M5
Lógica:
  - Compra si cierre rompe máximo de 20 velas (Donchian Upper)
  - Vende si cierre rompe mínimo de 20 velas (Donchian Lower)
  - Confirmación: ADX > 25 + volumen > 1.0*SMA20 + distancia al canal > 0.5*ATR
  - SL: mínimo/máximo de la vela de entrada menos 0.5*ATR (breakout failure)
  - TP: ATR * 3.0 desde la entrada (RR 1:3 para capturar tendencias fuertes)
"""

import pandas as pd
import numpy as np
from indicators import add_all_indicators


def generate_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    out = df.copy()

    if "adx" not in out.columns or "atr" not in out.columns or "volume" not in out.columns:
        out = add_all_indicators(out, cfg)

    # --- Canal Donchian ---
    period = getattr(cfg, "donchian_period", 20)
    out["donchian_high"] = out["high"].rolling(period).max()
    out["donchian_low"] = out["low"].rolling(period).min()

    # --- Volumen confirmación ---
    out["volume_sma20"] = out["volume"].rolling(20).mean()
    out["volume_ok"] = out["volume"] > 1.0 * out["volume_sma20"].replace(0, np.nan)

    # --- Filtros de régimen (HIGH_VOL) ---
    is_high_vol = (out["adx"] > getattr(cfg, "donchian_adx_min", 25)) & (out["atr_pct"] > out["atr_pct"].quantile(0.80))
    in_session = out.get("in_session", True)

    # --- Condiciones de entrada ---
    long_cond = (
        (out["close"] > out["donchian_high"].shift(1)) &
        is_high_vol &
        in_session &
        out["volume_ok"] &
        ((out["close"] - out["donchian_low"]) > 0.5 * out["atr"])
    )

    short_cond = (
        (out["close"] < out["donchian_low"].shift(1)) &
        is_high_vol &
        in_session &
        out["volume_ok"] &
        ((out["donchian_high"] - out["close"]) > 0.5 * out["atr"])
    )

    out["signal_donchian"] = 0
    out.loc[long_cond, "signal_donchian"] = 1
    out.loc[short_cond, "signal_donchian"] = -1

    # --- Quality score ---
    out["signal_quality_donchian"] = 0
    for mask in [long_cond, short_cond]:
        if mask.sum() == 0:
            continue
        q = (
            (out.loc[mask, "adx"] > 30).astype(int) +
            (out.loc[mask, "volume"] > 1.5 * out.loc[mask, "volume_sma20"]).astype(int) +
            (out.loc[mask, "body_ratio"] > 0.6).astype(int)
        )
        out.loc[mask, "signal_quality_donchian"] = q.astype(int)

    return out
