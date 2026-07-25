"""
Continuous Improvement Agent — Meta-agente de auto-mejora de la Crew.

Rol: Analista de Mejora Continua (Continuous Improvement)
Ubicación: se ejecuta al final de cada ciclo, analiza resultados y
           propone mejoras al sistema (nuevos roles, ajustes, exclusiones).

Responsabilidades:
  1. Analizar históricos de trades y detectar patrones de fracaso
  2. Identificar gaps en la estructura actual de agentes
  3. Sugerir nuevos roles, herramientas o modificaciones al workflow
  4. Detectar configuraciones obsoletas o contraproducentes
  5. Registrar recomendaciones en un archivo de mejora continua
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

IMPROVEMENT_LOG = "data/crew_improvements.json"


class ContinuousImprovement:
    """
    Analiza el rendimiento de la Crew y propone mejoras continuas.
    Se ejecuta al final de cada ciclo y acumula recomendaciones.
    """

    def __init__(self, config: dict):
        self.config = config
        self._recommendations: list[dict] = []
        self._analysis_history: list[dict] = []
        self._load_history()

    # =========================================================================
    # API PRINCIPAL
    # =========================================================================

    def analyze_cycle(self, cycle_result: dict) -> list[dict]:
        """
        Analiza el resultado del ciclo actual y genera recomendaciones.

        Args:
            cycle_result: dict con datos del ciclo (trades, fallos, estado)

        Returns:
            list[dict] con recomendaciones
        """
        recommendations = []

        # ─── 1. Analizar fallos de ejecución ────────────────────────────────
        failed = cycle_result.get("failed_symbols", {})
        if failed:
            top_failures = sorted(failed.items(), key=lambda x: -x[1])[:3]
            for symbol, count in top_failures:
                if count >= 3:
                    recommendations.append(self._rec(
                        tipo="exclusion",
                        severidad="alta",
                        mensaje=f"Excluir {symbol} del scan permanente: {count} fallos",
                        accion=f"Agregar {symbol} a lista negra en tools.py",
                    ))

        # ─── 2. Analizar señales perdidas ──────────────────────────────────
        candidates = cycle_result.get("candidates", [])
        rejected_by_rr = sum(1 for c in candidates if c.get("validation_result") == "RR_TOO_LOW")
        if rejected_by_rr > 3:
            recommendations.append(self._rec(
                tipo="configuracion",
                severidad="media",
                mensaje=f"{rejected_by_rr} trades rechazados por RR bajo en este ciclo",
                accion="Reducir take_profit_minimo_rr de 2.0 a 1.5 en config.yaml",
            ))

        # ─── 3. Detectar gaps en agentes ────────────────────────────────────
        existing_roles = cycle_result.get("active_roles", [])
        gaps = self._detect_role_gaps(existing_roles, cycle_result)
        recommendations.extend(gaps)

        # ─── 4. Analizar concentración de símbolos ──────────────────────────
        scanned = cycle_result.get("scanned_symbols", [])
        always_top = self._detect_symbol_concentration(scanned)
        if always_top:
            recommendations.append(self._rec(
                tipo="diversificacion",
                severidad="baja",
                mensaje=f"Los mismos símbolos siempre en top: {always_top}",
                accion="Rotar símbolos manualmente o agregar nuevos al scan",
            ))

        # ─── 5. Evaluar efectividad de regimen ──────────────────────────────
        regime_stats = cycle_result.get("regime_stats", {})
        for regime, stats in regime_stats.items():
            trades = stats.get("trades", 0)
            win_rate = stats.get("win_rate", 0)
            if trades >= 5 and win_rate < 30:
                recommendations.append(self._rec(
                    tipo="estrategia",
                    severidad="alta",
                    mensaje=f"Estrategia {regime} solo {win_rate:.0f}% WR en {trades} trades",
                    accion=f"Ajustar parametros de {regime} en strategies/ o reducir su peso",
                ))

        # Guardar recomendaciones
        self._recommendations.extend(recommendations)
        self._save_history(cycle_result)

        return recommendations

    def get_pending_recommendations(self, min_severidad: str = "media") -> list[dict]:
        """Retorna recomendaciones pendientes por aplicar."""
        severidad_order = {"alta": 0, "media": 1, "baja": 2}
        min_score = severidad_order.get(min_severidad, 1)
        return [
            r for r in self._recommendations
            if severidad_order.get(r.get("severidad", "baja"), 2) <= min_score
            and not r.get("aplicada", False)
        ]

    def mark_applied(self, recommendation_id: str):
        """Marca una recomendación como aplicada."""
        for r in self._recommendations:
            if r.get("id") == recommendation_id:
                r["aplicada"] = True
                r["fecha_aplicacion"] = datetime.now().isoformat()
                self._save_recommendations()
                break

    def generate_report(self) -> str:
        """Genera un reporte legible de todas las recomendaciones."""
        lines = []
        lines.append("=" * 60)
        lines.append("  INFORME DE MEJORA CONTINUA — CREW AUTOTRADING")
        lines.append("=" * 60)

        pendientes = self.get_pending_recommendations("baja")
        aplicadas = [r for r in self._recommendations if r.get("aplicada", False)]

        lines.append(f"\n📌 Recomendaciones pendientes: {len(pendientes)}")
        for r in pendientes:
            lines.append(f"\n  [{r.get('severidad','?').upper()}] {r.get('mensaje','')}")
            lines.append(f"         Acción: {r.get('accion','')}")
            lines.append(f"         Tipo: {r.get('tipo','')} | ID: {r.get('id','')}")

        lines.append(f"\n✅ Recomendaciones aplicadas: {len(aplicadas)}")
        for r in aplicadas[-5:]:
            lines.append(f"  • {r.get('mensaje','')} ({r.get('fecha_aplicacion','')[:10]})")

        lines.append(f"\n📊 Historial: {len(self._analysis_history)} ciclos analizados")
        lines.append("=" * 60)

        return "\n".join(lines)

    # =========================================================================
    # MÉTODOS INTERNOS
    # =========================================================================

    def _detect_role_gaps(self, existing_roles: list[str], cycle_result: dict) -> list[dict]:
        """
        Analiza el pipeline completo y detecta qué roles faltan.

        Reglas de detección de gaps:
        1. Si hay +3 señales pero 0 ejecuciones → falta Execution Validator
        2. Si todos los trades son del mismo régimen → falta Regime Diversifier
        3. Si el win rate es <30% tras 10+ trades → falta Strategy Optimizer
        4. Si hay posiciones abiertas por +48h sin movimiento → falta Exit Manager
        5. Si el spread rechaza +50% de candidatos → falta Liquidity Scout
        6. Si el supervisor rechaza +60% por sector → falta Sector Allocator
        7. Si el profit factor es <1.0 tras 20 trades → falta Risk Rebalancer
        """
        recs = []
        missing_roles = set()
        pipeline = cycle_result.get("pipeline_stats", {})
        total_trades = cycle_result.get("total_trades", 0)
        candidates = cycle_result.get("candidates", [])
        win_rate = cycle_result.get("win_rate", 0)
        pnl = cycle_result.get("current_pnl", 0)
        open_positions = cycle_result.get("open_positions_count", 0)
        regime_stats = cycle_result.get("regime_stats", {})
        sentiment_source = cycle_result.get("sentiment_source", "")

        # ─── Gap 1: Execution Validator ────────────────────────────────────
        # Si hay candidatos pero ninguno llega a ejecución
        signals_count = len(candidates) if isinstance(candidates, list) else 0
        if signals_count >= 5 and total_trades == 0:
            missing_roles.add("execution_validator")
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="alta",
                mensaje=f"{signals_count} señales generadas pero 0 ejecutadas — falta un Execution Validator",
                accion="Crear agente ExecutionValidator que revise por qué las senales no llegan a MT5 y ajuste parametros",
            ))

        # ─── Gap 2: Regime Diversifier ─────────────────────────────────────
        # Si todas las operaciones son del mismo régimen (solo rango)
        if regime_stats:
            regimes_detected = list(regime_stats.keys())
            if len(regimes_detected) <= 1 and total_trades >= 5:
                missing_roles.add("regime_diversifier")
                recs.append(self._rec(
                    tipo="nuevo_rol",
                    severidad="alta",
                    mensaje=f"Solo se opera en regimen '{regimes_detected[0] if regimes_detected else '?'}' — falta diversificar",
                    accion="Crear agente RegimeDiversifier que fuerce busqueda de oportunidades en otros regimenes",
                ))

        # ─── Gap 3: Strategy Optimizer ─────────────────────────────────────
        # Si el win rate es bajo con suficientes datos
        if total_trades >= 10 and win_rate < 35:
            missing_roles.add("strategy_optimizer")
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="alta",
                mensaje=f"Win rate {win_rate:.0f}% en {total_trades} trades — falta un Strategy Optimizer",
                accion="Crear agente StrategyOptimizer que ajuste parametros de indicadores (BB period, RSI thresholds, ADX)",
            ))

        # ─── Gap 4: Exit Manager ──────────────────────────────────────────
        # Si hay posiciones abiertas hace tiempo
        if open_positions >= 2 and total_trades >= 5:
            missing_roles.add("exit_manager")
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="media",
                mensaje=f"{open_positions} posiciones abiertas — falta un Exit Manager",
                accion="Crear agente ExitManager que monitoree trailing stops, time-based exits y cierre de posiciones",
            ))

        # ─── Gap 5: News Monitor ──────────────────────────────────────────
        # Si el sentimiento es simulado
        if sentiment_source == "simulated" and total_trades >= 5:
            missing_roles.add("news_monitor")
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="baja",
                mensaje="Sentimiento simulado — falta un News Monitor real",
                accion="Conectar NewsAPI o crear agente NewsMonitor con fuentes RSS financieras",
            ))

        # ─── Gap 6: Risk Rebalancer ────────────────────────────────────────
        # Si el PnL es negativo después de varios trades
        if total_trades >= 20 and pnl < 0:
            missing_roles.add("risk_rebalancer")
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="alta",
                mensaje=f"PnL negativo (${pnl:.2f}) en {total_trades} trades — falta Risk Rebalancer",
                accion="Crear agente RiskRebalancer que reduzca riesgo progresivamente tras perdidas",
            ))

        # ─── Gap 7: Backtest Validator ─────────────────────────────────────
        # Si nunca se ha hecho backtest
        if total_trades >= 10 and not any("backtest" in r.get("accion", "") for r in self._recommendations):
            missing_roles.add("backtest_validator")
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="media",
                mensaje=f"{total_trades} trades en vivo sin respaldo de backtest — falta Backtest Validator",
                accion="Crear agente BacktestValidator que ejecute backtests periodicos con datos reales",
            ))

        return recs

        for role in missing_roles:
            recs.append(self._rec(
                tipo="nuevo_rol",
                severidad="media",
                mensaje=f"Rol faltante detectado: {role}",
                accion=f"Crear agente {role} con herramientas especificas",
            ))

        return recs

    def _detect_symbol_concentration(self, scanned: list[str]) -> list[str]:
        """Detecta si siempre aparecen los mismos símbolos en el top."""
        # Esta función requiere seguimiento entre ciclos
        # Por ahora, es un placeholder
        return []

    def _rec(self, tipo: str, severidad: str, mensaje: str, accion: str) -> dict:
        """Crea una recomendación estructurada."""
        return {
            "id": f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._recommendations)}",
            "tipo": tipo,
            "severidad": severidad,
            "mensaje": mensaje,
            "accion": accion,
            "fecha": datetime.now().isoformat(),
            "aplicada": False,
        }

    def _save_history(self, cycle_result: dict):
        """Guarda el análisis del ciclo."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "cycle_data": cycle_result,
            "recommendations": self._recommendations[-5:],
        }
        self._analysis_history.append(record)
        # Mantener últimos 100 ciclos
        self._analysis_history = self._analysis_history[-100:]

        # Guardar a disco
        try:
            os.makedirs(os.path.dirname(IMPROVEMENT_LOG), exist_ok=True)
            data = {
                "recommendations": self._recommendations,
                "history_count": len(self._analysis_history),
                "last_update": datetime.now().isoformat(),
            }
            with open(IMPROVEMENT_LOG, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"No se pudo guardar historial de mejora: {e}")

    def _load_history(self):
        """Carga recomendaciones previas desde disco."""
        try:
            if os.path.exists(IMPROVEMENT_LOG):
                with open(IMPROVEMENT_LOG) as f:
                    data = json.load(f)
                self._recommendations = data.get("recommendations", [])
                logger.info(f"Mejora continua: {len(self._recommendations)} recomendaciones cargadas")
        except Exception as e:
            logger.debug(f"Sin historial de mejora previo: {e}")

    def _save_recommendations(self):
        """Guarda solo las recomendaciones."""
        try:
            data = {
                "recommendations": self._recommendations,
                "history_count": len(self._analysis_history),
                "last_update": datetime.now().isoformat(),
            }
            with open(IMPROVEMENT_LOG, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            pass
