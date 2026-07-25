"""
Detector de Regímenes de Mercado (Regime Switching)

Identifica si el mercado está en:
  - TENDENCIA (direccional) → Estrategia de Breakout
  - RANGO (lateral)        → Estrategia de Reversión a la Media
  - ALTA VOLATILIDAD        → Estrategia de Momentum

Usa ADX, Bollinger Bands Width, ATR y Ratio de Eficiencia.
"""

import numpy as np
import pandas as pd
from enum import Enum


class MarketRegime(Enum):
    TREND = "tendencia"
    RANGE = "rango"
    HIGH_VOLATILITY = "alta_volatilidad"
    UNDEFINED = "indefinido"


class RegimeDetector:
    """Detecta el régimen actual del mercado usando múltiples métricas."""

    def __init__(self, config: dict):
        cfg = config.get("regimen", {})
        self.adx_period = cfg.get("ventana_adx", 22)
        self.trend_adx_threshold = cfg.get("umbral_tendencia_adx", 25)
        self.bb_period = cfg.get("ventana_bb", 20)
        self.bb_std = cfg.get("desviacion_bb", 2.0)
        self.range_bb_threshold = cfg.get("umbral_rango_bb", 0.15)
        self.atr_period = cfg.get("ventana_atr", 14)
        self.high_vol_atr_mult = cfg.get("umbral_alta_volatilidad", 1.5)
        self.efficiency_period = cfg.get("ventana_eficiencia", 50)

    def detect(self, df: pd.DataFrame) -> dict:
        """
        Detecta el régimen actual devolviendo un dict con:
          - regime: MarketRegime
          - confidence: float (0-100)
          - metrics: dict con valores de apoyo
        """
        if df is None or len(df) < max(self.adx_period, self.bb_period, self.atr_period) + 5:
            return {"regime": MarketRegime.UNDEFINED, "confidence": 0, "metrics": {}}

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        # --- ADX (Fuerza de Tendencia) ---
        adx = self._compute_adx(high, low, close, self.adx_period)
        current_adx = adx[-1] if len(adx) > 0 else 0

        # --- Bollinger Bands Width (Ancho relativo) ---
        bb_width = self._compute_bb_width(close, self.bb_period, self.bb_std)
        current_bbw = bb_width[-1] if len(bb_width) > 0 else 0

        # --- ATR (Volatilidad) ---
        atr = self._compute_atr(high, low, close, self.atr_period)
        atr_mean = np.mean(atr[-self.atr_period * 2:]) if len(atr) > self.atr_period * 2 else np.mean(atr)
        current_atr = atr[-1] if len(atr) > 0 else 0
        atr_ratio = current_atr / atr_mean if atr_mean > 0 else 1.0

        # --- Ratio de Eficiencia (Kaufman) ---
        efficiency_ratio = self._compute_efficiency_ratio(close, self.efficiency_period)
        current_er = efficiency_ratio[-1] if len(efficiency_ratio) > 0 else 0

        # --- Lógica de decisión ---
        metrics = {
            "adx": round(current_adx, 2),
            "bb_width_pct": round(current_bbw * 100, 2),
            "atr_ratio": round(atr_ratio, 2),
            "efficiency_ratio": round(current_er, 4),
        }

        # Alta volatilidad tiene prioridad
        if atr_ratio >= self.high_vol_atr_mult:
            regime = MarketRegime.HIGH_VOLATILITY
            confidence = min(100, atr_ratio * 40)
        elif current_adx >= self.trend_adx_threshold and current_er > 0.3:
            regime = MarketRegime.TREND
            confidence = min(100, current_adx * 2.5 + current_er * 50)
        elif current_bbw <= self.range_bb_threshold and current_er < 0.25:
            regime = MarketRegime.RANGE
            confidence = min(100, (1 - current_bbw / self.range_bb_threshold) * 60 + (1 - current_er) * 40)
        elif current_adx >= self.trend_adx_threshold:
            regime = MarketRegime.TREND
            confidence = min(100, current_adx * 2)
        else:
            regime = MarketRegime.RANGE
            confidence = min(100, (1 - current_bbw) * 50)

        return {
            "regime": regime,
            "regime_name": regime.value,
            "confidence": round(confidence, 1),
            "metrics": metrics,
        }

    def get_strategy_for_regime(self, regime: MarketRegime) -> str:
        """Retorna la estrategia recomendada según el régimen."""
        mapping = {
            MarketRegime.TREND: "breakout",
            MarketRegime.RANGE: "mean_reversion",
            MarketRegime.HIGH_VOLATILITY: "momentum",
            MarketRegime.UNDEFINED: "breakout",
        }
        return mapping.get(regime, "breakout")

    # ------------------------------------------------------------------
    # Métodos auxiliares (vectorizados con NumPy)
    # ------------------------------------------------------------------

    def _compute_adx(self, high, low, close, period: int):
        """ADX simplificado — smoothed directional movement."""
        if len(close) < period + 1:
            return np.array([0.0])

        plus_dm = np.diff(high)
        minus_dm = np.diff(low)
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        # Wilder smoothing
        atr = self._wilder_smooth(tr, period)
        plus_di = 100 * self._wilder_smooth(plus_dm, period) / atr
        minus_di = 100 * self._wilder_smooth(minus_dm, period) / atr
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = self._wilder_smooth(dx, period)
        return adx

    def _compute_bb_width(self, close, period: int, std_mult: float):
        """Ancho relativo de Bollinger Bands: (upper - lower) / middle."""
        if len(close) < period:
            return np.array([0.0])
        sma = np.convolve(close, np.ones(period) / period, mode="valid")
        rolling_std = np.array([np.std(close[i - period:i]) for i in range(period, len(close) + 1)])
        upper = sma + std_mult * rolling_std
        lower = sma - std_mult * rolling_std
        width = (upper - lower) / sma
        return width

    def _compute_atr(self, high, low, close, period: int):
        """Average True Range."""
        if len(close) < 2:
            return np.array([0.0])
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        return self._wilder_smooth(tr, period)

    def _compute_efficiency_ratio(self, close, period: int):
        """Kaufman Efficiency Ratio: direction / volatility."""
        if len(close) < period + 1:
            return np.array([0.0])
        direction = np.abs(np.diff(close, period))
        volatility = np.array([
            np.sum(np.abs(np.diff(close[i - period:i + 1])))
            for i in range(period, len(close))
        ])
        er = direction / (volatility + 1e-10)
        return er

    @staticmethod
    def _wilder_smooth(values, period: int):
        """Wilder's exponential smoothing (used in ADX/ATR)."""
        smoothed = np.zeros_like(values)
        smoothed[0] = values[0]
        for i in range(1, len(values)):
            smoothed[i] = (smoothed[i - 1] * (period - 1) + values[i]) / period
        return smoothed
