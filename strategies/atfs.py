"""
Adaptive Trend-Following System (ATFS) — BCH/USDT
Rediseño estructural de la estrategia de trading.
Timeframe: H1
Lógica:
  1. Filtro macro H4: EMA 50 > EMA 200 => solo longs; EMA 50 < EMA 200 => solo shorts
  2. Entrada H1: precio > EMA 20 + ADX > 20 + cruce EMA 9/21 + volumen > 0.7*SMA20
  3. Salida: Trailing stop dinámico SIN TP fijo (1.0*ATR), activo después de 1.5*ATR de ganancia
  4. Time stop: 12 velas H1
  5. Filtro RSI: no entrar en sobrecompra/sobreventa extrema
"""
import pandas as pd
import numpy as np
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals as generate_ema_signals


def generate_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    out = df.copy()

    out = add_all_indicators(out, cfg)
    out = generate_ema_signals(out, cfg)

    # --- Filtro macro H4 ---
    h4 = out.set_index("timestamp").resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna().reset_index()
    h4 = add_all_indicators(h4, cfg)
    h4["h4_bullish"] = h4["ema_fast"] > h4["ema_slow"]
    h4["h4_bearish"] = h4["ema_fast"] < h4["ema_slow"]
    h4["ts_4h"] = h4["timestamp"]

    # Mapear H4 -> H1
    out["ts_4h"] = pd.to_datetime(out["timestamp"]).dt.floor("4h")
    out = out.merge(h4[["ts_4h", "h4_bullish", "h4_bearish"]], on="ts_4h", how="left")

    # --- Indicadores adicionales ---
    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["volume_sma20"] = out["volume"].rolling(20).mean()
    out["volume_ok"] = out["volume"] > 0.7 * out["volume_sma20"].replace(0, np.nan)

    # RSI extremo filter
    delta = out["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = 100 - 100 / (1 + rs)

    # --- Señal ATFS ---
    long_cond = (
        out["h4_bullish"].fillna(False) &
        (out["close"] > out["ema20"]) &
        (out["adx"] > cfg.adx_threshold) &
        (out["signal"] == 1) &
        out["volume_ok"] &
        (out["rsi"] < 75)
    )

    short_cond = (
        out["h4_bearish"].fillna(False) &
        (out["close"] < out["ema20"]) &
        (out["adx"] > cfg.adx_threshold) &
        (out["signal"] == -1) &
        out["volume_ok"] &
        (out["rsi"] > 25)
    )

    out["signal_atfs"] = 0
    out.loc[long_cond, "signal_atfs"] = 1
    out.loc[short_cond, "signal_atfs"] = -1

    # Calidad
    out["signal_quality_atfs"] = 0
    for mask in [long_cond, short_cond]:
        if mask.sum() == 0:
            continue
        q = (
            (out.loc[mask, "adx"] > 25).astype(int) +
            (out.loc[mask, "volume"] > 1.2 * out.loc[mask, "volume_sma20"]).astype(int) +
            out.loc[mask, "volume_ok"].astype(int)
        )
        out.loc[mask, "signal_quality_atfs"] = q.astype(int)

    return out
