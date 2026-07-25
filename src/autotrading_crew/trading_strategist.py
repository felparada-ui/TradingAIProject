"""
Estratega de Trading — Arquitecto de Estrategias por Activo y Contexto.

Rol: Trading Strategist / Strategy Selector
Ubicación: entre FASE 2 (Technical Scout) y FASE 3 (Risk Manager)

Funciones:
  1. Seleccionar la estrategia óptima según el activo y el contexto
  2. Mantener un "playbook" de qué estrategias funcionan para cada instrumento
  3. Filtrar entradas falsas según condiciones específicas del mercado
  4. Adaptar parámetros de indicadores por tipo de activo
  5. Descartar señales en activos donde la estrategia no aplica
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TradingStrategist:
    """
    Arquitecto de estrategias. Conoce el comportamiento de cada activo
    y selecciona la estrategia correcta para cada contexto.

    Playbook de estrategias por activo:
      - Forex:      mean_reversion (rangos europeos), breakout (sesión americana)
      - Crypto:     momentum + breakout (volátil 24/7)
      - Commodities: mean_reversion + tendencia (sigue noticias macro)
      - Indices:    trend following (sesión americana)
    """

    def __init__(self, config: dict):
        self.config = config
        self._decision_log: list[dict] = []

        # ─── Playbook de estrategias por activo ──────────────────────────
        self.playbook = {
            # Forex — pares mayores
            "EUR/USD": {"default": "mean_reversion", "alternate": "breakout", "session": "london_ny", "min_vol": 0.0003},
            "GBP/USD": {"default": "mean_reversion", "alternate": "breakout", "session": "london", "min_vol": 0.0004},
            "USD/JPY": {"default": "breakout", "alternate": "mean_reversion", "session": "asia_london", "min_vol": 0.0003},
            "USD/CAD": {"default": "breakout", "alternate": "mean_reversion", "session": "london_ny", "min_vol": 0.0003},
            "AUD/USD": {"default": "breakout", "alternate": "mean_reversion", "session": "asia", "min_vol": 0.0004},
            "NZD/USD": {"default": "breakout", "alternate": "mean_reversion", "session": "asia", "min_vol": 0.0004},
            "USD/CHF": {"default": "mean_reversion", "alternate": "breakout", "session": "london", "min_vol": 0.0003},
            "EUR/JPY": {"default": "breakout", "alternate": "mean_reversion", "session": "london", "min_vol": 0.0005},
            "GBP/JPY": {"default": "breakout", "alternate": "momentum", "session": "london", "min_vol": 0.0006},
            # Crypto — alta volatilidad
            "BTC/USD": {"default": "momentum", "alternate": "breakout", "session": "24h", "min_vol": 0.005},
            "ETH/USD": {"default": "momentum", "alternate": "breakout", "session": "24h", "min_vol": 0.005},
            "SOL/USD": {"default": "momentum", "alternate": "breakout", "session": "24h", "min_vol": 0.008},
            "BCH/USD": {"default": "momentum", "alternate": "breakout", "session": "24h", "min_vol": 0.008},
            "LTC/USD": {"default": "momentum", "alternate": "breakout", "session": "24h", "min_vol": 0.006},
            "XRP/USD": {"default": "momentum", "alternate": "breakout", "session": "24h", "min_vol": 0.006},
            # Commodities
            "XAU/USD": {"default": "breakout", "alternate": "mean_reversion", "session": "london_ny", "min_vol": 0.002},
            "XAG/USD": {"default": "breakout", "alternate": "momentum", "session": "london_ny", "min_vol": 0.003},
        }

        # ─── Reglas de filtrado de entradas ──────────────────────────────
        self.filters = {
            "mean_reversion": {
                "max_spread_pct": 0.0005,  # Spread máximo para MR (más sensible)
                "min_confidence": 55,
                "avoid_news_window": True,  # No MR 30min antes de noticias
            },
            "breakout": {
                "max_spread_pct": 0.001,
                "min_confidence": 60,
                "min_volume_spike": 1.5,  # Volumen > 1.5x media
            },
            "momentum": {
                "max_spread_pct": 0.003,  # Momentum tolera spreads más altos
                "min_confidence": 65,
                "min_adx": 25,  # Momentum solo con ADX fuerte
            },
        }

    # =========================================================================
    # API PRINCIPAL
    # =========================================================================

    def select_strategy(self, symbol: str, regime: str, market_context: dict) -> dict:
        """
        Selecciona la estrategia óptima para el activo y contexto actual.

        Args:
            symbol: Símbolo a operar (ej: "EUR/USD")
            regime: Régimen detectado ("tendencia", "rango", "alta_volatilidad")
            market_context: Contexto del Master Trader (mood, hora, día)

        Returns:
            dict con estrategia seleccionada, ajustes y advertencias
        """
        play = self.playbook.get(symbol.upper(), self.playbook.get(symbol, {
            "default": "mean_reversion", "alternate": "breakout",
            "session": "24h", "min_vol": 0.001
        }))

        hour = market_context.get("hour", 12)
        mood = market_context.get("market_mood", "favorable")
        warnings = []
        adjustments = {}

        # ─── Seleccionar estrategia base ─────────────────────────────────
        if regime == "tendencia":
            # En tendencia, siempre breakout
            strategy = "breakout"
        elif regime == "alta_volatilidad":
            # Alta volatilidad: momentum
            strategy = "momentum"
        else:
            # Rango: usar default del playbook
            strategy = play["default"]

        # ─── Ajustar por sesión ──────────────────────────────────────────
        session = play["session"]
        if session == "london" and (hour < 7 or hour > 16):
            warnings.append(f"Fuera de sesion London ({session}: {hour}h) — señal debil")
            adjustments["confidence_penalty"] = -10
        elif session == "asia" and (hour < 0 or hour > 9):
            warnings.append(f"Fuera de sesion Asia ({session}: {hour}h)")
            adjustments["confidence_penalty"] = -10
        elif session == "london_ny" and (hour < 7 or hour > 21):
            warnings.append(f"Fuera de sesion principal ({session}: {hour}h)")
            adjustments["confidence_penalty"] = -15
        elif session == "asia_london" and (hour < 1 or hour > 17):
            warnings.append(f"Fuera de ventana Asia-London")
            adjustments["confidence_penalty"] = -10

        # ─── Ajustar por contexto del mercado ────────────────────────────
        if mood == "cauteloso":
            adjustments["confidence_penalty"] = adjustments.get("confidence_penalty", 0) - 10
            adjustments["size_mult"] = 0.7
        elif mood == "peligroso":
            adjustments["confidence_penalty"] = adjustments.get("confidence_penalty", 0) - 25
            adjustments["size_mult"] = 0.4

        # ─── Filtrar estrategia por régimen incompatible ─────────────────
        if strategy == "mean_reversion" and regime == "tendencia":
            warnings.append("MR en tendencia — no recomendado")
            strategy = play["alternate"]
        if strategy == "breakout" and regime == "rango" and mood == "cauteloso":
            warnings.append("Breakout en rango con mercado cauteloso — falso breakout probable")
            strategy = play["alternate"]

        result = {
            "selected_strategy": strategy,
            "playbook_default": play["default"],
            "alternate": play["alternate"],
            "session": play["session"],
            "warnings": warnings,
            "adjustments": adjustments,
            "filters": self.filters.get(strategy, {}),
        }
        self._decision_log.append(result)
        return result

    def validate_entry(self, signal: dict, strategy_info: dict, spread: float) -> dict:
        """
        Valida si una señal debe ejecutarse según las reglas de la estrategia.

        Args:
            signal: Señal del Technical Scout (confidence, rr_ratio, etc.)
            strategy_info: Resultado de select_strategy()
            spread: Spread actual del símbolo

        Returns:
            dict con decision de filtro
        """
        strategy = strategy_info.get("selected_strategy", "mean_reversion")
        filters = self.filters.get(strategy, {})
        confidence = signal.get("confidence", 0)
        rr = signal.get("rr_ratio", 0)
        reasons = []
        rejected = False

        # ─── Filtro 1: Confianza mínima ──────────────────────────────────
        min_conf = filters.get("min_confidence", 50)
        adj_penalty = strategy_info.get("adjustments", {}).get("confidence_penalty", 0)
        effective_min = min_conf + abs(adj_penalty) if adj_penalty < 0 else min_conf

        if confidence < effective_min:
            reasons.append(f"Confianza {confidence:.0f}% < minima ajustada {effective_min:.0f}%")
            rejected = True

        # ─── Filtro 2: RR mínimo por estrategia ──────────────────────────
        rr_minimos = {"mean_reversion": 1.8, "breakout": 2.0, "momentum": 2.2}
        min_rr = rr_minimos.get(strategy, 1.5)
        if rr < min_rr:
            reasons.append(f"RR {rr:.2f} < minimo para {strategy} ({min_rr})")
            rejected = True

        # ─── Filtro 3: Spread máximo por estrategia ──────────────────────
        max_spread = filters.get("max_spread_pct", 0.001)
        # Convertir spread absoluto a porcentaje
        entry = signal.get("entry", 1)
        spread_pct = spread * 0.0001 / entry if entry > 0 else 0
        if spread_pct > max_spread:
            reasons.append(f"Spread {spread_pct:.5f} > maximo {max_spread:.5f} para {strategy}")
            rejected = True

        # ─── Filtro 4: Reglas específicas por estrategia ─────────────────
        if strategy == "momentum" and strategy_info.get("warnings"):
            # Si momentum tiene advertencias de sesión, reducir confianza
            if confidence < 75:
                reasons.append("Momentum fuera de sesion optima y confianza < 75")
                rejected = True

        return {
            "approved": not rejected,
            "reasons": reasons,
            "effective_min_confidence": effective_min,
            "strategy_used": strategy,
        }
