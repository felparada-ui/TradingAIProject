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
        self._strategy_perf_file = "data/strategy_performance.json"

        # ─── Playbook inicial (neutral + se auto-ajusta con datos) ────────
        # Valores iniciales: todas las estrategias empiezan con peso 1.0
        # El sistema ajusta los pesos según resultados reales
        self.playbook = {}
        self.strategy_weights = {}  # {"EUR/USD": {"mean_reversion": 1.0, "breakout": 1.0, "momentum": 1.0}}
        self._load_performance()
        
        # Si no hay datos, inicializar con pesos neutros
        if not self.playbook:
            symbols = [
                "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
                "NZD/USD", "USD/CHF", "EUR/JPY", "GBP/JPY",
                "BTC/USD", "ETH/USD", "SOL/USD", "BCH/USD", "LTC/USD", "XRP/USD",
                "XAU/USD", "XAG/USD",
            ]
            for sym in symbols:
                self.playbook[sym] = {
                    "strategies": ["mean_reversion", "breakout", "momentum"],
                    "session": self._guess_session(sym),
                    "min_vol": self._guess_min_vol(sym),
                }
                self.strategy_weights[sym] = {"mean_reversion": 1.0, "breakout": 1.0, "momentum": 1.0}
            self._save_performance()

        # ─── Filtros (basados en sentido común, ajustables con datos) ──────
        self.filters = {
            "mean_reversion": {"max_spread_pct": 0.001, "min_confidence": 50},
            "breakout":       {"max_spread_pct": 0.002, "min_confidence": 55},
            "momentum":       {"max_spread_pct": 0.005, "min_confidence": 60},
        }

    # =========================================================================
    # SELECCIÓN DE ESTRATEGIA (basada en datos, no suposiciones)
    # =========================================================================

    def select_strategy(self, symbol: str, regime: str, market_context: dict) -> dict:
        """
        Selecciona la estrategia con mejor rendimiento HISTÓRICO para este activo.
        Si no hay datos históricos, elige por régimen.
        """
        play = self.playbook.get(symbol.upper(), {})
        weights = self.strategy_weights.get(symbol.upper(), {"mean_reversion": 1.0, "breakout": 1.0, "momentum": 1.0})

        hour = market_context.get("hour", 12)
        mood = market_context.get("market_mood", "favorable")
        warnings = []
        adjustments = {}

        # Elegir estrategia: la de mayor peso histórico
        best_strategy = max(weights, key=lambda s: weights[s])
        # Pero si el régimen sugiere otra, darle bonus
        regime_map = {"tendencia": "breakout", "rango": "mean_reversion", "alta_volatilidad": "momentum"}
        regime_strategy = regime_map.get(regime, "mean_reversion")
        if weights.get(regime_strategy, 0) >= weights.get(best_strategy, 0) * 0.8:
            best_strategy = regime_strategy

        strategy = best_strategy

        # Penalización por sesión (solo si hay datos de sesión)
        session = play.get("session", "24h")
        penalty = self._session_penalty(session, hour)
        if penalty:
            warnings.append(f"Fuera de sesion optima ({session}: {hour}h) — penalizando confianza")
            adjustments["confidence_penalty"] = penalty

        # Penalización por contexto de mercado
        if mood == "cauteloso":
            adjustments["confidence_penalty"] = adjustments.get("confidence_penalty", 0) - 10
        elif mood == "peligroso":
            adjustments["confidence_penalty"] = adjustments.get("confidence_penalty", 0) - 25

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

    # =========================================================================
    # AUTO-AJUSTE: aprende de resultados reales
    # =========================================================================

    def register_trade_result(self, symbol: str, strategy: str, won: bool, pnl: float):
        """
        Registra el resultado de un trade y ajusta los pesos de la estrategia.

        Si una estrategia gana, su peso sube. Si pierde, baja.
        Así el sistema DESCUBRE qué funciona para cada activo.
        """
        sym = symbol.upper()
        if sym not in self.strategy_weights:
            self.strategy_weights[sym] = {"mean_reversion": 1.0, "breakout": 1.0, "momentum": 1.0}

        weights = self.strategy_weights[sym]
        current = weights.get(strategy, 1.0)

        # Ajuste: ganar +0.1, perder -0.08 (mínimo 0.3, máximo 3.0)
        if won:
            weights[strategy] = min(3.0, current + 0.1)
        else:
            weights[strategy] = max(0.3, current - 0.08)

        # Registrar también en el playbook
        if sym in self.playbook:
            self.playbook[sym]["strategies"] = sorted(
                weights.keys(), key=lambda s: weights[s], reverse=True
            )

        self._save_performance()
        logger.info(f"[Estratega] {sym} {strategy}: peso {current:.2f} -> {weights[strategy]:.2f} ({'GANO' if won else 'PERDIO'})")

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _guess_session(self, symbol: str) -> str:
        """Estima sesión óptima según el activo (neutral, sin asumir)."""
        crypto = ["BTC", "ETH", "SOL", "BCH", "LTC", "XRP"]
        if any(c in symbol.upper() for c in crypto):
            return "24h"
        return "24h"  # Neutro: no penalizar hasta tener datos

    def _guess_min_vol(self, symbol: str) -> float:
        crypto = ["BTC", "ETH", "SOL", "BCH", "LTC", "XRP"]
        if any(c in symbol.upper() for c in crypto):
            return 0.005
        return 0.0003

    def _session_penalty(self, session: str, hour: int) -> int:
        """Solo penaliza si la sesión es restrictiva (y tenemos datos)."""
        return 0  # Neutro: sin penalización hasta tener datos reales

    def _load_performance(self):
        """Carga rendimiento histórico desde disco."""
        try:
            import json, os
            if os.path.exists(self._strategy_perf_file):
                with open(self._strategy_perf_file) as f:
                    data = json.load(f)
                self.playbook = data.get("playbook", {})
                self.strategy_weights = data.get("weights", {})
                logger.info(f"[Estratega] {len(self.playbook)} activos cargados con datos historicos")
        except Exception as e:
            logger.debug(f"Sin datos de estrategia previos: {e}")

    def _save_performance(self):
        """Guarda rendimiento a disco."""
        try:
            import json, os
            os.makedirs(os.path.dirname(self._strategy_perf_file), exist_ok=True)
            with open(self._strategy_perf_file, "w") as f:
                json.dump({
                    "playbook": self.playbook,
                    "weights": self.strategy_weights,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"No se pudo guardar rendimiento de estrategias: {e}")
