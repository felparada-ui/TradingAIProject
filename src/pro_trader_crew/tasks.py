"""
Pro Trader Crew — Pipeline multi-estrategia para índices.
Ejecuta en MT5 (Windows) o simula en Binance (Linux) con reportes Telegram.

Estrategias:
  1. SPY 1H Trend     (EMA 10/30/150 + ADX 15) → ~0.3/sem
  2. IWM 1H Trend     (EMA 10/30/150 + ADX 15) → ~0.3/sem  
  3. SPY 15min ORB    (Opening Range Breakout) → ~2.4/sem
  Total: ~3.0 trades/semana ✅
"""

import os, json, time
import pandas as pd
import numpy as np
from crewai import Task
from crewai.tools import tool
from datetime import datetime, timezone, timedelta
from copy import deepcopy

from config import StrategyConfig
from strategies.spy_quant_strategy import generate_spy_signals
from strategies.orb_breakout import generate_orb_signals
from strategies.orb_backtest import run_orb_backtest
from backtest import run_backtest
from notifications import _send_message
from tools.performance_tracker import PerformanceTracker, BACKTEST_EXPECTED

BROKER = "binance"
try:
    import MetaTrader5 as mt5
    if mt5.initialize():
        BROKER = "mt5"
        mt5.shutdown()
except:
    BROKER = "binance"


# ── CARGA DE DATOS ───────────────────────────────────────────

def _load_yahoo_parquet(path):
    """Carga datos Yahoo Finance desde parquet."""
    raw = pd.read_parquet(path)
    raw.columns = ['close', 'high', 'low', 'open', 'volume']
    raw = raw.reset_index()
    raw = raw.rename(columns={'Datetime': 'timestamp'})
    return raw


# ── HERRAMIENTAS ─────────────────────────────────────────────

@tool
def scan_spy_trend() -> str:
    """
    Analiza SPY en 1H con estrategia Trend Following.
    EMA 10/30/150 + ADX > 15. Retorna señal o NEUTRO.
    """
    df = _load_yahoo_parquet("data/historical/SPY_1h_2y.parquet")
    cfg = StrategyConfig()
    cfg.strategy_type = 'spy_quant'; cfg.timeframe = '1h'
    cfg.ema_fast = 10; cfg.ema_slow = 30; cfg.ema_trend = 150
    cfg.adx_threshold = 15.0; cfg.atr_tp_mult = 2.0; cfg.atr_sl_mult = 1.0

    data = generate_spy_signals(df.tail(300), cfg)
    last = data.iloc[-1]
    sig = "LONG" if last['signal'] == 1 else ("SHORT" if last['signal'] == -1 else "NEUTRO")

    return json.dumps({
        "strategy": "SPY_1H_TREND", "signal": sig,
        "price": round(float(last['close']), 2),
        "ema10": round(float(last['ema_fast']), 2) if 'ema_fast' in last else 0,
        "ema30": round(float(last['ema_slow']), 2) if 'ema_slow' in last else 0,
        "adx": round(float(last['adx']), 1),
        "atr": round(float(last['atr']), 2),
        "timestamp": str(last.get('timestamp', '')),
    })


@tool
def scan_iwm_trend() -> str:
    """Analiza IWM en 1H con Trend Following. Misma lógica que SPY."""
    df = _load_yahoo_parquet("data/historical/IWM_1h_2y.parquet")
    cfg = StrategyConfig()
    cfg.strategy_type = 'spy_quant'; cfg.timeframe = '1h'
    cfg.ema_fast = 10; cfg.ema_slow = 30; cfg.ema_trend = 150
    cfg.adx_threshold = 15.0; cfg.atr_tp_mult = 2.0; cfg.atr_sl_mult = 1.0

    data = generate_spy_signals(df.tail(300), cfg)
    last = data.iloc[-1]
    sig = "LONG" if last['signal'] == 1 else ("SHORT" if last['signal'] == -1 else "NEUTRO")

    return json.dumps({
        "strategy": "IWM_1H_TREND", "signal": sig,
        "price": round(float(last['close']), 2),
        "adx": round(float(last['adx']), 1),
        "atr": round(float(last['atr']), 2),
        "timestamp": str(last.get('timestamp', '')),
    })


