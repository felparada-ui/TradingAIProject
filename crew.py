"""
TradingAIProject — CrewAI Master Crew
======================================
Equipo de 6 agentes de IA autónomos que operan 24/7 para optimizar
el sistema de trading algorítmico en BTC/USDT H1 usando ATFS.

Ciclos de trabajo:
  - Horario  : Market Analyst + Risk Manager + Exec Monitor + Orchestrator
  - Diario   : + Strategy Optimizer + ML Engineer
  - Semanal  : Walk-forward completo + reentrenamiento ML
  - Mensual  : Rebalanceo de portfolio de estrategias
"""

import os
from crewai import Agent, Task, Crew, Process

try:
    from crewai.memory import LongTermMemory
    _HAS_LTM = True
except Exception:
    LongTermMemory = None
    _HAS_LTM = False

try:
    from crewai.memory.storage.ltm_sqlite_storage import LTMSQLiteStorage
    _HAS_LTM_STORAGE = True
except Exception:
    LTMSQLiteStorage = None
    _HAS_LTM_STORAGE = False

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# IMPORTAR HERRAMIENTAS PERSONALIZADAS
# (se implementan en tools/ — ver archivos separados)
# ─────────────────────────────────────────────
from tools.market_tools import (
    fetch_ohlcv_tool,
    detect_market_regime_tool,
    fetch_funding_rate_tool,
    fetch_liquidations_tool,
)
from tools.backtest_tools import (
    run_vectorbt_backtest_tool,
    run_walkforward_tool,
    optuna_optimize_tool,
)
from tools.risk_tools import (
    calculate_position_size_tool,
    portfolio_rebalance_tool,
    check_drawdown_tool,
    kelly_criterion_tool,
)
from tools.ml_tools import (
    train_xgboost_filter_tool,
    evaluate_model_tool,
    feature_importance_tool,
)
from tools.github_scanner import scan_github_strategies_tool


# ─────────────────────────────────────────────
# AGENTE 1: MARKET ANALYST
# ─────────────────────────────────────────────
market_analyst = Agent(
    role="Senior Crypto Market Analyst",
    goal=(
        "Monitorear BTC/USDT H1. "
        "Detectar régimen H1/H4, calcular ATR%, verificar ventana operativa. "
        "Generar un Market Regime Report corto para ATFS."
    ),
    backstory=(
        "Eres un ex-analista cuantitativo con 15 años en mercados cripto. "
        "Tu análisis es breve, accionable y centrado en ATFS."
    ),
    tools=[
        fetch_ohlcv_tool,
        detect_market_regime_tool,
        fetch_funding_rate_tool,
        fetch_liquidations_tool,
    ],
    verbose=True,
    memory=False,
    allow_delegation=False,
    max_iter=2,
    llm="openai/gpt-4o-mini",
)

# ─────────────────────────────────────────────
# AGENTE 2: STRATEGY OPTIMIZER
# ─────────────────────────────────────────────
strategy_optimizer = Agent(
    role="Quantitative Strategy Optimizer",
    goal=(
        "Optimizar continuamente los parámetros de las estrategias de trading. "
        "Ejecutar backtests diarios con datos frescos, realizar walk-forward optimization semanal, "
        "proponer ajustes de parámetros y eliminar estrategias con Sharpe < 0.5 en ventanas de 30 días. "
        "Mantener el portfolio de estrategias siempre calibrado al régimen de mercado actual."
    ),
    backstory=(
        "Eres un ingeniero cuantitativo especializado en systematic trading con experiencia en "
        "Citadel y Two Sigma. Has desarrollado sistemas de optimización de estrategias que operan "
        "en producción con capital real. Conoces en profundidad VectorBT, Freqtrade y Optuna. "
        "Tu obsesión es el Profit Factor y el Sharpe fuera de muestra, nunca el in-sample."
    ),
    tools=[
        run_vectorbt_backtest_tool,
        run_walkforward_tool,
        optuna_optimize_tool,
        scan_github_strategies_tool,
    ],
    verbose=True,
    memory=True,
    allow_delegation=False,
    max_iter=10,
    llm="openai/gpt-4o",
)

