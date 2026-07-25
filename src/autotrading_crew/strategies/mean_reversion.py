"""
Estrategia de Reversión a la Media — para mercados en RANGO.

Usa Bollinger Bands + RSI + Estocástico para detectar
sobrecompra/sobreventa en mercados laterales.
"""

import numpy as np
import pandas as pd


def generate_entry_signal(df: pd.DataFrame, config: dict) -> dict:
    """
    Genera señales de entrada para mercado en rango (reversión a la media).

    Args:
        df: DataFrame con columnas open, high, low, close, volume
        config: Config de indicadores.rango

    Returns:
        dict con señal, confianza, SL y TP
    """
    cfg = config.get("indicadores", {}).get("rango", {})
    bb_period = cfg.get("bb_periodo", 20)
    bb_std = cfg.get("bb_desviacion", 2.0)
    rsi_period = cfg.get("rsi_periodo", 14)
    rsi_lower = cfg.get("rsi_limite_inferior", 30)
    rsi_upper = cfg.get("rsi_limite_superior", 70)
    stoch_k = cfg.get("stochastic_k", 14)
    stoch_d = cfg.get("stochastic_d", 3)

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    # Bollinger Bands
    sma = np.convolve(close, np.ones(bb_period) / bb_period, mode="valid")
    rolling_std = np.array([np.std(close[i - bb_period:i]) for i in range(bb_period, len(close) + 1)])
    upper_band = sma + bb_std * rolling_std
    lower_band = sma - bb_std * rolling_std

    # RSI
    rsi = _rsi(close, rsi_period)

    # Estocástico
    stoch = _stochastic(high, low, close, stoch_k, stoch_d)

    last_price = close[-1]
    last_sma = sma[-1]
    last_upper = upper_band[-1]
    last_lower = lower_band[-1]
    last_rsi = rsi[-1]
    last_stoch_k = stoch["k"][-1]
    last_stoch_d = stoch["d"][-1]

    # Señal de COMPRA (sobreventa) — condiciones relajadas
    buy_signal = (
        last_price <= last_lower  # Precio en banda inferior
        and last_rsi < rsi_lower + 5  # RSI cerca de sobreventa (< 35)
        and last_stoch_k < 25         # Estocástico cerca de sobreventa
    )

    # Señal de VENTA (sobrecompra) — condiciones relajadas
    sell_signal = (
        last_price >= last_upper  # Precio en banda superior
        and last_rsi > rsi_upper - 5  # RSI cerca de sobrecompra (> 65)
        and last_stoch_k > 75         # Estocástico cerca de sobrecompra
    )

    atr = _atr(high, low, close, 14)
    current_atr = atr[-1]

    if buy_signal:
        sl = last_price - current_atr * 1.5
        # TP basado en ATR con RR mínimo > 1.8
        tp_atr = last_price + current_atr * 3.0
        tp_bb = last_sma + (last_sma - last_lower)  # SMA + 2*std (BB recovery)
        tp = max(tp_atr, min(tp_bb, last_price + current_atr * 4.0))
        confidence = min(80, 40 + (rsi_lower - last_rsi) * 3 + (last_lower - last_price) / current_atr * 10)
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
        tp_atr = last_price - current_atr * 3.0
        tp_bb = last_sma - (last_upper - last_sma)  # SMA - 2*std (BB mean reversion)
        tp = min(tp_atr, max(tp_bb, last_price - current_atr * 4.0))
        confidence = min(80, 40 + (last_rsi - rsi_upper) * 3 + (last_price - last_upper) / current_atr * 10)
        return {
            "signal": "SELL",
            "confidence": round(confidence, 1),
            "entry": round(last_price, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "atr": round(current_atr, 5),
        }

    return {"signal": "NEUTRAL", "confidence": 0, "entry": round(last_price, 5)}


def _rsi(values: np.ndarray, period: int) -> np.ndarray:
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.convolve(gains, np.ones(period) / period, mode="valid")
    avg_loss = np.convolve(losses, np.ones(period) / period, mode="valid")
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    pad = np.full(len(values) - len(rsi), 50.0)
    return np.concatenate([pad, rsi])


def _stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k_period: int, d_period: int) -> dict:
    """Estocástico %K y %D."""
    lowest_low = np.array([np.min(low[i - k_period + 1:i + 1]) for i in range(k_period - 1, len(low))])
    highest_high = np.array([np.max(high[i - k_period + 1:i + 1]) for i in range(k_period - 1, len(high))])
    close_slice = close[k_period - 1:]

    k = 100 * (close_slice - lowest_low) / (highest_high - lowest_low + 1e-10)
    d = np.convolve(k, np.ones(d_period) / d_period, mode="valid")

    # Padding
    pad_k = np.full(len(close) - len(k), 50.0)
    pad_d = np.full(len(close) - len(d), 50.0)
    return {
        "k": np.concatenate([pad_k, k]),
        "d": np.concatenate([pad_d, d]),
    }


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
