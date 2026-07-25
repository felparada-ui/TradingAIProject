"""
Gestor de Riesgos Avanzado

Responsabilidades:
  - Cálculo de tamaño de posición (Kelly fraccional, VaR, ATR-based)
  - Validación de límites de riesgo por operación y diarios
  - Cálculo de correlación entre posiciones abiertas
  - Trailing stop progresivo
  - Circuit breaker (drawdown diario > 5%, drawdown total > 15%)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RiskManager:
    """Núcleo de gestión de riesgos del sistema de autotrading."""

    def __init__(self, config: dict):
        risk_cfg = config.get("riesgo", {})
        general_cfg = config.get("general", {})

        self.capital = general_cfg.get("capital_inicial", 10000.0)
        self.risk_per_trade_pct = risk_cfg.get("riesgo_maximo_por_operacion", 1.5) / 100.0
        self.max_daily_dd_pct = risk_cfg.get("riesgo_maximo_diario", 5.0) / 100.0
        self.max_total_dd_pct = risk_cfg.get("riesgo_maximo_total", 15.0) / 100.0
        self.atr_sl_mult = risk_cfg.get("factor_volatilidad_atr", 1.5)
        self.min_rr = risk_cfg.get("take_profit_minimo_rr", 1.8)
        self.trail_activation_rr = risk_cfg.get("trailing_activacion", 1.2)
        self.trail_step_atr = risk_cfg.get("trailing_step", 0.3)
        self.max_correlation = risk_cfg.get("correlacion_maxima_permisible", 0.70)
        self.max_open_positions = general_cfg.get("max_operaciones_simultaneas", 5)

        # Estado interno
        self._daily_pnl = 0.0
        self._total_pnl = 0.0
        self._peak_capital = self.capital
        self._open_positions: list[dict] = []
        self._daily_trades = 0
        self._circuit_breaker_active = False
        self._last_reset_day = datetime.now().date()

    # ------------------------------------------------------------------
    # API pública (herramientas para CrewAI)
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        atr: float,
        account_balance: Optional[float] = None,
    ) -> dict:
        """
        Calcula el tamaño de posición óptimo usando:
        1. Risk % fijo del capital
        2. ATR-based sizing
        3. Fraccional Kelly simplificado
        """
        self._reset_daily_if_needed()

        if self._circuit_breaker_active:
            return {"error": "CIRCUIT_BREAKER_ACTIVO", "size": 0, "reason": "Riesgo diario excedido"}

        balance = account_balance or self.capital
        risk_amount = balance * self.risk_per_trade_pct
        risk_per_unit = abs(entry_price - stop_loss)

        if risk_per_unit <= 0 or entry_price <= 0:
            return {"error": "PRECIO_INVALIDO", "size": 0}

        # Tamaño base por riesgo fijo
        base_units = risk_amount / risk_per_unit

        # ATR-based adjustment
        atr_pct = atr / entry_price if entry_price > 0 else 0
        if atr_pct > 0.03:  # Alta volatilidad → reducir tamaño
            atr_factor = max(0.3, 1.0 - (atr_pct - 0.03) * 10)
        else:
            atr_factor = 1.0

        # Fraccional Kelly (simplificado: asume win_rate=0.55, avg_win/avg_loss=2.0)
        kelly_pct = 0.55 - (1 - 0.55) / 2.0
        kelly_fraction = max(0.05, min(0.25, kelly_pct))
        kelly_factor = kelly_fraction / 0.25

        # Tamaño base en unidades
        base_units = risk_amount / risk_per_unit
        final_units = max(1, int(base_units * atr_factor * kelly_factor))

        # Ajustar a lote mínimo MT5 (0.01 = 1,000 unidades para forex)
        min_lot_units = 1000  # 0.01 lotes estándar
        lot_size = max(0.01, round(final_units / min_lot_units, 2))
        final_units = int(lot_size * min_lot_units)

        position_value = final_units * entry_price
        risk_pct = (position_value * risk_per_unit / entry_price) / balance * 100 if balance > 0 else 0

        return {
            "units": final_units,
            "lot_size": lot_size,
            "position_value": round(position_value, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_pct": round(risk_pct, 2),
            "balance": round(balance, 2),
            "atr_factor": round(atr_factor, 2),
            "kelly_factor": round(kelly_factor, 2),
        }

    def validate_risk_limits(
        self,
        side: str,
        entry: float,
        sl: float,
        tp: float,
        atr: float,
        symbol: str,
    ) -> dict:
        """
        Valida que la operación cumpla con todos los límites de riesgo.
        Retorna {'approved': True/False, 'reasons': [...]}
        """
        reasons = []
        approved = True

        # 1. Relación Riesgo/Recompensa
        if side.upper() == "BUY":
            rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
        else:
            rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0

        if rr < self.min_rr:
            reasons.append(f"RR={rr:.2f} < mínimo {self.min_rr}")
            approved = False

        # 2. Número de operaciones abiertas
        if len(self._open_positions) >= self.max_open_positions:
            reasons.append(f"Máx operaciones simultáneas ({self.max_open_positions}) alcanzado")
            approved = False

        # 3. Correlación con posiciones abiertas
        for pos in self._open_positions:
            if pos.get("symbol") == symbol:
                reasons.append(f"Ya hay posición abierta en {symbol}")
                approved = False
                break

        # 4. Spread / volatilidad
        atr_pct = atr / entry * 100 if entry > 0 else 0
        if atr_pct > 5.0:
            reasons.append(f"ATR%={atr_pct:.2f}% > 5% — volatilidad extrema")
            approved = False

        # 5. Circuit breaker
        if self._circuit_breaker_active:
            reasons.append("Circuit breaker activo — trading suspendido")
            approved = False

        return {"approved": approved, "reasons": reasons, "rr": round(rr, 2)}

    def compute_portfolio_correlation(self, symbol_prices: dict[str, pd.Series]) -> dict:
        """
        Calcula la matriz de correlación entre los símbolos en posiciones
        abiertas y el nuevo símbolo candidato.
        """
        if len(symbol_prices) < 2:
            return {"max_correlation": 0.0, "pairs": []}

        df = pd.DataFrame(symbol_prices)
        corr_matrix = df.corr().abs()

        pairs = []
        max_corr = 0.0
        symbols = list(symbol_prices.keys())
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                c = corr_matrix.iloc[i, j]
                pairs.append({
                    "pair": f"{symbols[i]}-{symbols[j]}",
                    "correlation": round(c, 4),
                })
                if c > max_corr:
                    max_corr = c

        return {
            "max_correlation": round(max_corr, 4),
            "pairs": pairs,
            "risk_ok": max_corr <= self.max_correlation,
        }

    def manage_trailing_stop(
        self,
        position: dict,
        current_price: float,
        atr: float,
    ) -> dict:
        """
        Gestiona el trailing stop dinámico.
        Se activa cuando el RR realizado supera trail_activation_rr.
        """
        side = position.get("side", "BUY")
        entry = position.get("entry_price", 0)
        current_sl = position.get("stop_loss", 0)

        if side.upper() == "BUY":
            unrealized_rr = (current_price - entry) / (entry - current_sl) if (entry - current_sl) > 0 else 0
            if unrealized_rr >= self.trail_activation_rr:
                new_sl = current_price - atr * self.trail_step_atr
                if new_sl > current_sl:
                    return {
                        "update": True,
                        "new_stop_loss": round(new_sl, 5),
                        "unrealized_rr": round(unrealized_rr, 2),
                        "locked_profit": round((new_sl - entry) / entry * 100, 2),
                    }
        else:  # SELL
            unrealized_rr = (entry - current_price) / (current_sl - entry) if (current_sl - entry) > 0 else 0
            if unrealized_rr >= self.trail_activation_rr:
                new_sl = current_price + atr * self.trail_step_atr
                if new_sl < current_sl:
                    return {
                        "update": True,
                        "new_stop_loss": round(new_sl, 5),
                        "unrealized_rr": round(unrealized_rr, 2),
                        "locked_profit": round((entry - new_sl) / entry * 100, 2),
                    }

        return {"update": False, "unrealized_rr": round(unrealized_rr, 2)}

    def check_circuit_breaker(self, current_pnl: float) -> dict:
        """Verifica si se debe activar el circuit breaker."""
        self._total_pnl = current_pnl
        current_capital = self.capital + current_pnl

        # Actualizar pico de capital
        if current_capital > self._peak_capital:
            self._peak_capital = current_capital

        # Drawdown desde el pico
        dd_from_peak = (self._peak_capital - current_capital) / self._peak_capital if self._peak_capital > 0 else 0

        # Drawdown diario
        daily_dd = abs(self._daily_pnl) / self.capital if self.capital > 0 else 0

        reasons = []
        triggered = False

        if daily_dd >= self.max_daily_dd_pct:
            triggered = True
            self._circuit_breaker_active = True
            reasons.append(f"Drawdown diario {daily_dd:.2%} ≥ {self.max_daily_dd_pct:.2%}")

        if dd_from_peak >= self.max_total_dd_pct:
            triggered = True
            self._circuit_breaker_active = True
            reasons.append(f"Drawdown total {dd_from_peak:.2%} ≥ {self.max_total_dd_pct:.2%}")

        if not triggered and self._circuit_breaker_active:
            # Auto-release si el mercado se recupera
            if daily_dd < self.max_daily_dd_pct * 0.6:
                self._circuit_breaker_active = False
                reasons.append("Circuit breaker desactivado — drawdown recuperado")

        return {
            "circuit_breaker_active": self._circuit_breaker_active,
            "daily_dd_pct": round(daily_dd * 100, 2),
            "total_dd_pct": round(dd_from_peak * 100, 2),
            "peak_capital": round(self._peak_capital, 2),
            "current_capital": round(current_capital, 2),
            "reasons": reasons,
        }

    # ------------------------------------------------------------------
    # Métodos de estado interno
    # ------------------------------------------------------------------

    def register_trade(self, trade: dict):
        """Registra una nueva operación abierta."""
        trade["_open_since"] = datetime.now()
        trade["_bars_held"] = 0
        self._open_positions.append(trade)
        self._daily_trades += 1

    def remove_position(self, symbol: str):
        """Elimina una posición cerrada del registro."""
        self._open_positions = [p for p in self._open_positions if p.get("symbol") != symbol]

    def update_pnl(self, pnl: float):
        """Actualiza el PnL diario."""
        self._daily_pnl += pnl

    def apply_swap_costs(self, config: dict) -> float:
        """
        Aplica costos de swap (overnight) a posiciones abiertas.
        Retorna el costo total de swap en USD.
        """
        riesgo_cfg = config.get("riesgo", {})
        swap_rates = {
            "forex": riesgo_cfg.get("swap_diario_forex", 0.15),
            "crypto": riesgo_cfg.get("swap_diario_crypto", 0.50),
            "etf": riesgo_cfg.get("swap_diario_etf", 0.10),
        }
        max_dias = riesgo_cfg.get("max_dias_operacion", 5)

        total_swap = 0.0
        now = datetime.now()

        for pos in self._open_positions:
            opened = pos.get("_open_since", now)
            days_open = (now - opened).days
            pos["_bars_held"] = days_open

            if days_open < 1:
                continue

            # Determinar categoría del símbolo
            symbol = pos.get("symbol", "")
            if any(c in symbol.upper() for c in ["BTC", "ETH", "SOL", "BCH", "LTC", "XRP"]):
                rate = swap_rates["crypto"]
            elif any(c in symbol.upper() for c in ["SPY", "QQQ", "IWM", "DIA", "SP500"]):
                rate = swap_rates["etf"]
            else:
                rate = swap_rates["forex"]

            # Aplicar swap por cada día completo
            swap_cost = days_open * rate * pos.get("volume", 1)
            total_swap += swap_cost

            # Advertencia si lleva muchos días
            if days_open > max_dias:
                logger.warning(f"PosiciÃ³n en {symbol} lleva {days_open} dÃas — swap acumulado: ${swap_cost:.2f}")

        return total_swap

    def _reset_daily_if_needed(self):
        """Resetea contadores diarios si cambió el día."""
        today = datetime.now().date()
        if today != self._last_reset_day:
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset_day = today

    def get_status_summary(self) -> dict:
        """Retorna un resumen del estado actual de riesgos."""
        return {
            "capital": round(self.capital, 2),
            "open_positions": len(self._open_positions),
            "daily_trades": self._daily_trades,
            "daily_pnl": round(self._daily_pnl, 2),
            "total_pnl": round(self._total_pnl, 2),
            "circuit_breaker": self._circuit_breaker_active,
            "peak_capital": round(self._peak_capital, 2),
        }