# ─────────────────────────────────────────────
# AGENTE 3: RISK MANAGER
# ─────────────────────────────────────────────
risk_manager = Agent(
    role="Institutional Risk Manager",
    goal=(
        "Proteger el capital en BTC/USDT H1. "
        "Calcular sizing ATR/Kelly, verificar drawdown diario/total, "
        "activar circuit breakers y validar time stop. "
        "Reporte de riesgo corto y accionable."
    ),
    backstory=(
        "Eres ex-Chief Risk Officer de un fondo de hedge. "
        "Tu foco es preservación del capital y disciplina de riesgo."
    ),
    tools=[
        calculate_position_size_tool,
        check_drawdown_tool,
        kelly_criterion_tool,
        fetch_ohlcv_tool,
    ],
    verbose=True,
    memory=False,
    allow_delegation=False,
    max_iter=2,
    llm="openai/gpt-4o-mini",
)

# ─────────────────────────────────────────────
# AGENTE 4: ML ENGINEER
# ─────────────────────────────────────────────
ml_engineer = Agent(
    role="Senior ML Engineer — Financial Time Series",
    goal=(
        "Desarrollar y mantener el meta-modelo de filtrado de señales de trading. "
        "Reentrenar el modelo XGBoost/LightGBM semanalmente con datos frescos. "
        "Realizar feature engineering automático: técnicos, de microestructura y de sentimiento. "
        "Detectar overfitting y mantener un leaderboard de modelos con métricas out-of-sample. "
        "El objetivo del modelo es filtrar el 30% de señales de peor calidad antes de la ejecución."
    ),
    backstory=(
        "Eres un PhD en Machine Learning aplicado a finanzas, ex-investigador de DeepMind. "
        "Publicas en NeurIPS y ICML. Dominas XGBoost, LightGBM, "
        "Temporal Fusion Transformers y técnicas de validación para datos temporales "
        "(purged k-fold, embargo). Eres paranoico con el overfitting y el data snooping bias."
    ),
    tools=[
        train_xgboost_filter_tool,
        evaluate_model_tool,
        feature_importance_tool,
        run_vectorbt_backtest_tool,
    ],
    verbose=True,
    memory=True,
    allow_delegation=False,
    max_iter=8,
    llm="gpt-4o",
)

# ─────────────────────────────────────────────
# AGENTE 5: EXECUTION MONITOR
# ─────────────────────────────────────────────
execution_monitor = Agent(
    role="Trade Execution Quality Monitor",
    goal=(
        "Supervisar ejecución en BTC/USDT H1. "
        "Medir slippage, latencia, comisiones y estado del exchange. "
        "Reporte breve de calidad de ejecución."
    ),
    backstory=(
        "Eres un experto en market microstructure. "
        "Tu foco es mantener el costo de ejecución bajo control."
    ),
    tools=[
        fetch_ohlcv_tool,
        check_drawdown_tool,
    ],
    verbose=True,
    memory=False,
    allow_delegation=False,
    max_iter=2,
    llm="openai/gpt-4o-mini",
)

# ─────────────────────────────────────────────
# AGENTE 6: ORCHESTRATOR (MANAGER)
# ─────────────────────────────────────────────
orchestrator = Agent(
    role="Trading System Orchestrator",
    goal=(
        "Coordinar la crew para BTC/USDT H1 + ATFS. "
        "Sintetizar reportes y tomar decisiones operativas: "
        "OPERAR_NORMAL, OPERAR_REDUCIDO, PAUSAR_ENTRADAS o STOP_TOTAL. "
        "Si drawdown total > 10%, pausar y alertar."
    ),
    backstory=(
        "Eres el CEO de un quant fund pequeño. "
        "Priorizas preservación del capital, luego consistencia, luego rendimiento."
    ),
    tools=[
        check_drawdown_tool,
        fetch_ohlcv_tool,
        calculate_position_size_tool,
    ],
    verbose=True,
    memory=False,
    allow_delegation=True,
    max_iter=2,
    llm="openai/gpt-4o-mini",
)


# ─────────────────────────────────────────────
# TAREAS — CICLO HORARIO
# ─────────────────────────────────────────────

task_market_analysis = Task(
    description=(
        "Analiza BTC/USDT H1 brevemente: "
        "1. Últimas 200 velas OHLCV. "
        "2. Régimen H1 y H4. "
        "3. ATR% y percentil. "
        "4. Funding y liquidaciones. "
        "5. Anomalías. "
        "6. Ventana operativa H1. "
        "7. Filtro H4 para dirección. "
        "Genera Market Regime Report corto para ATFS."
    ),
    expected_output=(
        "Market Regime Report:\n"
        "- Régimen H1: [TREND_BULL|TREND_BEAR|RANGE|HIGH_VOL]\n"
        "- Régimen H4: [BULLISH|BEARISH|NEUTRAL]\n"
        "- Filtro H4: [PERMITIR_LONGS|PERMITIR_SHORTS|NO_OPERAR]\n"
        "- ATR% actual y percentil\n"
        "- Funding rate actual\n"
        "- Anomalías: [NONE|VOLUME_SPIKE|PRICE_GAP|LIQUIDATION_CASCADE]\n"
        "- Score de condiciones (0-10)\n"
        "- Recomendación: [OPERAR|REDUCIR_SIZE|PAUSAR]"
    ),
    agent=market_analyst,
)

