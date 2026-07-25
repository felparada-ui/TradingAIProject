"""
Sistema Multi-Agente de Autotrading — Orquestador Principal

Arquitectura:
  CrewAI con 5 agentes especializados que operan en un ciclo iterativo
  de 4 fases: Barrido → Análisis Cruzado → Validación → Ejecución.

Modos de operación:
  1. LLM mode (requiere OPENAI_API_KEY en .env)
     → Los agentes CrewAI usan LLM para razonar y decidir
  2. Autonomous mode (sin LLM)
     → Ejecuta herramientas directamente con lógica programática

Uso:
  python src/autotrading_crew/main.py
  python src/autotrading_crew/main.py --mode autonomous
  python src/autotrading_crew/main.py --mode llm --ciclo-minutos 5
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
import yaml

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.autotrading_crew import tools as crew_tools
from src.autotrading_crew.agents import load_agents
from src.autotrading_crew.risk_manager import RiskManager
from src.autotrading_crew.sentiment_tracker import SentimentTracker
from src.autotrading_crew.execution_trader import MT5Executor
from src.autotrading_crew.regime_detector import RegimeDetector

# Telegram (opcional — no rompe si no está configurado)
try:
    from notifications import _send_message
    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False
    def _send_message(text, **kwargs): return False

logger = logging.getLogger(__name__)


# ============================================================================
#  CARGA DE CONFIGURACIÓN
# ============================================================================

def load_config() -> dict:
    """Carga config.yaml e inyecta variables de entorno (MT5, Telegram)."""
    config_path = os.path.join(os.path.dirname(__file__), "config", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Inyectar MT5 desde .env (sobrescribe defaults del YAML)
    if "mt5" not in config:
        config["mt5"] = {}
    mt5_cfg = config["mt5"]
    if os.getenv("MT5_LOGIN"):
        mt5_cfg["login"] = int(os.getenv("MT5_LOGIN"))
    if os.getenv("MT5_PASSWORD"):
        mt5_cfg["password"] = os.getenv("MT5_PASSWORD")
    if os.getenv("MT5_SERVER"):
        mt5_cfg["server"] = os.getenv("MT5_SERVER")

    # Inyectar Telegram desde .env
    if "telegram" not in config:
        config["telegram"] = {}
    tg_cfg = config["telegram"]
    tg_cfg["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_cfg["chat_id"] = os.getenv("TELEGRAM_CHAT_ID", "")

    return config


# ============================================================================
#  MODO AUTÓNOMO (SIN LLM)
# ============================================================================

def run_autonomous_cycle(config: dict, risk_manager: RiskManager):
    """
    Ejecuta un ciclo completo de trading SIN LLM.
    Las herramientas se llaman directamente con lógica programática.
    """
    general = config.get("general", {})
    print(f"\n{'='*60}")
    print(f"  🚀 CICLO AUTÓNOMO — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # ─── FASE 1: BARRIDO ───────────────────────────────────────────────────
    print("\n📡 [FASE 1] Quant Strategist — Escaneando mercado...")
    scan_result = json.loads(crew_tools.scan_market_assets())
    top_symbols = [a["symbol"] for a in scan_result.get("top_assets", [])[:3]]
    print(f"   Top 3 activos: {', '.join(top_symbols)}")

    # Detectar régimen para cada activo top
    regimes = {}
    for symbol in top_symbols:
        regime_data = json.loads(crew_tools.detect_market_regime(symbol))
        regimes[symbol] = regime_data
        print(f"   {symbol:10s} → Régimen: {regime_data['regime']:20s} "
              f"(confianza: {regime_data['confidence']}%) | "
              f"Estrategia: {regime_data['recommended_strategy']}")

    # ─── FASE 2: ANÁLISIS CRUZADO ──────────────────────────────────────────
    print("\n🔬 [FASE 2] Technical Scout + Sentiment Tracker — Analizando...")
    candidates = []
    for symbol in top_symbols:
        # Análisis técnico
        tech_signal = json.loads(crew_tools.generate_technical_signal(symbol))
        vwap = json.loads(crew_tools.calculate_vwap_profile(symbol))
        flow = json.loads(crew_tools.compute_order_flow_imbalance(symbol))

        # Análisis de sentimiento
        sentiment = json.loads(crew_tools.compute_sentiment_factor(symbol, top_symbols))

        # Ajustar confianza técnica con sentimiento
        base_confidence = tech_signal.get("confidence", 50)
        sentiment_adj = sentiment.get("adjustment_pct", 0)
        adjusted_confidence = base_confidence + sentiment_adj
        adjusted_confidence = max(0, min(100, adjusted_confidence))

        candidates.append({
            "symbol": symbol,
            "regime": regimes[symbol]["regime"],
            "signal": tech_signal["signal"],
            "base_confidence": base_confidence,
            "sentiment_adj": sentiment_adj,
            "adjusted_confidence": adjusted_confidence,
            "entry": tech_signal.get("entry", 0),
            "stop_loss": tech_signal.get("stop_loss", 0),
            "take_profit": tech_signal.get("take_profit", 0),
            "atr": tech_signal.get("atr", 0),
            "vwap_position": vwap.get("position_vs_vwap", "unknown"),
            "order_flow": flow.get("verdict", "unknown"),
            "sentiment": sentiment["classification"],
        })

        print(f"   {symbol:10s} → Señal: {tech_signal['signal']:6s} | "
              f"Conf: {base_confidence:.0f}% → {adjusted_confidence:.0f}% "
              f"(sent: {sentiment_adj:+.1f})")

    # ─── DEBATE / CONSENSO ─────────────────────────────────────────────────
    # Verificar si hay discrepancia > 30% entre técnico y sentimiento
    best_candidate = max(candidates, key=lambda c: c["adjusted_confidence"])
    print(f"\n⚖️  Mejor candidato: {best_candidate['symbol']} "
          f"(confianza: {best_candidate['adjusted_confidence']:.1f}%)")

    for c in candidates:
        if abs(c["adjusted_confidence"] - best_candidate["adjusted_confidence"]) > 30:
            print(f"   ⚠️  Discrepancia detectada en {c['symbol']}: "
                  f"{c['adjusted_confidence']:.0f}% vs {best_candidate['adjusted_confidence']:.0f}%")

    # ─── FASE 3: VALIDACIÓN ────────────────────────────────────────────────
    print(f"\n🛡️  [FASE 3] Risk Manager — Validando {best_candidate['symbol']}...")

    if best_candidate["signal"] == "NEUTRAL":
        print("   ⏳ Sin señal clara — saltando validación")
        return

    # Validar límites
    validation = risk_manager.validate_risk_limits(
        side=best_candidate["signal"],
        entry=best_candidate["entry"],
        sl=best_candidate["stop_loss"],
        tp=best_candidate["take_profit"],
        atr=best_candidate["atr"],
        symbol=best_candidate["symbol"],
    )
    print(f"   Validación: {'✅ APROBADA' if validation['approved'] else '❌ RECHAZADA'}")
    if not validation["approved"]:
        for reason in validation.get("reasons", []):
            print(f"      ⚠️  {reason}")
        return

    # Calcular tamaño de posición
    pos_size = risk_manager.calculate_position_size(
        entry_price=best_candidate["entry"],
        stop_loss=best_candidate["stop_loss"],
        atr=best_candidate["atr"],
    )
    if "error" in pos_size:
        print(f"   ❌ Error en tamaño de posición: {pos_size['error']}")
        return

    print(f"   Tamaño: {pos_size['units']} unidades @ ${pos_size['position_value']:.2f}")
    print(f"   Riesgo: {pos_size['risk_pct']:.2f}% del capital")

    # Circuit breaker
    cb = risk_manager.check_circuit_breaker(0)
    if cb["circuit_breaker_active"]:
        print(f"   ❌ Circuit breaker activo: {', '.join(cb['reasons'])}")
        return

    # ─── FASE 4: EJECUCIÓN ─────────────────────────────────────────────────
    print(f"\n⚡ [FASE 4] Execution Trader — Ejecutando orden...")

    exec_result = json.loads(crew_tools.place_market_order(
        symbol=best_candidate["symbol"],
        side=best_candidate["signal"],
        volume=float(pos_size["units"]),
        sl=best_candidate["stop_loss"],
        tp=best_candidate["take_profit"],
    ))

    if exec_result.get("order_sent"):
        print(f"   ✅ Orden ejecutada: ID={exec_result.get('order_id')} | "
              f"Precio=${exec_result.get('price', 0)} | "
              f"Volumen={exec_result.get('volume', 0)}")
        risk_manager.register_trade({
            "symbol": best_candidate["symbol"],
            "side": best_candidate["signal"],
            "entry_price": exec_result.get("price", best_candidate["entry"]),
            "stop_loss": best_candidate["stop_loss"],
            "take_profit": best_candidate["take_profit"],
            "volume": pos_size["units"],
            "timestamp": datetime.now().isoformat(),
        })
    else:
        print(f"   ❌ Orden rechazada: {exec_result.get('error', 'Desconocido')}")

    print(f"\n{'='*60}")
    print(f"  ✅ CICLO COMPLETADO")
    print(f"{'='*60}")


# ============================================================================
#  MODO LLM (CREWAI)
# ============================================================================

def run_llm_cycle(config: dict):
    """
    Ejecuta un ciclo completo usando CrewAI con LLM.
    """
    from crewai import Crew, Process

    print(f"\n{'='*60}")
    print(f"  🧠 CICLO LLM — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY no configurada en .env")
        print("   Usa: --mode autonomous para modo sin LLM")
        return

    agents = load_agents(config)
    print("✅ Agentes cargados:")
    for name, agent in agents.items():
        print(f"  📊 {name:22s}: {agent.role} ({len(agent.tools)} herramientas)")

    # Importar tareas
    from src.autotrading_crew.tasks import (
        create_scan_task,
        create_technical_analysis_task,
        create_sentiment_analysis_task,
        create_risk_validation_task,
        create_execution_task,
        create_monitoring_task,
    )

    # Construir pipeline de tareas
    scan_task = create_scan_task(agents["quant_strategist"])
    tech_task = create_technical_analysis_task(
        agents["technical_scout"],
        "{{ scan_task.output }}"
    )
    sent_task = create_sentiment_analysis_task(
        agents["sentiment_tracker"],
        "{{ scan_task.output }}"
    )
    risk_task = create_risk_validation_task(
        agents["risk_manager"],
        "{{ tech_task.output }}"
    )
    exec_task = create_execution_task(
        agents["execution_trader"],
        "{{ risk_task.output }}"
    )
    monitor_task = create_monitoring_task(agents["execution_trader"])

    crew = Crew(
        agents=list(agents.values()),
        tasks=[scan_task, tech_task, sent_task, risk_task, exec_task, monitor_task],
        process=Process.sequential,
        verbose=True,
    )

    print("\n⚡ Ejecutando crew...")
    result = crew.kickoff()

    print(f"\n{'='*60}")
    print("✅ Ciclo LLM completado")
    try:
        print(result.raw if hasattr(result, 'raw') else result)
    except Exception:
        print(result)
    print(f"{'='*60}")


# ============================================================================
#  MODO LIVE (MT5 REAL + TELEGRAM)
# ============================================================================

def run_live_cycle(config: dict, risk_manager: RiskManager):
    """
    Igual que autonomous pero con MT5 real y notificaciones Telegram.
    """
    executor = MT5Executor(config)

    # ─── Conectar MT5 ───────────────────────────────────────────────────────
    print("\n🔌 Conectando a MetaTrader 5...")
    mt5_result = executor.connect_mt5()

    if not mt5_result.get("connected"):
        err = mt5_result.get("error", "Desconocido")
        msg = f"❌ <b>Autotrading Crew</b>\nError conectando MT5: {err}"
        _send_message(msg)
        print(f"   ❌ {err}")

        # Si no hay MT5, ejecutar en modo simulado igual
        print("   ⚠️  Continuando en modo simulado...")
        crew_tools.initialize(config)
        run_autonomous_cycle(config, risk_manager)
        return

    # Inyectar executor real en tools
    config["_executor"] = executor
    crew_tools._executor = executor

    balance = mt5_result.get("balance", 0)
    server = mt5_result.get("server", "?")
    account = mt5_result.get("account", "?")

    msg = (
        f"🟢 <b>Autotrading Crew iniciado</b>\n"
        f"• Servidor: {server}\n"
        f"• Cuenta: {account}\n"
        f"• Balance: ${balance:.2f}\n"
        f"• Estrategias: Breakout + MeanRev + Momentum\n"
        f"• Ciclo cada: {config.get('general', {}).get('ciclo_segundos', 300)}s"
    )
    _send_message(msg)
    print(f"   ✅ Conectado — ${balance:.2f} en {server}")

    # ─── Ejecutar ciclo autónomo ────────────────────────────────────────────
    run_autonomous_cycle(config, risk_manager)

    # ─── Notificar resultado ────────────────────────────────────────────────
    status = risk_manager.get_status_summary()
    msg = (
        f"📊 <b>Ciclo completado</b>\n"
        f"• Posiciones abiertas: {status['open_positions']}\n"
        f"• PnL diario: ${status['daily_pnl']:.2f}\n"
        f"• PnL total: ${status['total_pnl']:.2f}\n"
        f"• Circuit breaker: {'⚠️ ACTIVO' if status['circuit_breaker'] else '✅ OK'}\n"
        f"• Capital: ${status['capital']:.2f}"
    )
    _send_message(msg)

    # ─── Health check (no critico) ─────────────────────────────────────
    try:
        health = json.loads(crew_tools.check_mt5_health())
        if not health.get("connected", False):
            _send_message(f"[MT5] desconectado — reconexion en proximo ciclo.")
    except Exception as e:
        logger.warning(f"Health check no critico fallo: {e}")


# ============================================================================
#  MODO BACKTEST (SIN LLM, SIN MT5)
# ============================================================================

def run_backtest_mode(config: dict, use_real_data: bool = False):
    """Ejecuta backtest con datos sintéticos o reales (CCXT/CSV)."""
    from src.autotrading_crew.backtest import BacktestSimulator

    sim = BacktestSimulator(config)
    report = sim.run(days=180, use_real_data=use_real_data)


# ============================================================================
#  PUNTO DE ENTRADA PRINCIPAL
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Sistema Multi-Agente de Autotrading (CrewAI)"
    )
    parser.add_argument(
        "--mode",
        choices=["autonomous", "live", "llm", "backtest"],
        default="autonomous",
        help="Modo de operación (default: autonomous, live = MT5 real + Telegram)",
    )
    parser.add_argument(
        "--ciclo-minutos",
        type=int,
        default=5,
        help="Minutos entre ciclos (default: 5)",
    )
    parser.add_argument(
        "--ciclos",
        type=int,
        default=1,
        help="Número de ciclos a ejecutar (default: 1, 0 = infinito)",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Usar datos reales (CCXT/CSV) en lugar de sintéticos (backtest)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Iniciar dashboard Streamlit después del ciclo",
    )
    args = parser.parse_args()

    # Configurar logging
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(f"{log_dir}/autotrading_crew.log"),
            logging.StreamHandler(),
        ],
    )

    # Cargar configuración
    config = load_config()
    crew_tools.initialize(config)

    print(f"""