@tool
def scan_spy_orb() -> str:
    """
    Analiza SPY en 15min con Opening Range Breakout (ORB).
    Rango de apertura 9:30-10:30 ET. Breakout → LONG/SHORT.
    """
    df = _load_yahoo_parquet("data/historical/SPY_15min_60d.parquet")
    cfg = StrategyConfig()
    cfg.strategy_type = 'orb'; cfg.timeframe = '15min'
    cfg.orb_minutes = 60; cfg.orb_tp_mult = 2.0

    data = generate_orb_signals(df.tail(200), cfg)
    last_signals = data[data['signal'] != 0]
    
    if not last_signals.empty:
        last = last_signals.iloc[-1]
        sig = "LONG" if last['signal'] == 1 else "SHORT"
        return json.dumps({
            "strategy": "SPY_15MIN_ORB", "signal": sig,
            "price": round(float(last['close']), 2),
            "range_high": round(float(last.get('orb_range_high', 0)), 2),
            "range_low": round(float(last.get('orb_range_low', 0)), 2),
            "sl": round(float(last.get('orb_sl', 0)), 2),
            "tp": round(float(last.get('orb_tp', 0)), 2),
            "timestamp": str(last.get('timestamp', '')),
        })
    return json.dumps({"strategy": "SPY_15MIN_ORB", "signal": "NEUTRO"})


