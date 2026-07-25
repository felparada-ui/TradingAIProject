"""
Strategy Hunter Crew — Busca estrategias ganadoras en múltiples activos.

Agentes:
  1. Data Engineer       → Prepara datos multi-activo
  2. Strategy Searcher   → Grid search masivo de parámetros
  3. Cross-Asset Validator → Valida en BTC, ETH, SOL, etc.
  4. Strategy Curator    → Mantiene portfolio rankeado
  5. Reporter            → Documenta hallazgos
"""

import os, sys
from dotenv import load_dotenv
from crewai import Crew, Process
from crewai import Agent
import yaml

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.strategy_hunter_crew.tasks import (
    fetch_multi_asset_data,
    grid_search_strategy,
    validate_on_multiple_assets,
    get_strategy_portfolio,
    save_to_portfolio,
    create_data_task,
    create_search_task,
    create_validation_task,
    create_curator_task,
    create_reporter_task,
)


def load_agents():
    config_path = os.path.join(os.path.dirname(__file__), "config/agents.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    agents = {}
    for name, cfg in config.items():
        agent_tools = []
        if name == "data_engineer":
            agent_tools = [fetch_multi_asset_data]
        elif name == "strategy_searcher":
            agent_tools = [grid_search_strategy]
        elif name == "cross_asset_validator":
            agent_tools = [validate_on_multiple_assets]
        elif name == "strategy_curator":
            agent_tools = [get_strategy_portfolio, save_to_portfolio]
        elif name == "reporter":
            agent_tools = [get_strategy_portfolio]

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
    print("🎯 STRATEGY HUNTER CREW — Buscando estrategias ganadoras")
    print("=" * 60)

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY no configurada. Ejecutando modo autónomo...")
        print("   (Las herramientas funcionan sin LLM)\n")

    agents = load_agents()
    print("✅ Agentes listos:")
    for name, agent in agents.items():
        print(f"  🎯 {name:22s}: {agent.role}")

    print("\n" + "=" * 60)
    print("Para ejecutar con LLM: python src/strategy_hunter_crew/main.py")
    print("\nO prueba las herramientas directamente:")
    print("  python -c \"from src.strategy_hunter_crew.tasks import *; ...\"")
    print("=" * 60)


def run_discovery():
    """Ejecuta el descubrimiento completo sin LLM."""
    print("🎯 INICIANDO DESCUBRIMIENTO DE ESTRATEGIAS")
    print("=" * 60)

    import json

    # 1. Descargar datos
    print("\n📥 [1] Data Engineer: Descargando datos...")
    for symbol in ["BCH/USDT", "BTC/USDT", "ETH/USDT", "SOL/USDT"]:
        for tf in ["1h", "4h"]:
            result = fetch_multi_asset_data.run(symbol, tf, 2022)
            print(f"    {symbol:10s} {tf}: {result['bars']} velas")

    # 2. Buscar estrategias en BCH
    print("\n🔍 [2] Strategy Searcher: Buscando en BCH/USDT 1H...")
    best_strategies = []
    for st in ["ema_cross", "macd_cross", "bb_breakout", "di_cross"]:
        result = json.loads(grid_search_strategy.run("BCH/USDT", "1h", st, 30))
        if result["top_results"]:
            best = result["top_results"][0]
            best_strategies.append(best)
            print(f"    {st:15s}: Mejor={best['params'][:30]} | Ret={best['return_pct']:+.2f}% | PF={best['profit_factor']}")

    # 3. Validar en multi-activo
    print("\n✅ [3] Cross-Asset Validator: Validando mejores...")
    for s in best_strategies[:3]:
        params = s["params"]
        try:
            result = json.loads(validate_on_multiple_assets.run(params, "BTC/USDT,ETH/USDT,SOL/USDT"))
            if "error" in result:
                print(f"    {params[:30]:30s} | ERROR: {result['error']}")
                continue
            working = [r for r in result.get("results", []) if r.get("works")]
            print(f"    {params[:30]:30s} | Aprobadas en {len(working)}/{len(result.get('results',[]))} activos")
            for r in result.get("results", []):
                if "error" not in r:
                    status = "✅" if r.get("works") else "❌"
                    print(f"      {status} {r['symbol']:10s} | Ret={r.get('return_pct',0):+.2f}% | PF={r.get('profit_factor',0):.2f}")
        except Exception as e:
            print(f"    {params[:30]:30s} | Error: {e}")

    # 4. Guardar portfolio
    print("\n📚 [4] Strategy Curator: Actualizando portfolio...")
    for s in best_strategies:
        score = s["return_pct"] * 0.4 + s["profit_factor"] * 30 + s["win_rate"] * 0.3
        entry = {**s, "score": round(score, 1)}
        save_to_portfolio.run(json.dumps(entry))
    portfolio = json.loads(get_strategy_portfolio.run())
    print(f"    Portfolio ahora tiene {len(portfolio['strategies'])} estrategias")

    # 5. Reporte
    print("\n📊 [5] Reporter: Resumen ejecutivo")
    print("=" * 60)
    print("  🎯 MEJORES ESTRATEGIAS ENCONTRADAS:")
    for i, s in enumerate(portfolio["strategies"][:5], 1):
        print(f"  {i}. {s['params']}")
        print(f"     Retorno: {s['return_pct']:+.2f}% | PF: {s['profit_factor']} | WR: {s['win_rate']}%")
    print("=" * 60)

    # Notificar por Telegram
    try:
        from notifications import _send_message
        msg = "<b>🎯 STRATEGY HUNTER CREW — Reporte</b>\n\n"
        msg += f"<b>Estrategias descubiertas: {len(best_strategies)}</b>\n"
        for s in best_strategies[:3]:
            msg += f"\n✅ {s['params'][:35]}\n   Ret: {s['return_pct']:+.2f}% | PF: {s['profit_factor']} | WR: {s['win_rate']}%"
        msg += f"\n\n<b>Portfolio: {len(portfolio['strategies'])} estrategias</b>"
        _send_message(msg)
        print("📤 Reporte enviado a Telegram")
    except Exception as e:
        pass

    print("\n✅ Descubrimiento completado")


if __name__ == "__main__":
    if "--discover" in sys.argv:
        run_discovery()
    else:
        main()