╔══════════════════════════════════════════════════════════╗
║     SISTEMA MULTI-AGENTE DE AUTOTRADING                 ║
║     Modo: {args.mode:34s}║
║     Ciclos: {str(args.ciclos if args.ciclos > 0 else '∞'):33s}║
║     Intervalo: {f'{args.ciclo_minutos} min':32s}║
╚══════════════════════════════════════════════════════════╝
    """)

    ciclo_count = 0
    while True:
        ciclo_count += 1
        print(f"\n{'#'*60}")
        print(f"  CICLO #{ciclo_count}")
        print(f"{'#'*60}")

        risk_manager = RiskManager(config)

        if args.mode == "autonomous":
            run_autonomous_cycle(config, risk_manager)
        elif args.mode == "live":
            run_live_cycle(config, risk_manager)
        elif args.mode == "llm":
            run_llm_cycle(config)
        elif args.mode == "backtest":
            run_backtest_mode(config, use_real_data=args.real)
            break  # Backtest es una sola ejecución

        if args.ciclos > 0 and ciclo_count >= args.ciclos:
            break

        if args.ciclos == 0 or ciclo_count < args.ciclos:
            wait_minutes = args.ciclo_minutos
            print(f"\n⏳ Esperando {wait_minutes} minuto(s) para el siguiente ciclo...\n")
            time.sleep(wait_minutos * 60)

    if args.dashboard:
        print("\n📊 Iniciando dashboard...")
        os.system("streamlit run src/autotrading_crew/dashboard.py &")


if __name__ == "__main__":
    main()
