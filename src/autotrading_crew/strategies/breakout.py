"""
Estrategia de Breakout — para mercados en TENDENCIA.

Usa EMAs (9, 21, 55) + ADX para detectar rupturas de tendencia
y entrar en la dirección de la tendencia principal.
"""

import numpy as np
import pandas as pd


def generate_entry_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Genera señales de entrada para mercado en tendencia.

    Args:
        df: DataFrame con columnas open, high, low, close, volume
        config: Config de indicadores.tendencia

    Returns:
        dict con señal, confianza, SL y TP
    """
    cfg = config.get("indicadores", {}).get("tendencia", {})
    ema_fast = cfg.get("ema_rapida", 9)
    ema_mid = cfg.get("ema_media", 21)
    ema_slow = cfg.get("ema_lenta", 55)
    adx_period = cfg.get("adx_periodo", 22)
    adx_threshold = cfg.get("adx_umbral", 25)
    rsi_period = cfg.get("rsi_periodo", 14)
    rsi_ob = cfg.get("rsi_sobrecompra", 70)
    rsi_os = cfg.get("rsi_sobreventa", 30)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    # EMAs
    ema_9 = _ema(close, ema_fast)
    ema_21 = _ema(close, ema_mid)
    ema_55 = _ema(close, ema_slow)

    # RSI
    rsi = _rsi(close, rsi_period)

    # Condiciones de entrada
    last_price = close[-1]
    buy_signal = (
        ema_9[-1] > ema_21[-1] > ema_55[-1]  # Tendencia alcista
        and ema_9[-2] <= ema_21[-2]           # Cruce reciente
        and rsi[-1] > 50                      # Momento positivo
        and rsi[-1] < rsi_ob                  # No sobrecompra
    )
    sell_signal = (
        ema_9[-1] < ema_21[-1] < ema_55[-1]  # Tendencia bajista
        and ema_9[-2] >= ema_21[-2]           # Cruce reciente
        and rsi[-1] < 50                      # Momento negativo
        and rsi[-1] > rsi_os                  # No sobreventa
    )

    atr = _atr(high, low, close, 14)
    current_atr = atr[-1]

    if buy_signal:
        sl = last_price - current_atr * 1.5
        tp = last_price + current_atr * 3.0
        confidence = min(85, 50 + (ema_9[-1] - ema_21[-1]) / ema_21[-1] * 500)
        return {
            "signal": "BUY",
            "confidence": round(confidence, 1),
            "entry": round(last_price, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(current_atr, 5),
        }
    elif sell_signal:
        sl = last_price + current_atr * 1.5
        tp = last_price - current_atr * 3.0
        confidence = min(85, 50 + (ema_21[-1] - ema_9[-1]) / ema_21[-1] * 500)
        return {
            "signal": "SELL",
            "confidence": round(confidence, 1),
            "entry": round(last_price, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(current_atr, 5),
        }

    return {"signal": "NEUTRAL", "confidence": 0, "entry": round(last_price, 5)}


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    result = np.zeros_like(values)
    result[:period] = np.mean(values[:period])
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def _rsi(values: np.ndarray, period: int) -> np.ndarray:
    """Relative Strength Index."""
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.convolve(gains, np.ones(period) / period, mode="valid")
    avg_loss = np.convolve(losses, np.ones(period) / period, mode="valid")
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    # Padding
    pad = np.full(len(values) - len(rsi), 50.0)
    return np.concatenate([pad, rsi])


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Average True Range."""
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ),
    )
    atr = np.zeros_like(close)
    atr[0] = tr[0]
    for i in range(1, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    atr[-1] = atr[-2] if len(atr) > 1 else atr[0]
    return atr
