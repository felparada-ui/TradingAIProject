"""
Estrategia de Momentum — para mercados de ALTA VOLATILIDAD.

Usa MACD, ATR y rupturas de rango para capturar movimientos
explosivos en mercados volátiles.
"""

import numpy as np
import pandas as pd


def generate_entry_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Genera señales de entrada para mercado de alta volatilidad.

    Args:
        df: DataFrame con columnas open, high, low, close, volume
        config: Config de indicadores.alta_volatilidad

    Returns:
        dict con señal, confianza, SL y TP
    """
    cfg = config.get("indicadores", {}).get("alta_volatilidad", {})
    atr_period = cfg.get("atr_periodo", 14)
    atr_entry_mult = cfg.get("atr_mult_entry", 1.0)
    atr_sl_mult = cfg.get("atr_mult_sl", 1.5)
    macd_fast = cfg.get("macd_fast", 12)
    macd_slow = cfg.get("macd_slow", 26)
    macd_signal = cfg.get("macd_signal", 9)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    # MACD
    macd_line, signal_line = _macd(close, macd_fast, macd_slow, macd_signal)

    # ATR
    atr = _atr(high, low, close, atr_period)
    current_atr = atr[-1]
    last_price = close[-1]

    # Detectar breakout de rango intradía
    range_high = np.max(high[-20:])
    range_low = np.min(low[-20:])
    range_pct = (range_high - range_low) / range_low * 100 if range_low > 0 else 0

    # Señal BUY: MACD alcista + breakout al alza
    buy_signal = (
        macd_line[-1] > signal_line[-1]  # MACD sobre señal
        and macd_line[-2] <= signal_line[-2]  # Cruce reciente
        and last_price > range_high * 0.999  # Cerca del máximo del rango
        and range_pct > 2.0  # Rango significativo
    )

    # Señal SELL: MACD bajista + breakout a la baja
    sell_signal = (
        macd_line[-1] < signal_line[-1]
        and macd_line[-2] >= signal_line[-2]
        and last_price < range_low * 1.001
        and range_pct > 2.0
    )

    if buy_signal:
        sl = last_price - current_atr * atr_sl_mult
        tp = last_price + current_atr * atr_sl_mult * 2.5
        confidence = min(90, 50 + (macd_line[-1] - signal_line[-1]) * 100 + range_pct * 5)
        return {
            "signal": "BUY",
            "confidence": round(confidence, 1),
            "entry": round(last_price, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(current_atr, 5),
        }
    elif sell_signal:
        sl = last_price + current_atr * atr_sl_mult
        tp = last_price - current_atr * atr_sl_mult * 2.5
        confidence = min(90, 50 + (signal_line[-1] - macd_line[-1]) * 100 + range_pct * 5)
        return {
            "signal": "SELL",
            "confidence": round(confidence, 1),
            "entry": round(last_price, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(current_atr, 5),
        }

    return {"signal": "NEUTRAL", "confidence": 0, "entry": round(last_price, 5)}


def _macd(values: np.ndarray, fast: int, slow: int, signal: int):
    """MACD Line, Signal Line."""
    ema_fast = _ema(values, fast)
    ema_slow = _ema(values, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    return macd_line, signal_line


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    result = np.zeros_like(values)
    result[:period] = np.mean(values[:period])
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])),
    )
    atr = np.zeros_like(close)
    atr[0] = tr[0]
    for i in range(1, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    atr[-1] = atr[-2] if len(atr) > 1 else atr[0]
    return atr
