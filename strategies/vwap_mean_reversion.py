"""
VWAP Mean Reversion Strategy — BTC/USDT M5
Régimen objetivo: RANGE (ADX < 22)
Timeframe: M5
Lógica:
  - VWAP intradía (desde 00:00 UTC) como centro de gravedad
  - Entrada long cuando precio cierra por debajo de VWAP - 1.0*ATR
  - Entrada short cuando precio cierra por encima de VWAP + 1.0*ATR
  - Confirmación adicional: RSI fuera de zona central y volumen > 70% de SMA20
  - Salida por TP (VWAP) o SL (ATR * 1.0) según casos extremos
"""

import pandas as pd
import numpy as np
from indicators import add_all_indicators


def generate_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Genera señales de VWAP Mean Reversion.

    Args:
        df: DataFrame OHLCV con columnas base.
        cfg: StrategyConfig.

    Returns:
        DataFrame con columnas:
          - signal_vwap: 1=long MR, -1=short MR, 0=san
          - regime_vwap: etiqueta simplificada para logging
          - signal_quality_vwap: score 0-4
    """
    out = df.copy()

    # --- Indicadores base (reusar lo que ya existe) ---
    if "adx" not in out.columns or "atr" not in out.columns or "rsi" not in out.columns:
        out = add_all_indicators(out, cfg)

    # --- VWAP intradía (reinicia cada día a las 00:00 UTC) ---
    days = pd.to_datetime(out["timestamp"]).dt.floor("D")
    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    cum_tp_vol = (typical * out["volume"]).groupby(days).cumsum()
    cum_vol = out["volume"].groupby(days).cumsum()
    out["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)

    # --- Bandas de VWAP para detectar desviaciones extremas ---
    band_mult = getattr(cfg, "vwap_band_mult", 0.6)
    out["vwap_lower"] = out["vwap"] - band_mult * out["atr"]
    out["vwap_upper"] = out["vwap"] + band_mult * out["atr"]

    # --- Volumen relativo (confirmación) ---
    out["volume_sma20"] = out["volume"].rolling(20).mean()
    out["volume_ok"] = out["volume"] > getattr(cfg, "vwap_min_volume_mult", 0.7) * out["volume_sma20"].replace(0, np.nan)

    # --- Filtros de régimen ---
    is_range = out["adx"] < getattr(cfg, "vwap_adx_max", 22.0)
    in_session = out.get("in_session", True)

    # --- Condiciones de entrada ---
    long_cond = (
        (out["close"] <= out["vwap_lower"]) &
        is_range &
        in_session &
        (out["rsi"] < getattr(cfg, "vwap_rsi_long_max", 45)) &
        out["volume_ok"]
    )

    short_cond = (
        (out["close"] >= out["vwap_upper"]) &
        is_range &
        in_session &
        (out["rsi"] > getattr(cfg, "vwap_rsi_short_min", 55)) &
        out["volume_ok"]
    )

    out["signal_vwap"] = 0
    out.loc[long_cond, "signal_vwap"] = 1
    out.loc[short_cond, "signal_vwap"] = -1

    # --- Regime y calidad para logging ---
    out["regime_vwap"] = "RANGE"
    out.loc[out["atr_pct"] > out["atr_pct"].quantile(0.80), "regime_vwap"] = "HIGH_VOL_IGNORE"

    quality = pd.Series(0, index=out.index, dtype=int)
    for mask in [long_cond, short_cond]:
        if mask.sum() == 0:
            continue
        score = (
            (out.loc[mask, "adx"] < 18).astype(int) +
            (out.loc[mask, "atr_pct"] > out["atr_pct"].median()).astype(int) +
            (out.loc[mask, "rsi"].between(30, 40) | out.loc[mask, "rsi"].between(60, 70)).astype(int) +
            out.loc[mask, "volume_ok"].astype(int)
        )
        out.loc[mask, "signal_quality_vwap"] = score.astype(int)

    return out
