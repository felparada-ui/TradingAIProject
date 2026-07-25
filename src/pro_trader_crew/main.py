"""
PRO TRADER CREW — Pipeline multi-estrategia para índices.

3 estrategias → ~3 trades/semana → Notificaciones Telegram
  SPY 1H Trend    (+7.14%, PF 1.77)
  IWM 1H Trend    (+6.61%, PF 1.72)
  SPY 15min ORB   (+3.13%, PF 1.39)
"""

import os, sys, json
from dotenv import load_dotenv
from crewai import Crew, Process
from crewai import Agent
import yaml

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.pro_trader_crew.tasks import (
    scan_spy_trend, scan_iwm_trend, scan_spy_orb,
    execute_index_trade, report_daily_summary, check_system_health,
    create_analysis_task, create_execution_task, create_report_task,
    create_reliability_task, BROKER,
)
from notifications import _send_message


def load_agents():
    config_path = os.path.join(os.path.dirname(__file__), "config/agents.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    agents = {}
    for name, cfg in config.items():
        agent_tools = []
        if name == "master_trader":
            agent_tools = [scan_spy_trend, scan_iwm_trend, scan_spy_orb]
        elif name == "execution_agent":
            agent_tools = [execute_index_trade]
        elif name == "performance_analyst":
            agent_tools = [report_daily_summary]
        elif name == "system_reliability":
            agent_tools = [check_system_health]

        agents[name] = Agent(
            role=cfg["role"], goal=cfg["goal"], backstory=cfg["backstory"],
            verbose=cfg.get("verbose", True),
            allow_delegation=cfg.get("allow_delegation", False),
            tools=agent_tools,
        )
    return agents


def run_pipeline():
    """Ejecuta el pipeline completo sin LLM."""
    CAPITAL = 1024.67

    print(f"\n{'='*60}")
    print(f"  PRO TRADER — Pipeline Multi-Estrategia")
    print(f"  Broker: {BROKER.upper()} | Capital: ${CAPITAL}")
    print(f"  SPY Trend + IWM Trend + SPY ORB")
    print(f"{'='*60}")

    # 1. Escanear las 3 estrategias
    print("\n📡 Escaneando estrategias...")
    results = {}
    for name, scan_fn in [("SPY 1H Trend", scan_spy_trend),
                          ("IWM 1H Trend", scan_iwm_trend),
                          ("SPY 15min ORB", scan_spy_orb)]:
        result = json.loads(scan_fn.run())
        sig = result.get("signal", "NEUTRO")
        price = result.get("price", 0)
        results[name] = result
        print(f"  {name:18s} → {sig:6s} @ ${price}")

    # 2. Ejecutar señales válidas
    print("\n💰 Ejecutando señales...")
    executed = 0
    for name, result in results.items():
        if result.get("signal") != "NEUTRO":
            exec_result = json.loads(execute_index_trade.run(json.dumps(result), CAPITAL))
            print(f"  ✅ {name}: {exec_result.get('side','?')} ${exec_result.get('entry',0)}")
            executed += 1
        else:
            print(f"  ⏳ {name}: Sin señal")

    # 4. Verificar salud del sistema
    print("\n🔧 Verificando salud del sistema...")
    health = {"status": "UNKNOWN", "issues": []}
    try:
        health = json.loads(check_system_health.run())
        print(f"  Estado: {health.get('status', '?')}")
        print(f"  Issues: {len(health.get('issues', []))}")
        for issue in health.get('issues', []):
            print(f"    ⚠️ {issue}")
    except Exception as e:
        print(f"  Error en health check: {e}")

    # 5. Enviar resumen diario
    print("\n📊 Enviando resumen diario...")
    summary = json.loads(report_daily_summary.run())
    print(f"  Trades hoy: {summary.get('trades', 0)} | PnL: ${summary.get('pnl_usd', 0)}")

    print(f"\n{'='*60}")
    print(f"  ✅ Pipeline completado — {executed} operaciones | Sistema: {health.get('status','OK')}")
    print(f"{'='*60}")


def main():
    # Modo autónomo siempre (ejecuta herramientas directamente, sin LLM)
    run_pipeline()


if __name__ == "__main__":
    main()
