"""
Trading Bot Crew — Ciclo completo con 5 agentes.

Estrategia: EMA 5/13/150 + ADX 22 + TP 1.8 en BCH/USDT 1H
Validada: +20.38% en 4.5 años de datos reales

Agentes:
  1. Market Analyst       → Analiza mercado y backtest
  2. Risk Manager         → VaR, drawdown, sizing
  3. Strategy Developer   → Documenta la estrategia
  4. Backtest Validator   → Valida contra histórico 4.5 años
  5. Performance Monitor  → Monitorea bot en tiempo real
"""

import os
import sys
from dotenv import load_dotenv
from crewai import Crew, Process
from crewai import Agent, Task
import yaml

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.trading_bot_crew.tasks import (
    fetch_and_backtest_ema,
    compute_risk_metrics,
    check_paper_trading_status,
    create_analysis_task,
    create_risk_task,
    create_strategy_task,
    create_backtest_task,
    create_monitor_task,
)


def load_agents_from_yaml():
    config_path = os.path.join(os.path.dirname(__file__), "config/agents.yaml")
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    agents = {}
    for name, cfg in config.items():
        agent_tools = []
        if name == "market_analyst":
            agent_tools = [fetch_and_backtest_ema]
        elif name == "risk_manager":
            agent_tools = [compute_risk_metrics]
        elif name == "backtest_validator":
            agent_tools = [fetch_and_backtest_ema]
        elif name == "performance_monitor":
            agent_tools = [check_paper_trading_status, fetch_and_backtest_ema]

        agents[name] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=cfg.get("verbose", True),
            allow_delegation=cfg.get("allow_delegation", False),
            tools=agent_tools,
        )
    return agents


def main():
    print("🚀 Iniciando Trading Bot Crew — EMA 5/13/150 en BCH/USDT 1H")
    print("=" * 60)

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  ERROR: OPENAI_API_KEY no configurada en .env")
        print("   Agrega tu API key en el archivo .env")
        return

    agents = load_agents_from_yaml()

    print("✅ Agentes cargados:")
    for name, agent in agents.items():
        tools_str = f" ({len(agent.tools)} herramientas)" if agent.tools else ""
        print(f"  📊 {name:22s}: {agent.role}{tools_str}")

    # Crear tareas
    task_analysis = create_analysis_task(agent_obj=agents["market_analyst"])
    task_risk = create_risk_task(agent_obj=agents["risk_manager"])
    task_strategy = create_strategy_task(agent_obj=agents["strategy_developer"])
    task_backtest = create_backtest_task(agent_obj=agents["backtest_validator"])
    task_monitor = create_monitor_task(agent_obj=agents["performance_monitor"])

    crew = Crew(
        agents=list(agents.values()),
        tasks=[task_analysis, task_risk, task_strategy, task_backtest, task_monitor],
        process=Process.sequential,
        verbose=True,
    )

    print("\n" + "=" * 60)
    print("⚡ Ejecutando ciclo de la crew (5 agentes)...")
    print("   1. Market Analyst       → Análisis EMA 5/13/150 + backtest")
    print("   2. Risk Manager         → VaR, drawdown, sizing")
    print("   3. Strategy Developer   → Documentación de estrategia")
    print("   4. Backtest Validator   → Validación vs 4.5 años")
    print("   5. Performance Monitor  → Monitoreo del bot en vivo")
    print("=" * 60)

    result = crew.kickoff()

    print("\n" + "=" * 60)
    print("✅ Ciclo de crew completado")
    try:
        print(result.raw if hasattr(result, 'raw') else result)
    except Exception:
        print(result)
    print("=" * 60)


if __name__ == "__main__":
    main()
