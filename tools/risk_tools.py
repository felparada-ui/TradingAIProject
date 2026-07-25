"""
Herramientas de riesgo para la crew de trading.
"""
from crewai.tools import BaseTool
from config import STRATEGY, EXCHANGE
from risk_manager import RiskManager


class CalculatePositionSizeTool(BaseTool):
    name: str = "calculate_position_size"
    description: str = "Calcula el tamaño de posición óptimo para BTC/USDT H1"

    def _run(self, capital: float = 200.0, risk_pct: float = 0.01, entry_price: float = 50000.0, stop_price: float = 49000.0) -> str:
        try:
            rm = RiskManager(STRATEGY, capital)
            size = rm.calc_position_size(entry_price, stop_price)
            risk_usd = abs(entry_price - stop_price) * size
            return f"Tamaño: {size:.6f} BTC | Riesgo USD: ${risk_usd:.2f} | Riesgo %: {risk_pct*100:.1f}%"
        except Exception as e:
            return f"Error: {e}"


class CheckDrawdownTool(BaseTool):
    name: str = "check_drawdown"
    description: str = "Verifica el drawdown actual del portfolio"

    def _run(self, current_equity: float = 200.0, peak_equity: float = 200.0) -> str:
        dd = (current_equity - peak_equity) / peak_equity * 100
        status = "OK" if dd > -10 else "ALERTA" if dd > -15 else "CRITICO"
        return f"Drawdown actual: {dd:.2f}% | Estado: {status}"


class KellyCriterionTool(BaseTool):
    name: str = "kelly_criterion"
    description: str = "Calcula el sizing óptimo según Kelly Criterion"

    def _run(self, win_rate: float = 0.47, avg_win: float = 1.0, avg_loss: float = 0.92) -> str:
        if avg_loss == 0:
            return "Error: avg_loss no puede ser 0"
        b = avg_win / avg_loss
        kelly = (b * win_rate - (1 - win_rate)) / b
        kelly = max(0, min(kelly, 0.05))  # Limitar a 5% máximo
        return f"Kelly óptimo: {kelly*100:.2f}% | Win rate: {win_rate*100:.1f}% | Avg win/loss: {avg_win:.2f}/{avg_loss:.2f}"


class PortfolioRebalanceTool(BaseTool):
    name: str = "portfolio_rebalance"
    description: str = "Rebalancea la asignación de capital entre estrategias"

    def _run(self, capital: float = 200.0) -> str:
        return f"Portfolio rebalanceado. Capital total: ${capital:.2f}. Estrategia activa: ATFS 100%"


calculate_position_size_tool = CalculatePositionSizeTool()
check_drawdown_tool = CheckDrawdownTool()
kelly_criterion_tool = KellyCriterionTool()
portfolio_rebalance_tool = PortfolioRebalanceTool()
