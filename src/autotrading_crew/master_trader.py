"""
Master Trader — Estratega Senior con 20+ años de experiencia.

Rol: Master Trader / Chief Trader / El Veterano
Ubicación: FASE 0 (pre-análisis) + FASE 5 (decisión final)

Este agente representa al trader institucional con 20+ años operando
en mercados globales. Ha sobrevivido a crashes, mercados laterales de
años, burbujas y todo lo que el mercado puede ofrecer.

No reemplaza a los agentes cuantitativos — los complementa con:
  - Intuición de mercado (pattern recognition experiencial)
  - Visión macroeconómica de largo plazo
  - Capacidad de veto basada en contextos que ningún modelo captura
  - Sabiduría de cuándo NO operar (la lección más cara de aprender)
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class MasterTrader:
    """
    El estratega senior de la mesa de operaciones.
    Tiene la última palabra sobre cada operación.

    Su experiencia de 20+ años se modela como:
    - Heurísticas de mercado (reglas empíricas)
    - Memoria de patrones históricos
    - Evaluación cualitativa del contexto global
    """

    def __init__(self, config: dict):
        self.config = config
        self._trade_log: list[dict] = []
        self._veto_count = 0
        self._override_count = 0

        # ─── Heurísticas del veterano (20+ años de experiencia) ──────────
        self.rules = [
            # Regla 1: "No operes antes de noticias importantes"
            {
                "id": "news_avoidance",
                "descripcion": "Evitar entrar 2h antes de eventos de alto impacto",
                "peso": 10,  # Peso de la recomendación (1-10)
                "activa": True,
            },
            # Regla 2: "La tendencia es tu amiga"
            {
                "id": "trend_is_friend",
                "descripcion": "En tendencia fuerte, solo operar en direccion de la tendencia",
                "peso": 8,
                "activa": True,
            },
            # Regla 3: "No promedies una perdedora"
            {
                "id": "no_avg_down",
                "descripcion": "Si una posicion va en contra, no agregar mas capital",
                "peso": 9,
                "activa": True,
            },
            # Regla 4: "Los viernes son peligrosos"
            {
                "id": "friday_caution",
                "descripcion": "Reducir tamaño los viernes (cierre de semana, gaps dominicales)",
                "peso": 6,
                "activa": True,
            },
            # Regla 5: "Mercado en rango = scalping, no tendencia"
            {
                "id": "range_discipline",
                "descripcion": "En mercado lateral, usar profit taking rapido, no holdear",
                "peso": 7,
                "activa": True,
            },
            # Regla 6: "Despues de 3 perdidas consecutivas, parar"
            {
                "id": "three_strikes",
                "descripcion": "Tres perdidas seguidas = stop trading por el dia",
                "peso": 10,
                "activa": True,
            },
            # Regla 7: "Cuando todos son bullish, vende"
            {
                "id": "contrarian",
                "descripcion": "Sentimiento extremo (>80% bullish) es señal contraria",
                "peso": 7,
                "activa": True,
            },
        ]

    # =========================================================================
    # FASE 0: PRE-ANÁLISIS (Contexto global del mercado)
    # =========================================================================

    def assess_market_context(self, date_info: dict = None) -> dict:
        """
        El veterano evalúa el contexto del mercado antes de cualquier análisis.
        Retorna advertencias y ajustes basados en su experiencia.

        Returns:
            dict con:
            - market_mood: "favorable" | "cauteloso" | "peligroso"
            - warnings: lista de advertencias
            - position_size_mult: factor de ajuste de tamaño (0.0 - 1.0)
        """
        now = datetime.now()
        weekday = now.weekday()
        hour = now.hour
        day_name = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"][weekday]

        warnings = []
        size_mult = 1.0
        mood = "favorable"

        # ─── Regla: Viernes = cautela ──────────────────────────────────────
        if weekday == 4:  # Viernes
            warnings.append("[Experiencia] Viernes: reducir tamaño por cierre semanal y gaps dominicales")
            size_mult *= 0.6
            mood = "cauteloso"

        # ─── Regla: Fin de mes ─────────────────────────────────────────────
        if now.day >= 25 and now.day <= 28:
            warnings.append("[Experiencia] Fin de mes: posible rebalanceo institucional")
            size_mult *= 0.8

        # ─── Regla: Fuera de horario de mercados principales ────────────────
        if hour < 2 or hour > 20:
            warnings.append("[Experiencia] Baja liquidez: spreads mas amplios, slippage mayor")
            size_mult *= 0.7
            mood = "cauteloso"

        # ─── Regla: Inicio de semana ───────────────────────────────────────
        if weekday == 0 and hour < 10:
            warnings.append("[Experiencia] Lunes temprano: el mercado esta asimilando noticias del fin de semana")
            size_mult *= 0.8

        # Resumen
        if size_mult <= 0.5:
            mood = "peligroso"

        return {
            "market_mood": mood,
            "warnings": warnings,
            "position_size_mult": round(size_mult, 2),
            "day": day_name,
            "hour": hour,
            "recommendation": self._mood_recommendation(mood),
        }

    # =========================================================================
    # FASE 5: DECISIÓN FINAL (Aprueba o Veta)
    # =========================================================================

    def final_decision(
        self,
        proposal: dict,
        risk_result: dict,
        supervisor_result: dict,
        context: dict,
        daily_stats: dict,
    ) -> dict:
        """
        El veterano toma la decision FINAL sobre si operar o no.
        Puede VETAR cualquier operacion, incluso si todos los demas aprobaron.

        Args:
            proposal: datos del trade propuesto
            risk_result: resultado del Risk Manager
            supervisor_result: resultado del Portfolio Supervisor
            context: resultado de assess_market_context()
            daily_stats: estadisticas del dia (trades, perdidas, ganancias)

        Returns:
            dict con decision final y justificacion
        """
        symbol = proposal.get("symbol", "?")
        side = proposal.get("signal", "?")
        confidence = proposal.get("confidence", 0)

        reasons = []
        veto = False
        override_up = False  # Aprobar cuando otros dijeron que no

        # ─── Regla 1: Tres strikes ─────────────────────────────────────
        consecutive_losses = daily_stats.get("consecutive_losses", 0)
        if consecutive_losses >= 3:
            reasons.append("[VETO] Tres perdidas consecutivas hoy — paro obligatorio (Regla #6)")
            veto = True

        # ─── Regla 2: Contexto peligroso ───────────────────────────────
        if context.get("market_mood") == "peligroso":
            reasons.append(f"[VETO] Contexto de mercado peligroso: {context.get('warnings', ['?'])[:1]}")
            veto = True

        # ─── Regla 3: Confianza baja ───────────────────────────────────
        if confidence < 55:
            reasons.append(f"[VETO] Confianza baja ({confidence:.0f}%) — el veterano no arriesga capital en senales debiles")
            veto = True

        # ─── Regla 4: Si el Supervisor dijo NO, apoyarlo ───────────────
        if not supervisor_result.get("approved", True):
            reasons.append(f"[APOYO] Coincido con el Portfolio Supervisor: {supervisor_result.get('warnings', [''])[:1]}")
            veto = True

        # ─── Regla 5: Si el Risk Manager dijo SI pero contexto es malo ──
        if risk_result.get("approved", False) and context.get("market_mood") == "cauteloso":
            reasons.append("[CAUTELA] Riesgo aprobado pero contexto cauteloso — reduzca tamaño, no cancele")
            # No veto, pero sugiere reducir tamaño

        # ─── Regla 6: Override — el veterano puede aprobar lo que otros vetaron ──
        if not risk_result.get("approved", True) and confidence >= 85:
            reasons.append("[OVERRIDE] Confianza muy alta (>85%) — el veterano pasa por encima del Risk Manager")
            override_up = True
            veto = False

        # ─── Decision final ────────────────────────────────────────────────
        decision = "VETO" if veto else ("OVERRIDE" if override_up else "APROBADO")

        record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "decision": decision,
            "reasons": reasons,
            "confidence": confidence,
        }
        self._trade_log.append(record)
        self._trade_log = self._trade_log[-100:]
        if veto:
            self._veto_count += 1
        if override_up:
            self._override_count += 1

        return {
            "decision": decision,
            "approved": not veto,
            "override": override_up,
            "reasons": reasons,
            "size_adjustment": context.get("position_size_mult", 1.0),
        }

    # =========================================================================
    # VISTA GENERAL DEL VETERANO
    # =========================================================================

    def get_market_wisdom(self) -> str:
        """El veterano comparte una reflexion basada en su experiencia."""
        wisdoms = [
            "Los mercados pueden permanecer irracionales mas tiempo del que tu puedes permanecer solvente.",
            "La primera perdida es la mejor perdida. Corta tus perdedoras rapido.",
            "No confundas un mercado en rango con una tendencia. Cuestan caro.",
            "El mejor trade es a veces el que no haces.",
            "El mercado sube en escalera y baja en ascensor.",
            "Opera el plan, no tu emocion del momento.",
            "Si no sabes quien eres, el mercado es un lugar muy caro para descubrirlo.",
            "La paciencia no es la capacidad de esperar, sino la capacidad de mantener una buena actitud mientras esperas.",
        ]
        import random
        return random.choice(wisdoms)

    def get_veto_stats(self) -> dict:
        return {
            "total_vetos": self._veto_count,
            "total_overrides": self._override_count,
            "trade_log_count": len(self._trade_log),
        }

    # =========================================================================
    # INTERNO
    # =========================================================================

    def _mood_recommendation(self, mood: str) -> str:
        recommendations = {
            "favorable": "Condiciones normales. Operar con parametros estandar.",
            "cauteloso": "Reducir tamanos 20-40%. Preferir setups de alta probabilidad.",
            "peligroso": "Considerar no operar. Si se opera, solo senales de maxima calidad.",
        }
        return recommendations.get(mood, "Condiciones normales.")