task_risk_assessment = Task(
    description=(
        "Con base en el Market Regime Report para BTC/USDT H1 y ATFS: "
        "1. Calcula sizing ATR/Kelly. "
        "2. Verifica drawdown diario y total. "
        "3. Si DD diario > 3%, modo defensivo. "
        "4. Si DD total > 10%, alerta CRITICA. "
        "5. Confirma trailing stop y time stop. "
        "6. Valida score mínimo ATFS."
    ),
    expected_output=(
        "Risk Assessment Report:\n"
        "- Size recomendado: X% del capital\n"
        "- Drawdown: DD_diario% | DD_total%\n"
        "- Circuit breaker: [NORMAL|DEFENSIVO|ALERTA_CRITICA|STOP]\n"
        "- Trailing stop distancia: X ATR\n"
        "- Time stop restante: X velas\n"
        "- Nivel de riesgo: [BAJO|MEDIO|ALTO|EXTREMO]\n"
        "- Acción: [MANTENER|REDUCIR_SIZE|CERRAR_POSICIONES|PAUSAR]"
    ),
    agent=risk_manager,
    context=[task_market_analysis],
)

task_execution_check = Task(
    description=(
        "Revisa ejecución de los últimos trades en BTC/USDT H1: "
        "1. Slippage promedio. "
        "2. Latencia promedio. "
        "3. Comisiones efectivas. "
        "4. Fills completos/parciales. "
        "5. Estado exchange. "
        "6. Routing maker/taker."
    ),
    expected_output=(
        "Execution Quality Report:\n"
        "- Slippage promedio: X bps\n"
        "- Latencia promedio: X ms\n"
        "- Comisión efectiva: X%\n"
        "- Fills completos/parciales: X/Y\n"
        "- Estado exchange: [OK|DEGRADADO|ERROR]\n"
        "- Routing: [MAKER_PREFERIDO|TAKER_ACEPTABLE|REVISAR]"
    ),
    agent=execution_monitor,
    context=[task_market_analysis],
)

task_orchestrate_hourly = Task(
    description=(
        "Sintetiza reportes para BTC/USDT H1 bajo ATFS. "
        "Decisión operativa: "
        "1. ¿Aceptar señales ATFS? "
        "2. ¿Ajustar tamaño? "
        "3. ¿H4 permite operar? "
        "Si Score < 4 o H4 no alinea, pausar entradas."
    ),
    expected_output=(
        "Hourly Decision Log:\n"
        "- Timestamp UTC: [datetime]\n"
        "- Decisión: [OPERAR_NORMAL|OPERAR_REDUCIDO|PAUSAR_ENTRADAS|STOP_TOTAL]\n"
        "- Estrategia activa: ATFS\n"
        "- Dirección permitida por H4: [LONG|SHORT|NO_OPERAR]\n"
        "- Size aprobado: X% del capital\n"
        "- Razón: [justificación breve]\n"
        "- Intervención humana: [SI|NO]\n"
        "- Próxima revisión: [timestamp]"
    ),
    agent=orchestrator,
    context=[task_market_analysis, task_risk_assessment, task_execution_check],
)


# ─────────────────────────────────────────────
# TAREAS — CICLO DIARIO
# ─────────────────────────────────────────────

task_daily_backtest = Task(
    description=(
        "Backtest diario de ATFS sobre BTC/USDT H1: "
        "1. Agrega velas H1 de hoy. "
        "2. Backtest últimos 30 días. "
        "3. Calcula Sharpe, PF, WR, Max DD. "
        "4. Si PF < 1.0 o Sharpe < 1.0, propón ajustes vía Optuna (50 trials). "
        "5. Ajustes para H4, ADX, SL, trailing. "
        "6. Propón cambios para mañana."
    ),
    expected_output=(
        "Daily Strategy Report:\n"
        "- Performance ATFS (30 días): Sharpe|PF|WR|MaxDD|Retorno\n"
        "- Alertas: [lista si PF<1.0 o Sharpe<1.0]\n"
        "- Parámetros propuestos: ADX|SL|Trailing|TimeStop\n"
        "- Filtro H4: [MANTENER|AJUSTAR|DESACTIVAR]\n"
        "- Acción: [MANTENER|OPTIMIZAR|PAUSAR]"
    ),
    agent=strategy_optimizer,
)

