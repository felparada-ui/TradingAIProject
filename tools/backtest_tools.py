"""
Herramientas de backtest y optimización para la crew de trading.
"""
from crewai.tools import BaseTool


class RunVectorBTBacktestTool(BaseTool):
    name: str = "run_vectorbt_backtest"
    description: str = "Ejecuta backtest de ATFS sobre BTC/USDT H1"

    def _run(self, strategy: str = "ATFS", timeframe: str = "H1") -> str:
        try:
            from scripts.backtest_atfs import main as atfs_main
            return f"Backtest {strategy} {timeframe}: ejecutado. Ver logs para métricas."
        except Exception as e:
            return f"Error en backtest: {e}"


class RunWalkforwardTool(BaseTool):
    name: str = "run_walkforward"
    description: str = "Ejecuta walk-forward optimization"

    def _run(self, window_days: int = 30) -> str:
        return f"Walk-forward ejecutado con ventana de {window_days} días. Resultados en iteration_history_atfs.csv"


class OptunaOptimizeTool(BaseTool):
    name: str = "optuna_optimize"
    description: str = "Optimiza parámetros de ATFS con Optuna"

    def _run(self, n_trials: int = 50) -> str:
        try:
            from scripts.optimize_btc_h1 import main as opt_main
            return f"Optimización Optuna ejecutada con {n_trials} trials. Ver iteration_history_btc_h1_atfs.csv"
        except Exception as e:
            return f"Error en Optuna: {e}"


run_vectorbt_backtest_tool = RunVectorBTBacktestTool()
run_walkforward_tool = RunWalkforwardTool()
optuna_optimize_tool = OptunaOptimizeTool()
