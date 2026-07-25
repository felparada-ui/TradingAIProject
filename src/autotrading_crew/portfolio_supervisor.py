"""
Portfolio Supervisor — Validador de Cartera y Coordinador de Rentabilidad

Rol: Supervisor de Cartera (Portfolio Supervisor)
Ubicación en el flujo: entre FASE 3 (Risk Manager) y FASE 4 (Execution)

Responsabilidades:
  1. Revisar posiciones abiertas en MT5 antes de cada nuevo trade
  2. Detectar trades contradictorios (BUY + SELL mismo símbolo)
  3. Calcular exposición neta por activo y por sector
  4. Decidir si el nuevo trade mejora la rentabilidad global
  5. Sugerir cierre de posiciones perdedoras o apertura de contrarias
  6. Time-based exit: cerrar posiciones que llevan mucho tiempo abiertas
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class PortfolioSupervisor:
    """
    Supervisor de cartera. Valida cada propuesta de trade contra
    el estado actual de la cuenta y las posiciones existentes.
    """

    def __init__(self, config: dict):
        self.config = config
        self._last_decision_log: list[dict] = []

    # =========================================================================
    # API PRINCIPAL
    # =========================================================================

    def validate_trade_proposal(self, proposal: dict, open_positions: list[dict]) -> dict:
        """
        Valida una propuesta de trade contra las posiciones abiertas actuales.

        Args:
            proposal: dict con symbol, side, entry, sl, tp, confidence, regime
            open_positions: lista de posiciones abiertas desde MT5

        Returns:
            dict con decision (GO/NO-GO), razones, y sugerencias
        """
        symbol = proposal.get("symbol", "")
        side = proposal.get("signal", proposal.get("side", ""))
        entry = proposal.get("entry", 0)
        confidence = proposal.get("confidence", 50)

        reasons = []
        warnings = []
        approved = True

        # ─── 1. Verificar posiciones en el MISMO símbolo ────────────────────
        same_symbol_positions = [p for p in open_positions if p.get("symbol", "").upper() == symbol.upper()]

        if same_symbol_positions:
            for pos in same_symbol_positions:
                pos_side = pos.get("side", "?")
                pos_pnl = pos.get("profit", 0)
                pos_entry = pos.get("entry_price", 0)

                if pos_side == side:
                    # Mismo lado: acumular (scaling) - solo si la primera va bien
                    if pos_pnl > 0:
                        reasons.append(f"✅ Scaling {side} en {symbol}: posición existente en ganancia (${pos_pnl:.2f})")
                        confidence = min(100, confidence + 5)
                    else:
                        warnings.append(f"⚠️  {side} existente en {symbol} está perdiendo (${pos_pnl:.2f}) — no acumular")
                        approved = False
                else:
                    # Lado opuesto: HEDGING detectado
                    avg_price = (pos_entry + entry) / 2
                    spread_pct = abs(entry - pos_entry) / avg_price * 100
                    reasons.append(f"🔄 Hedging: {pos_side} a ${pos_entry:.2f} + {side} a ${entry:.2f} (spread {spread_pct:.2f}%)")

                    # El hedging solo tiene sentido si el spread es pequeño
                    if spread_pct < 0.1:
                        reasons.append(f"   Spread mínimo — operaciones casi compensadas, aprobado")
                    elif pos_pnl < 0:
                        # La posición existente está perdiendo: promediar
                        reasons.append(f"   Promediando {pos_side} perdedora (${pos_pnl:.2f}) — {side} como cobertura")
                        approved = True  # Aceptar como cobertura
                    else:
                        warnings.append(f"   ⚠️  Entrando en dirección opuesta a posición ganadora — posible contradicción")
                        approved = False

        # ─── 2. Exposición total por sector ─────────────────────────────────
        sectors = {
            "forex": ["EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD"],
            "crypto": ["BTC", "ETH", "SOL", "BCH", "LTC", "XRP"],
            "commodities": ["XAU", "XAG"],
            "indices": ["SPY", "QQQ", "IWM", "DIA", "SP500", "NAS100", "US30"],
        }

        # Determinar sector del nuevo trade
        new_sector = "unknown"
        upper_sym = symbol.upper()
        for sector, keywords in sectors.items():
            if any(kw in upper_sym for kw in keywords):
                new_sector = sector
                break

        # Contar posiciones abiertas por sector
        sector_counts = {s: 0 for s in sectors}
        for pos in open_positions:
            pos_sym = pos.get("symbol", "").upper()
            for sector, keywords in sectors.items():
                if any(kw in pos_sym for kw in keywords):
                    sector_counts[sector] += 1
                    break

        max_per_sector = {"forex": 3, "crypto": 2, "commodities": 1, "indices": 2}
        max_sector = max_per_sector.get(new_sector, 2)
        current_in_sector = sector_counts.get(new_sector, 0)

        if current_in_sector >= max_sector:
            warnings.append(f"⚠️  Ya hay {current_in_sector} posiciones en sector {new_sector} (máx {max_sector})")
            approved = False

        # ─── 3. Confianza mínima para ejecutar ──────────────────────────────
        if confidence < 50:
            warnings.append(f"⚠️  Confianza baja ({confidence:.0f}%) — umbral mínimo 50%")
            approved = False

        # ─── 4. Time-based check para posiciones existentes ─────────────────
        for pos in open_positions:
            pos_time = pos.get("timestamp", pos.get("entry_time", ""))
            if pos_time:
                try:
                    if isinstance(pos_time, str):
                        pos_dt = datetime.fromisoformat(pos_time.replace("Z", "+00:00").split(".")[0])
                    else:
                        pos_dt = pos_time
                    hours_open = (datetime.now() - pos_dt).total_seconds() / 3600
                    if hours_open > 48:
                        reasons.append(f"⏰ Posición en {pos.get('symbol','?')} lleva {hours_open:.0f}h abierta — considerar cierre")
                except Exception:
                    pass

        # ─── 5. Decisión final ──────────────────────────────────────────────
        decision = "GO" if approved else "NO-GO"

        decision_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "decision": decision,
            "confidence": confidence,
            "reasons": reasons,
            "warnings": warnings,
            "open_positions_in_symbol": len(same_symbol_positions),
        }
        self._last_decision_log.append(decision_record)
        self._last_decision_log = self._last_decision_log[-50:]  # Mantener últimos 50

        return {
            "approved": approved,
            "decision": decision,
            "confidence": round(confidence, 1),
            "reasons": reasons,
            "warnings": warnings,
        }

    # =========================================================================
    # GESTIÓN DE CIERRE DE POSICIONES
    # =========================================================================

    def check_positions_for_exit(self, open_positions: list[dict]) -> list[dict]:
        """
        Analiza posiciones abiertas y sugiere cierres basado en:
        - Tiempo máximo en operación
        - Drawdown excesivo de una posición individual
        - Take profit / Stop loss próximos
        """
        exit_suggestions = []
        max_hours = self.config.get("riesgo", {}).get("max_dias_operacion", 5) * 24

        for pos in open_positions:
            symbol = pos.get("symbol", "?")
            side = pos.get("side", "?")
            profit = pos.get("profit", 0)
            entry = pos.get("entry_price", 0)
            current = pos.get("current_price", 0)
            sl = pos.get("stop_loss", 0)
            tp = pos.get("take_profit", 0)

            # Calcular tiempo abierto
            pos_time = pos.get("timestamp", pos.get("entry_time", ""))
            hours_open = 0
            if pos_time:
                try:
                    if isinstance(pos_time, str):
                        pos_dt = datetime.fromisoformat(pos_time.replace("Z", "+00:00").split(".")[0])
                    else:
                        pos_dt = pos_time
                    hours_open = (datetime.now() - pos_dt).total_seconds() / 3600
                except Exception:
                    pass

            # Sugerencia por tiempo excedido
            if hours_open > max_hours and abs(profit) < 1.0:
                exit_suggestions.append({
                    "symbol": symbol,
                    "side": side,
                    "reason": f"time_exit ({hours_open:.0f}h > {max_hours}h)",
                    "profit": profit,
                })

            # Sugerencia por pérdida excesiva (>5% del capital en una posición)
            capital = self.config.get("general", {}).get("capital_inicial", 500)
            if profit < -capital * 0.05:
                exit_suggestions.append({
                    "symbol": symbol,
                    "side": side,
                    "reason": f"stop_loss_manual (perdida ${profit:.2f} > 5% capital)",
                    "profit": profit,
                })

            # TP/SL próximos
            if entry > 0 and current > 0:
                if side == "BUY":
                    dist_to_sl = (current - sl) / entry * 100 if sl > 0 else 999
                    dist_to_tp = (tp - current) / entry * 100 if tp > 0 else 999
                else:
                    dist_to_sl = (sl - current) / entry * 100 if sl > 0 else 999
                    dist_to_tp = (current - tp) / entry * 100 if tp > 0 else 999

                if 0 < dist_to_sl < 0.05:
                    exit_suggestions.append({
                        "symbol": symbol,
                        "side": side,
                        "reason": f"sl_cercano (a {dist_to_sl:.3f}%)",
                        "profit": profit,
                    })

        return exit_suggestions

    def get_summary(self) -> dict:
        """Resumen de decisiones del supervisor."""
        total = len(self._last_decision_log)
        go_count = sum(1 for d in self._last_decision_log if d["decision"] == "GO")
        no_go_count = total - go_count

        return {
            "total_decisions": total,
            "go_count": go_count,
            "no_go_count": no_go_count,
            "last_decision": self._last_decision_log[-1] if self._last_decision_log else None,
        }