task_ml_daily_eval = Task(
    description=(
        "Evalúa el modelo ML de filtrado de señales ATFS: "
        "1. Compara predicciones vs trades reales. "
        "2. Calcula accuracy, precision, recall. "
        "3. Si accuracy < 52%, marcar para reentrenamiento. "
        "4. Reporta data drift. "
        "5. Propón 3 features nuevas si hay drift."
    ),
    expected_output=(
        "ML Daily Evaluation:\n"
        "- Accuracy hoy: X%\n"
        "- Precision/Recall: X%/X%\n"
        "- Estado: [SALUDABLE|DEGRADADO|REENTRENAR]\n"
        "- Data drift: [SI/NO + descripción]\n"
        "- Nuevas features: [lista o NINGUNA]"
    ),
    agent=ml_engineer,
    context=[task_daily_backtest],
)

task_daily_summary = Task(
    description=(
        "Executive Summary diario BTC/USDT H1 + ATFS: "
        "1. PnL, trades, win rate del día. "
        "2. Resume reportes. "
        "3. Top 3 eventos. "
        "4. Plan mañana con parámetros ATFS. "
        "5. Items para revisión humana. "
        "6. Progreso mensual vs objetivo 1.5-3%."
    ),
    expected_output=(
        "EXECUTIVE SUMMARY DIARIO — {fecha}\n"
        "=" * 35 + "\n"
        "Activo: BTC/USDT H1 | Estrategia: ATFS\n"
        "PnL del dia: +/-X.XX% | Trades: N | Win Rate: X%\n"
        "Profit Factor (30 días): X.XX | Sharpe: X.XX\n"
        "Progreso mensual: X.XX% de objetivo 1.5-3%\n"
        "Mejor trade: [descripcion]\n"
        "Peor trade: [descripcion]\n"
        "Estado del sistema: [VERDE|AMARILLO|ROJO]\n"
        "Plan manana: [parametros ATFS + horario + size]\n"
        "Items para revision humana: [lista o NINGUNO]\n"
        "=" * 35
    ),
    agent=orchestrator,
    context=[task_daily_backtest, task_ml_daily_eval, task_risk_assessment],
)


# ─────────────────────────────────────────────
# CONFIGURACIÓN DE MEMORIA COMPARTIDA
# ─────────────────────────────────────────────

if _HAS_LTM and _HAS_LTM_STORAGE:
    long_term_memory = LongTermMemory(
        storage=LTMSQLiteStorage(db_path="./memory/crew_ltm.db")
    )
else:
    long_term_memory = None


# ─────────────────────────────────────────────
# CREWS INSTANCIADOS
# ─────────────────────────────────────────────

def build_hourly_crew() -> Crew:
    """Crew que se ejecuta cada hora durante la sesion de trading."""
    return Crew(
        agents=[market_analyst, risk_manager, execution_monitor, orchestrator],
        tasks=[
            task_market_analysis,
            task_risk_assessment,
            task_execution_check,
            task_orchestrate_hourly,
        ],
        process=Process.sequential,
        memory=True,
        long_term_memory=long_term_memory,
        verbose=True,
        output_log_file="logs/hourly_crew.log",
    )


def build_daily_crew() -> Crew:
    """Crew que se ejecuta al cierre del dia UTC."""
    return Crew(
        agents=[
            market_analyst,
            strategy_optimizer,
            risk_manager,
            ml_engineer,
            execution_monitor,
            orchestrator,
        ],
        tasks=[
            task_market_analysis,
            task_risk_assessment,
            task_execution_check,
            task_daily_backtest,
            task_ml_daily_eval,
            task_daily_summary,
        ],
        process=Process.hierarchical,
        manager_agent=orchestrator,
        memory=True,
        long_term_memory=long_term_memory,
        verbose=True,
        output_log_file="logs/daily_crew.log",
    )


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TradingAI CrewAI Runner")
    parser.add_argument(
        "--cycle",
        choices=["hourly", "daily"],
        default="hourly",
        help="Ciclo a ejecutar: hourly o daily",
    )
    args = parser.parse_args()

    if args.cycle == "hourly":
        print("\n Iniciando CICLO HORARIO del CrewAI...\n")
        crew = build_hourly_crew()
    else:
        print("\n Iniciando CICLO DIARIO del CrewAI...\n")
        crew = build_daily_crew()

    result = crew.kickoff()
    print("\n" + "=" * 60)
    print("CREW COMPLETADO")
    print("=" * 60)
    print(result)
