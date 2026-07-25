"""
Diagnóstico de Pre-vuelo — Verifica todo antes de operar.

Se ejecuta al inicio del modo live y verifica:
  1. Conexión MT5 y estado de la cuenta
  2. Símbolos disponibles con precio real
  3. Configuración de riesgo
  4. APIs externas (NewsAPI, Telegram)
  5. Estado de la crew (roles cargados)
  6. Posiciones abiertas previas

Genera un "parte médico" completo antes del primer ciclo.
"""

import json
import logging
import os
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


def run_diagnostic(config: dict) -> dict:
    """
    Ejecuta el diagnóstico completo de pre-vuelo.
    Retorna dict con resultados de cada prueba.
    """
    print(f"\n{'='*60}")
    print(f"  🔍 DIAGNÓSTICO DE PRE-VUELO")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    results = {}
    all_ok = True

    # ─── 1. MT5 ──────────────────────────────────────────────────────────
    print("\n1️⃣  MetaTrader 5")
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            account = mt5.account_info()
            if account:
                print(f"   ✅ Conectado: {account.server} | Balance: ${account.balance:.2f}")
                results["mt5"] = {"status": "ok", "server": account.server, "balance": account.balance}
            else:
                print(f"   ⚠️  MT5 inicializado pero sin cuenta")
                results["mt5"] = {"status": "warning", "detail": "sin cuenta"}
        else:
            print(f"   ⚠️  MT5 no disponible — modo simulado")
            results["mt5"] = {"status": "simulated", "detail": "MT5 no disponible"}
    except ImportError:
        print(f"   ⚠️  MetaTrader5 no instalado — modo simulado")
        results["mt5"] = {"status": "simulated", "detail": "no instalado"}

    # ─── 2. Símbolos con precio real ──────────────────────────────────────
    print("\n2️⃣  Símbolos disponibles")
    try:
        import MetaTrader5 as mt5
        symbols_to_check = ["EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "ETHUSD", "XAUUSD"]
        available = 0
        for sym in symbols_to_check:
            mt5.symbol_select(sym, True)
            tick = mt5.symbol_info_tick(sym)
            price = (tick.bid + tick.ask) / 2 if tick and tick.bid > 0 and tick.ask > 0 else 0
            status = "✅" if price > 0 else "⏭️"
            if price > 0:
                available += 1
            print(f"   {status} {sym:10s} → ${price:<10.5f}" if price > 0 else f"   {status} {sym:10s} → sin precio")
        results["symbols"] = {"available": available, "total": len(symbols_to_check)}
        if available == 0:
            all_ok = False
    except Exception:
        print(f"   ⚠️  Sin MT5, no se pueden verificar símbolos")
        results["symbols"] = {"status": "simulated"}

    # ─── 3. Configuración ────────────────────────────────────────────────
    print("\n3️⃣  Configuración")
    general = config.get("general", {})
    riesgo = config.get("riesgo", {})
    capital = general.get("capital_inicial", 0)
    risk_pct = riesgo.get("riesgo_maximo_por_operacion", 0)
    rr_min = riesgo.get("take_profit_minimo_rr", 0)
    max_spread = config.get("mt5", {}).get("max_spread", 0)
    max_ops = general.get("max_operaciones_simultaneas", 0)

    print(f"   ✅ Capital: ${capital:.2f}")
    print(f"   ✅ Riesgo: {risk_pct}% por operación (${capital * risk_pct / 100:.2f})")
    print(f"   ✅ RR mínimo: {rr_min}")
    print(f"   ✅ Spread max: {max_spread} pts")
    print(f"   ✅ Máx operaciones: {max_ops}")
    results["config"] = {"capital": capital, "risk_pct": risk_pct, "rr_min": rr_min}

    # ─── 4. APIs externas ────────────────────────────────────────────────
    print("\n4️⃣  APIs externas")
    from dotenv import load_dotenv
    load_dotenv()

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    news_key = os.getenv("NEWSAPI_KEY", "")
    mt5_login = os.getenv("MT5_LOGIN", "")

    if tg_token and tg_chat:
        print(f"   ✅ Telegram: configurado")
        results["telegram"] = {"status": "ok"}
    else:
        print(f"   ⚠️  Telegram: no configurado (sin notificaciones)")
        results["telegram"] = {"status": "warning"}

    if news_key:
        print(f"   ✅ NewsAPI: configurada")
        results["newsapi"] = {"status": "ok"}
    else:
        print(f"   ⚠️  NewsAPI: no configurada (sentimiento simulado)")
        results["newsapi"] = {"status": "warning"}

    if mt5_login:
        print(f"   ✅ MT5 credenciales: configuradas (Cuenta: {mt5_login})")
        results["mt5_creds"] = {"status": "ok"}
    else:
        print(f"   ❌ MT5 credenciales: NO configuradas")
        results["mt5_creds"] = {"status": "error"}
        all_ok = False

    # ─── 5. Crew ─────────────────────────────────────────────────────────
    print("\n5️⃣  Crew de agentes")
    try:
        agents = load_agents(config)
        print(f"   ✅ {len(agents)} roles cargados:")
        for name, agent in agents.items():
            print(f"      • {name:25s} → {len(agent.tools)} herramientas")
        results["crew"] = {"agents": len(agents), "names": list(agents.keys())}
    except Exception as e:
        # Fallback: leer del YAML directamente
        import yaml
        yaml_path = os.path.join(os.path.dirname(__file__), "config", "agents.yaml")
        with open(yaml_path) as f:
            agents_yaml = yaml.safe_load(f)
        print(f"   ✅ {len(agents_yaml)} roles definidos en YAML:")
        for name, cfg in agents_yaml.items():
            print(f"      • {name:25s} → {len(cfg.get('tools', []))} herramientas")
        results["crew"] = {"agents": len(agents_yaml), "names": list(agents_yaml.keys())}

    # ─── 6. Posiciones abiertas ──────────────────────────────────────────
    print("\n6️⃣  Posiciones abiertas")
    try:
        import MetaTrader5 as mt5
        positions = mt5.positions_get()
        if positions and len(positions) > 0:
            print(f"   ⚠️  {len(positions)} posiciones abiertas encontradas:")
            for p in positions:
                side = "BUY" if p.type == 0 else "SELL"
                print(f"      • {p.symbol:10s} {side:5s} Vol: {p.volume:.2f} PnL: ${p.profit:.2f}")
            results["positions"] = {"count": len(positions), "open": True}
        else:
            print(f"   ✅ Sin posiciones abiertas")
            results["positions"] = {"count": 0, "open": False}
    except Exception:
        print(f"   ⚠️  No se pudieron verificar posiciones")
        results["positions"] = {"status": "unknown"}

    # ─── Resumen ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if all_ok and results.get("symbols", {}).get("available", 0) > 0:
        print(f"  ✅ DIAGNÓSTICO COMPLETADO — Listo para operar")
    else:
        issues = []
        if results.get("symbols", {}).get("available", 1) == 0:
            issues.append("Sin símbolos disponibles")
        if not results.get("mt5_creds", {}).get("status") == "ok":
            issues.append("Credenciales MT5 faltantes")
        print(f"  ⚠️  DIAGNÓSTICO COMPLETADO — {len(issues)} advertencias:")
        for i in issues:
            print(f"      • {i}")
    print(f"{'='*60}")

    return results
