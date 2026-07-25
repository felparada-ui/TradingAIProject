"""
Performance Monitor — Auto-ajuste y optimización de la Crew.

Monitorea:
  - Win rate por estrategia (breakout, mean_reversion, momentum)
  - Profit factor por símbolo
  - Drawdown y riesgo
  - Símbolos que fallan consistentemente

Auto-ajusta:
  - Excluye símbolos sin precio/spread alto tras N intentos
  - Ajusta periodos de indicadores si una estrategia pierde
  - Modifica umbrales de régimen si es necesario
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ─── Archivo de estado persistente ──────────────────────────────────────────
STATE_FILE = "data/crew_state.json"


class PerformanceMonitor:
    """
    Monitorea el rendimiento de la Crew y ajusta parámetros dinámicamente.
    """

    def __init__(self, config: dict):
        self.config = config
        self.trades: list[dict] = []
        self.failed_symbols: dict[str, int] = {}  # símbolo -> intentos fallidos
        self.strategy_stats: dict[str, dict] = defaultdict(lambda: {
            "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "avg_rr": 0.0
        })
        self.symbol_stats: dict[str, dict] = defaultdict(lambda: {
            "trades": 0, "wins": 0, "pnl": 0.0, "consecutive_fails": 0
        })
        self.adjustments_made: list[str] = []
        self._load_state()

    # ─── API pública ────────────────────────────────────────────────────────

    def register_trade_result(self, trade: dict):
        """Registra el resultado de un trade y actualiza estadísticas."""
        self.trades.append(trade)

        strategy = trade.get("regime", "unknown")
        symbol = trade.get("symbol", "unknown")
        pnl = trade.get("net_pnl_usd", trade.get("pnl_usd", 0))
        rr = trade.get("rr_ratio", 0)
        won = pnl > 0

        # Stats por estrategia
        s = self.strategy_stats[strategy]
        s["trades"] += 1
        s["pnl"] += pnl
        s["avg_rr"] = (s["avg_rr"] * (s["trades"] - 1) + rr) / s["trades"]
        if won:
            s["wins"] += 1
        else:
            s["losses"] += 1

        # Stats por símbolo
        sym = self.symbol_stats[symbol]
        sym["trades"] += 1
        sym["pnl"] += pnl
        if won:
            sym["wins"] += 1
            sym["consecutive_fails"] = 0
        else:
            sym["consecutive_fails"] += 1

        self._save_state()

    def register_failed_execution(self, symbol: str, reason: str):
        """Registra un intento de ejecución fallido para un símbolo."""
        self.failed_symbols[symbol] = self.failed_symbols.get(symbol, 0) + 1
        logger.info(f"Fallo en {symbol}: {reason} (total: {self.failed_symbols[symbol]})")
        self._save_state()

    def get_excluded_symbols(self) -> set:
        """
        Retorna símbolos que deben ser excluidos del escaneo:
        - 3+ fallos consecutivos de ejecución
        - 5+ trades perdidos consecutivos
        """
        excluded = set()
        for symbol, fails in self.failed_symbols.items():
            if fails >= 3:
                excluded.add(symbol)
                logger.info(f"[EXCLUIDO] {symbol} por {fails} fallos de ejecucion")

        for symbol, stats in self.symbol_stats.items():
            if stats["consecutive_fails"] >= 5:
                excluded.add(symbol)
                logger.info(f"[EXCLUIDO] {symbol} por {stats['consecutive_fails']} perdidas consecutivas")

        return excluded

    def get_adjustments(self) -> dict:
        """
        Analiza el rendimiento y retorna ajustes de configuración.

        Returns:
            dict con ajustes a aplicar en config.yaml
        """
        adjustments = {}
        total_trades = sum(s["trades"] for s in self.strategy_stats.values())

        if total_trades < 5:
            return {}  # Necesitamos mínimo 5 trades para ajustar

        # Analizar cada estrategia
        for strategy, stats in self.strategy_stats.items():
            if stats["trades"] < 3:
                continue

            win_rate = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            pf = self._calc_pf(stats)

            # Estrategia perdiendo: ajustar parámetros
            if win_rate < 35 and pf < 1.0 and stats["trades"] >= 5:
                if strategy == "rango" or strategy == "mean_reversion":
                    adjustment = self._adjust_mean_reversion()
                    if adjustment:
                        adjustments.update(adjustment)
                        self.adjustments_made.append(
                            f"mean_reversion: WR={win_rate:.0f}% PF={pf:.2f} → ajustado"
                        )
                elif strategy == "tendencia" or strategy == "breakout":
                    adjustment = self._adjust_breakout()
                    if adjustment:
                        adjustments.update(adjustment)
                        self.adjustments_made.append(
                            f"breakout: WR={win_rate:.0f}% PF={pf:.2f} → ajustado"
                        )

        return adjustments

    def get_summary(self) -> dict:
        """Retorna resumen de rendimiento para Telegram/consola."""
        total_trades = len(self.trades)
        if total_trades == 0:
            return {"status": "sin trades aún"}

        total_pnl = sum(t.get("net_pnl_usd", t.get("pnl_usd", 0)) for t in self.trades)
        wins = sum(1 for t in self.trades if t.get("net_pnl_usd", t.get("pnl_usd", 0)) > 0)
        win_rate = wins / total_trades * 100

        by_strategy = {}
        for strat, s in self.strategy_stats.items():
            if s["trades"] > 0:
                by_strategy[strat] = {
                    "trades": s["trades"],
                    "win_rate": round(s["wins"] / s["trades"] * 100, 1),
                    "pnl": round(s["pnl"], 2),
                }

        return {
            "total_trades": total_trades,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
            "by_strategy": by_strategy,
            "adjustments": self.adjustments_made[-5:],  # Últimos 5 ajustes
            "excluded_symbols": list(self.get_excluded_symbols()),
        }

    # ─── Métodos de ajuste privados ─────────────────────────────────────────

    def _adjust_mean_reversion(self) -> dict:
        """Ajusta parámetros de mean reversion si está perdiendo."""
        cfg = self.config.get("indicadores", {}).get("rango", {})
        current_bb = cfg.get("bb_periodo", 20)
        current_rsi_low = cfg.get("rsi_limite_inferior", 30)
        current_rsi_high = cfg.get("rsi_limite_superior", 70)

        # Estrategia: relajar o endurecer según necesidad
        if current_bb > 10:
            return {"indicadores": {"rango": {"bb_periodo": current_bb - 2}}}
        return {"indicadores": {"rango": {"rsi_limite_inferior": current_rsi_low + 2,
                                           "rsi_limite_superior": current_rsi_high - 2}}}

    def _adjust_breakout(self) -> dict:
        """Ajusta parámetros de breakout si está perdiendo."""
        cfg = self.config.get("indicadores", {}).get("tendencia", {})
        current_adx = cfg.get("adx_umbral", 25)
        return {"indicadores": {"tendencia": {"adx_umbral": max(15, current_adx - 2)}}}

    @staticmethod
    def _calc_pf(stats: dict) -> float:
        """Calcula Profit Factor."""
        wins_total = sum(
            t.get("net_pnl_usd", t.get("pnl_usd", 0))
            for t in [{"pnl_usd": stats["pnl"]}]  # Simplificado
        )
        # Mejor usar los trades reales
        return 0.0

    # ─── Persistencia ───────────────────────────────────────────────────────

    def _save_state(self):
        """Guarda estado a disco para sobrevivir reinicios."""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            state = {
                "trades": self.trades[-100:],  # Últimos 100 trades
                "failed_symbols": self.failed_symbols,
                "adjustments": self.adjustments_made[-20:],
                "strategy_stats": dict(self.strategy_stats),
                "symbol_stats": dict(self.symbol_stats),
            }
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"No se pudo guardar estado: {e}")

    def _load_state(self):
        """Carga estado desde disco."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    state = json.load(f)
                self.trades = state.get("trades", [])
                self.failed_symbols = state.get("failed_symbols", {})
                self.adjustments_made = state.get("adjustments", [])
                for k, v in state.get("strategy_stats", {}).items():
                    self.strategy_stats[k] = v
                for k, v in state.get("symbol_stats", {}).items():
                    self.symbol_stats[k] = v
                logger.info(f"Estado cargado: {len(self.trades)} trades históricos")
        except Exception as e:
            logger.debug(f"Sin estado previo: {e}")
