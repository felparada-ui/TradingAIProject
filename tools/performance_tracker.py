"""
Sistema de tracking de rendimiento — Compara resultados reales vs backtest.
Responde: ¿La estrategia está funcionando como se espera?
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Optional

BACKTEST_EXPECTED = {
    "total_return_pct": 20.38,
    "years": 4.5,
    "annual_return_pct": 4.53,    # 20.38 / 4.5
    "monthly_return_pct": 0.38,   # 4.53 / 12
    "weekly_return_pct": 0.09,    # 4.53 / 52
    "win_rate": 43.0,
    "profit_factor": 1.35,
    "max_drawdown_pct": -4.27,
    "trades_per_month": 3.44,     # 186 / 54 meses
    "avg_win_usd": 2.99,
    "avg_loss_usd": -1.0,
    "rr_ratio": 1.8,
}


class PerformanceTracker:
    """
    Rastrea el rendimiento real vs las expectativas del backtest.
    """
    
    def __init__(self, initial_capital: float = 200.0):
        self.initial_capital = initial_capital
        self.trades_file = "logs/trades/executions.jsonl"
        self.report_file = "logs/trades/performance_report.json"
        os.makedirs("logs/trades", exist_ok=True)

    def load_trades(self) -> list:
        """Carga todos los trades registrados."""
        trades = []
        if os.path.exists(self.trades_file):
            with open(self.trades_file) as f:
                for line in f:
                    try:
                        trades.append(json.loads(line))
                    except:
                        pass
        return trades

    def compute_metrics(self) -> dict:
        """Calcula métricas de rendimiento real."""
        trades = self.load_trades()
        
        if not trades:
            return {
                "total_trades": 0,
                "status": "SIN DATOS — Esperando primeras operaciones",
                "days_running": 0,
            }

        # Calcular PnL real de cada trade
        total_pnl = 0.0
        wins = 0
        losses = 0
        win_pnls = []
        loss_pnls = []
        
        for t in trades:
            side = t.get("side", "BUY")
            entry = t.get("entry_price", 0)
            exit_p = t.get("exit_price", 0)
            size = t.get("size", 0)
            
            if exit_p > 0 and entry > 0:
                pnl = (exit_p - entry) * size * (1 if side == "BUY" else -1)
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
                    win_pnls.append(pnl)
                else:
                    losses += 1
                    loss_pnls.append(pnl)

        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0
        gross_profit = sum(win_pnls)
        gross_loss = abs(sum(loss_pnls))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Fecha del primer trade
        first_trade = trades[0].get("timestamp", "")
        days_running = 0
        if first_trade:
            try:
                first = datetime.fromisoformat(first_trade)
                days_running = (datetime.now(timezone.utc) - first).days
            except:
                pass

        current_capital = self.initial_capital + total_pnl
        total_return = (total_pnl / self.initial_capital) * 100

        # Annualizar si hay suficientes datos
        annualized = 0
        if days_running > 0:
            annualized = (current_capital / self.initial_capital) ** (365 / max(days_running, 1)) - 1

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "total_pnl_usd": round(total_pnl, 2),
            "total_return_pct": round(total_return, 2),
            "annualized_return_pct": round(annualized * 100, 2),
            "current_capital": round(current_capital, 2),
            "days_running": days_running,
            "avg_win_usd": round(np.mean(win_pnls), 2) if win_pnls else 0,
            "avg_loss_usd": round(np.mean(loss_pnls), 2) if loss_pnls else 0,
        }

    def compare_with_backtest(self) -> dict:
        """Compara rendimiento real vs lo esperado del backtest."""
        real = self.compute_metrics()
        
        if real.get("total_trades", 0) == 0:
            return {"status": "SIN DATOS", "real": real, "expected": BACKTEST_EXPECTED}
        
        trades_expected = round(BACKTEST_EXPECTED["trades_per_month"] * max(real["days_running"], 1) / 30, 1)
        return_expected = BACKTEST_EXPECTED["annual_return_pct"] * max(real["days_running"], 1) / 365

        comparison = {
            "status": "TRACKING",
            "last_updated": str(datetime.now(timezone.utc)),
            "real": real,
            "expected": {
                "trades_in_period": trades_expected,
                "return_in_period_pct": round(return_expected, 2),
                "win_rate": BACKTEST_EXPECTED["win_rate"],
                "profit_factor": BACKTEST_EXPECTED["profit_factor"],
                "max_drawdown": BACKTEST_EXPECTED["max_drawdown_pct"],
            },
            "veredict": self._evaluate(real, trades_expected, return_expected),
        }
        
        # Guardar reporte
        with open(self.report_file, "w") as f:
            json.dump(comparison, f, indent=2, default=str)
        
        return comparison

    def _evaluate(self, real: dict, expected_trades: float, expected_return: float) -> str:
        """Evalúa si la estrategia va por buen camino."""
        notes = []
        
        if real["total_trades"] >= expected_trades * 0.5:
            notes.append(f"✅ Trades: {real['total_trades']}/{expected_trades:.0f} esperados")
        elif real["total_trades"] > 0:
            notes.append(f"⏳ Trades: {real['total_trades']} (esperando ~{expected_trades:.0f})")
        else:
            notes.append("⏳ Sin trades aún")
        
        if real["total_trades"] >= 5:
            if real["profit_factor"] >= BACKTEST_EXPECTED["profit_factor"]:
                notes.append(f"✅ PF: {real['profit_factor']} (target {BACKTEST_EXPECTED['profit_factor']})")
            elif real["profit_factor"] >= 1.0:
                notes.append(f"⚠️ PF: {real['profit_factor']} (mínimo aceptable 1.0)")
            else:
                notes.append(f"❌ PF: {real['profit_factor']} (DEBE SER > 1.0)")
            
            if real["win_rate_pct"] >= BACKTEST_EXPECTED["win_rate"] * 0.7:
                notes.append(f"✅ WR: {real['win_rate_pct']}% (target {BACKTEST_EXPECTED['win_rate']}%)")
            else:
                notes.append(f"⚠️ WR: {real['win_rate_pct']}% (bajo, esperado {BACKTEST_EXPECTED['win_rate']}%)")
        
        if real["total_return_pct"] >= expected_return * 0.5:
            notes.append(f"✅ Retorno: {real['total_return_pct']:+.2f}%")
        elif real["total_return_pct"] < -5:
            notes.append(f"❌ Retorno: {real['total_return_pct']:+.2f}% (alerta de pérdidas)")
        else:
            notes.append(f"⏳ Retorno: {real['total_return_pct']:+.2f}%")
        
        return " | ".join(notes)

    def generate_telegram_report(self) -> str:
        """Genera mensaje para Telegram con el estado actual."""
        comparison = self.compare_with_backtest()
        
        if comparison["status"] == "SIN DATOS":
            return (
                "<b>📊 TRACKER DE RENDIMIENTO</b>\n\n"
                "⏳ Sin operaciones registradas aún.\n"
                "El tracker empezará a reportar automáticamente\n"
                "cuando se ejecuten las primeras operaciones.\n\n"
                f"<b>Capital inicial:</b> ${self.initial_capital:.2f}\n"
                f"<b>Expectativa:</b> +{BACKTEST_EXPECTED['annual_return_pct']}% anual\n"
                f"<b>Objetivo mensual:</b> +{BACKTEST_EXPECTED['monthly_return_pct']}%"
            )
        
        real = comparison["real"]
        exp = comparison["expected"]
        
        msg = (
            f"<b>📊 TRACKER DE RENDIMIENTO</b>\n\n"
            f"<b>📈 Rendimiento Real vs Esperado:</b>\n"
            f"  Trades: {real['total_trades']} | Esperados: ~{exp['trades_in_period']:.0f}\n"
            f"  Retorno real: {real['total_return_pct']:+.2f}% (esperado: {exp['return_in_period_pct']:+.2f}%)\n"
            f"  Win Rate: {real['win_rate_pct']}% (esperado: {exp['win_rate']}%)\n"
            f"  Profit Factor: {real['profit_factor']} (esperado: {exp['profit_factor']})\n\n"
            f"<b>💰 Capital:</b>\n"
            f"  Inicial: ${self.initial_capital:.2f}\n"
            f"  Actual: ${real['current_capital']:.2f}\n"
            f"  PnL: ${real['total_pnl_usd']:+.2f}\n\n"
            f"<b>📋 Veredicto:</b>\n"
            f"  {comparison['veredict']}"
        )
        return msg


def check_performance(capital: float = 200.0, send_telegram: bool = True):
    """Verifica el rendimiento y opcionalmente envía a Telegram."""
    tracker = PerformanceTracker(initial_capital=capital)
    
    if send_telegram:
        try:
            from notifications import _send_message
            msg = tracker.generate_telegram_report()
            _send_message(msg)
        except Exception as e:
            print(f"Error enviando Telegram: {e}")
    
    comparison = tracker.compare_with_backtest()
    return comparison


if __name__ == "__main__":
    import sys
    capital = float(sys.argv[1]) if len(sys.argv) > 1 else 200.0
    result = check_performance(capital)
    print(json.dumps(result, indent=2, default=str))
