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
        """Detecta qué roles faltan en la Crew según los problemas actuales."""
        recs = []
        missing_roles = []

        # Detectar si falta un rol de cierre automático de posiciones
        if cycle_result.get("open_positions_count", 0) > 0:
            has_exit_manager = "exit_manager" in existing_roles or "portfolio_supervisor" in existing_roles
            if not has_exit_manager:
                missing_roles.append("exit_manager")

        # Detectar si falta un rol de monitoreo de noticias en tiempo real
        if cycle_result.get("sentiment_source", "") == "simulated":
            missing_roles.append("news_monitor")

        # Detectar si falta un rol de optimización de parámetros
        if cycle_result.get("total_trades", 0) > 10:
            missing_roles.append("param_optimizer")

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