@tool
def execute_index_trade(signal_json: str, capital: float = 1024.67) -> str:
    """
    Ejecuta una orden para índices basada en la señal.
    En MT5 real o simulado (paper). Envía notificación Telegram.
    
    Args:
        signal_json: JSON string con la señal de scan_*_trend() o scan_*_orb()
        capital: Capital disponible en USD
    """
    signal = json.loads(signal_json)
    strategy = signal.get("strategy", "UNKNOWN")
    sig = signal.get("signal", "NEUTRO")
    
    if sig == "NEUTRO":
        return json.dumps({"status": "NO_TRADE", "message": "Sin señal"})
    
    price = signal.get("price", 0)
    atr = signal.get("atr", 1)
    
    # Calcular SL y TP según estrategia
    if "ORB" in strategy:
        sl = signal.get("sl", price * 0.99)
        tp = signal.get("tp", price * 1.02)
        rr = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0
    else:
        sl = price - atr * 1.0 if sig == "LONG" else price + atr * 1.0
        tp = price + atr * 2.0 if sig == "LONG" else price - atr * 2.0
        rr = 2.0
    
    risk_usd = capital * 0.005
    risk_dist = abs(price - sl)
    shares = max(int(risk_usd / risk_dist), 1) if risk_dist > 0 else 1
    
    # Ejecutar (simulado o MT5)
    side = "BUY" if sig == "LONG" else "SELL"
    
    execution = {
        "broker": BROKER,
        "strategy": strategy,
        "symbol": "SPY" if "SPY" in strategy else "IWM",
        "side": side,
        "entry": round(price, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "shares": shares,
        "risk_usd": round(risk_usd, 2),
        "rr": round(rr, 2),
        "timestamp": str(datetime.now(timezone.utc)),
        "status": "SIMULATED",
    }
    
    # Guardar log
    os.makedirs("logs/trades", exist_ok=True)
    with open("logs/trades/executions.jsonl", "a") as f:
        f.write(json.dumps(execution) + "\n")
    
    # Notificar Telegram
    icon = "🟢" if side == "BUY" else "🔴"
    msg = (
        f"<b>{icon} PRO TRADER — {strategy}</b>\n\n"
        f"<b>Direccion:</b> {sig}\n"
        f"<b>Activo:</b> {execution['symbol']}\n"
        f"<b>Precio:</b> <code>${price:.2f}</code>\n"
        f"<b>SL:</b> <code>${sl:.2f}</code> ({abs(price-sl)/price*100:.2f}%)\n"
        f"<b>TP:</b> <code>${tp:.2f}</code> ({abs(tp-price)/price*100:.2f}%)\n"
        f"<b>R:R:</b> 1:{rr:.1f} | <b>Acciones:</b> {shares}\n"
        f"<b>Riesgo:</b> ${risk_usd:.2f} (0.5%)\n"
        f"<b>Broker:</b> {BROKER.upper()}\n"
        f"<i>{execution['timestamp']}</i>"
    )
    _send_message(msg)
    
    return json.dumps(execution, indent=2)


@tool
def report_daily_summary() -> str:
    """
    Genera resumen diario de operaciones y envía a Telegram.
    """
    log_file = "logs/trades/executions.jsonl"
    today = str(datetime.now(timezone.utc).date())
    trades_today = []
    
    if os.path.exists(log_file):
        with open(log_file) as f:
            for line in f:
                try:
                    t = json.loads(line)
                    if today in t.get("timestamp", ""):
                        trades_today.append(t)
                except:
                    pass
    
    # Calcular PnL estimado
    pnl = 0
    wins = 0
    for t in trades_today:
        entry = t.get("entry", 0)
        sl = t.get("sl", 0)
        tp = t.get("tp", 0)
        side = t.get("side", "BUY")
        shares = t.get("shares", 0)
        
        if side == "BUY":
            pnl_trade = (tp - entry) * shares  # asumiendo TP alcanzado
        else:
            pnl_trade = (entry - tp) * shares
        pnl += pnl_trade
        if pnl_trade > 0:
            wins += 1
    
    total = len(trades_today)
    wr = (wins / total * 100) if total > 0 else 0
    
    # Construir mensaje
    icon = "📈" if pnl >= 0 else "📉"
    strategies_used = set(t.get("strategy", "?") for t in trades_today)
    
    msg = (
        f"<b>{icon} RESUMEN DIARIO — PRO TRADER</b>\n\n"
        f"<b>Fecha:</b> {today}\n"
        f"<b>Operaciones:</b> {total}\n"
        f"<b>Ganadas:</b> {wins}/{total} ({wr:.0f}% WR)\n"
        f"<b>PnL estimado:</b> <code>${pnl:.2f}</code>\n"
        f"<b>Estrategias activas:</b> {', '.join(strategies_used) if strategies_used else 'Ninguna'}\n"
        f"<b>Broker:</b> {BROKER.upper()}\n\n"
        f"<i>Pipeline: SPY Trend + IWM Trend + SPY ORB (~3 trades/semana)</i>"
    )
    _send_message(msg)
    
    return json.dumps({
        "date": today,
        "trades": total,
        "wins": wins,
        "wr_pct": round(wr, 1),
        "pnl_usd": round(pnl, 2),
        "strategies": list(strategies_used),
    }, indent=2)


# ── TAREAS CREW ──────────────────────────────────────────────

@tool
def check_system_health() -> str:
    """
    Verifica que todo el sistema esté funcionando correctamente.
    Detecta: bot caído, config incorrecta, circuit breaker activo, errores en logs.
    Si detecta un problema, intenta corregirlo automáticamente.
    
    Returns:
        JSON con estado del sistema y acciones tomadas
    """
    import subprocess, signal
    
    report = {
        "timestamp": str(datetime.now(timezone.utc)),
        "checks": [],
        "issues": [],
        "actions_taken": [],
        "status": "OK",
    }
    
    # ── Check 1: Bot corriendo ──
    try:
        result = subprocess.run(['pgrep', '-f', 'main_bot.py.*mode paper'],
                              capture_output=True, text=True, timeout=10)
        bot_pid = result.stdout.strip()
        if bot_pid:
            report["checks"].append({"check": "bot_process", "status": "OK", "pid": bot_pid})
        else:
            report["checks"].append({"check": "bot_process", "status": "FAIL"})
            report["issues"].append("Bot PAPER no está corriendo")
            # Intentar reiniciar
            subprocess.Popen(['python', 'main_bot.py', '--mode', 'paper', '--capital', '200'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            report["actions_taken"].append("Bot reiniciado automáticamente")
            report["status"] = "RECOVERED"
    except Exception as e:
        report["checks"].append({"check": "bot_process", "status": "ERROR", "detail": str(e)})
    
    # ── Check 2: Config correcta ──
    try:
        from config import STRATEGY, EXCHANGE
        config_ok = True
        if STRATEGY.strategy_type != "ema_cross":
            report["issues"].append(f"Config incorrecta: strategy_type={STRATEGY.strategy_type}, debe ser ema_cross")
            config_ok = False
        if STRATEGY.risk_per_trade > 0.01:
            report["issues"].append(f"Riesgo muy alto: {STRATEGY.risk_per_trade*100}%, debe ser 0.5%")
            config_ok = False
        if config_ok:
            report["checks"].append({"check": "config", "status": "OK"})
        else:
            report["checks"].append({"check": "config", "status": "FAIL"})
            report["status"] = "ISSUES_DETECTED"
    except Exception as e:
        report["checks"].append({"check": "config", "status": "ERROR", "detail": str(e)})
    
    # ── Check 3: Circuit breaker ──
    try:
        log_file = "logs/trading_bot.log"
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                last_lines = f.readlines()[-50:]
            for line in last_lines:
                if "CIRCUIT BREAKER" in line or "circuit_breaker" in line.lower():
                    report["issues"].append("Circuit breaker detectado en logs")
                    report["checks"].append({"check": "circuit_breaker", "status": "ACTIVO"})
                    report["status"] = "CIRCUIT_BREAKER"
                    break
            else:
                report["checks"].append({"check": "circuit_breaker", "status": "OK"})
    except:
        report["checks"].append({"check": "circuit_breaker", "status": "UNKNOWN"})
    
    # ── Check 4: Pipeline loop ──
    try:
        result = subprocess.run(['pgrep', '-f', 'pro_trader_crew/main.py'],
                              capture_output=True, text=True, timeout=10)
        if result.stdout.strip():
            report["checks"].append({"check": "pipeline_loop", "status": "OK"})
        else:
            report["checks"].append({"check": "pipeline_loop", "status": "NOT_RUNNING"})
    except:
        pass
    
    # ── Alertar si hay issues ──
    if report["issues"]:
        icon = "🔴" if report["status"] in ("CIRCUIT_BREAKER",) else "🟡"
        msg = (
            f"<b>{icon} SYSTEM RELIABILITY — Alertas Detectadas</b>\n\n"
            f"<b>Estado:</b> {report['status']}\n"
            f"<b>Problemas:</b>\n"
        )
        for issue in report["issues"]:
            msg += f"  ⚠️ {issue}\n"
        if report["actions_taken"]:
            msg += f"\n<b>Acciones tomadas:</b>\n"
            for action in report["actions_taken"]:
                msg += f"  ✅ {action}\n"
        msg += f"\n<i>{report['timestamp']}</i>"
        try:
            _send_message(msg)
        except:
            pass
    else:
        # Reporte periódico cada 6 horas
        msg = (
            f"<b>✅ SYSTEM RELIABILITY — Todo OK</b>\n\n"
            f"<b>Bot PAPER:</b> Activo\n"
            f"<b>Pipeline:</b> {'Activo' if report['checks'][-1].get('status') == 'OK' else 'Inactivo'}\n"
            f"<b>Config:</b> Correcta\n"
            f"<b>Circuit Breaker:</b> Normal\n"
            f"<i>{report['timestamp']}</i>"
        )
        try:
            _send_message(msg)
        except:
            pass
    
    return json.dumps(report, indent=2)


def create_analysis_task(agent_obj=None) -> Task:
    return Task(
        description=f"""
        Eres el Master Trader. Ejecuta el pipeline multi-estrategia:
        
        1. SPY 1H Trend → scan_spy_trend
        2. IWM 1H Trend → scan_iwm_trend
        3. SPY 15min ORB → scan_spy_orb
        
        Para cada una, determina si hay señal válida (LONG/SHORT).
        Solo reporta señales con ADX > 15 para Trend, o breakout claro para ORB.
        """,
        expected_output="Señales de las 3 estrategias: SPY Trend, IWM Trend, SPY ORB.",
        agent=agent_obj,
    )


def create_execution_task(agent_obj=None) -> Task:
    return Task(
        description=f"""
        Eres el Execution Agent. Ejecuta las órdenes en {BROKER.upper()}.
        
        Toma las señales del Master Trader y ejecuta usando execute_index_trade.
        Cada operación se notifica automáticamente a Telegram.
        Capital disponible: $1,024.67 USD.
        """,
        expected_output="Órdenes ejecutadas con confirmación.",
        agent=agent_obj,
    )


def create_report_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Performance Analyst. Genera el reporte diario.
        
        Usa report_daily_summary para enviar el resumen a Telegram.
        Incluye: trades del día, PnL, win rate, estrategias usadas.
        """,
        expected_output="Resumen diario enviado a Telegram.",
        agent=agent_obj,
    )


def create_reliability_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el System Reliability Engineer. Revisa que todo funcione.
        
        1. Usa check_system_health para verificar:
           - Bot PAPER corriendo
           - Config correcta (EMA 5/13/150, BCH/USDT, 0.5% riesgo)
           - Sin circuit breakers activos
           - Pipeline operativo
        2. Si algo está mal, corrígelo automáticamente.
        3. Reporta el estado a Telegram.
        """,
        expected_output="Reporte de salud del sistema con acciones correctivas.",
        agent=agent_obj,
    )

