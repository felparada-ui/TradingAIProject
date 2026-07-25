"""
Creador de Agentes CrewAI para el Sistema Multi-Agente de Autotrading.

Carga la definición de cada agente desde config/agents.yaml y mapea
las herramientas (tools.py) a cada agente según su rol.
"""

import os
import yaml
from crewai import Agent

from src.autotrading_crew import tools as tools_module


def load_agents(config: dict) -> dict[str, Agent]:
    """
    Carga y construye todos los agentes desde config/agents.yaml.

    Returns:
        dict[str, Agent]: nombre_del_agente -> instancia de CrewAI Agent
    """
    config_path = os.path.join(os.path.dirname(__file__), "config/agents.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        agents_def = yaml.safe_load(f)

    # Mapeo nombre_de_herramienta -> función del módulo tools.py
    tool_map = {
        # Quant Strategist
        "scan_market_assets": tools_module.scan_market_assets,
        "detect_market_regime": tools_module.detect_market_regime,
        "score_assets": tools_module.score_assets,
        "resolve_consensus_debate": tools_module.resolve_consensus_debate,
        # Technical Scout
        "analyze_multi_timeframe": tools_module.analyze_multi_timeframe,
        "calculate_vwap_profile": tools_module.calculate_vwap_profile,
        "detect_harmonic_patterns": tools_module.detect_harmonic_patterns,
        "compute_order_flow_imbalance": tools_module.compute_order_flow_imbalance,
        "generate_technical_signal": tools_module.generate_technical_signal,
        # Sentiment Tracker
        "fetch_economic_calendar": tools_module.fetch_economic_calendar,
        "analyze_news_sentiment": tools_module.analyze_news_sentiment,
        "get_social_sentiment": tools_module.get_social_sentiment,
        "compute_sentiment_factor": tools_module.compute_sentiment_factor,
        # Risk Manager
        "calculate_position_size": tools_module.calculate_position_size,
        "validate_risk_limits": tools_module.validate_risk_limits,
        "compute_portfolio_correlation": tools_module.compute_portfolio_correlation,
        "manage_trailing_stop": tools_module.manage_trailing_stop,
        "check_circuit_breaker": tools_module.check_circuit_breaker,
        # Execution Trader
        "connect_mt5": tools_module.connect_mt5,
        "place_market_order": tools_module.place_market_order,
        "place_limit_order": tools_module.place_limit_order,
        "place_stop_order": tools_module.place_stop_order,
        "monitor_open_positions": tools_module.monitor_open_positions,
        "cancel_pending_orders": tools_module.cancel_pending_orders,
        "check_mt5_health": tools_module.check_mt5_health,
    }

    agents: dict[str, Agent] = {}
    for name, cfg in agents_def.items():
        agent_tools = []
        for tool_name in cfg.get("tools", []):
            tool_fn = tool_map.get(tool_name)
            if tool_fn:
                agent_tools.append(tool_fn)
            else:
                import logging
                logging.getLogger(__name__).warning(
                    f"Herramienta '{tool_name}' no encontrada para agente '{name}'"
                )

        agents[name] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=cfg.get("verbose", True),
            allow_delegation=cfg.get("allow_delegation", False),
            tools=agent_tools,
        )

    return agents
