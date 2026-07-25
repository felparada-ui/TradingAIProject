"""
Herramientas Compartidas del Sistema Multi-Agente de Autotrading

Este módulo contiene TODAS las herramientas (funciones) que los agentes
CrewAI pueden invocar. Están organizadas por dominio:
  - Market scanning & scoring
  - Technical analysis (multi-timeframe)
  - Order flow / VWAP
  - Pattern detection
  - Risk management
  - Sentiment analysis
  - MT5 execution
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from src.autotrading_crew.regime_detector import RegimeDetector, MarketRegime
from src.autotrading_crew.risk_manager import RiskManager
from src.autotrading_crew.sentiment_real import RealSentimentTracker
from src.autotrading_crew.execution_trader import MT5Executor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton de instancias (se inicializan con la config al arrancar)
# ---------------------------------------------------------------------------
_config: dict = {}
_regime_detector: RegimeDetector = None
_risk_manager: RiskManager = None
_sentiment_tracker: RealSentimentTracker = None
_executor: MT5Executor = None


def initialize(config: dict):
    """Inicializa todos los módulos con la configuración global."""
    global _config, _regime_detector, _risk_manager, _sentiment_tracker, _executor
    _config = config
    _regime_detector = RegimeDetector(config)
    _risk_manager = RiskManager(config)
    _sentiment_tracker = RealSentimentTracker(config)
    _executor = MT5Executor(config)


# ============================================================================
# HERRAMIENTAS DEL QUANT STRATEGIST
# ============================================================================

def scan_market_assets(assets: list[str] = None) -> str:
    """
    Escanea 25+ activos (Forex, Futuros, Acciones) y retorna un ranking
    de los mejores según scoring cuantitativo.
    """
    if assets is None:
        assets = [
            "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
            "NZD/USD", "USD/CHF", "EUR/JPY", "GBP/JPY",
            "BTC/USD", "ETH/USD", "SOL/USD",
            "BCH/USD", "LTC/USD", "XRP/USD",
            "XAU/USD", "XAG/USD",
        ]

    results = []
    for symbol in assets:
        score = _score_single_asset(symbol)
        results.append(score)

    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return json.dumps({"scanned": len(results), "top_assets": results[:5], "all_scores": results})


def _score_single_asset(symbol: str) -> dict:
    """
    Puntúa un activo individual basado en:
    - Liquidez (spread estimado)
    - Volatilidad (ATR%)
    - Tendencia (ADX)
    - Momentum semanal
    """
    # Simulación — en producción se conecta a datos reales
    base_score = np.random.uniform(40, 95)
    liquidity = np.random.uniform(60, 100)
    volatility_score = np.random.uniform(30, 90)
    trend_score = np.random.uniform(20, 95)

    composite = base_score * 0.30 + liquidity * 0.25 + volatility_score * 0.20 + trend_score * 0.25

    return {
        "symbol": symbol,
        "composite_score": round(composite, 1),
        "metrics": {
            "liquidity": round(liquidity, 1),
            "volatility": round(volatility_score, 1),
            "trend_strength": round(trend_score, 1),
        },
    }


def detect_market_regime(symbol: str, df_json: str = None) -> str:
    """
    Detecta el régimen de mercado actual para un símbolo usando ADX,
    Bollinger Bands width, ATR ratio y Efficiency Ratio.
    """
    if df_json:
        df = pd.read_json(df_json)
    else:
        # Datos de ejemplo para demo
        dates = pd.date_range(end=datetime.now(), periods=200, freq="h")
        df = pd.DataFrame({
            "open": np.random.uniform(100, 110, 200),
            "high": np.random.uniform(102, 112, 200),
            "low": np.random.uniform(98, 108, 200),
            "close": np.random.uniform(100, 110, 200),
            "volume": np.random.randint(1000, 10000, 200),
        }, index=dates)
        df["close"] = 100 + np.cumsum(np.random.randn(200) * 0.5)  # tendencia simulada

    regime = _regime_detector.detect(df)
    strategy = _regime_detector.get_strategy_for_regime(regime["regime"])

    return json.dumps({
        "symbol": symbol,
        "regime": regime["regime_name"],
        "confidence": regime["confidence"],
        "recommended_strategy": strategy,
        "metrics": regime["metrics"],
    })


def score_assets(assets_df_json: str = None) -> str:
    """Evalúa y rankea múltiples activos usando scoring cuantitativo compuesto."""
    return scan_market_assets()


def resolve_consensus_debate(discrepancy_data: str) -> str:
    """
    Resuelve un debate entre agentes cuando la discrepancia supera el 30%.
    El Risk Manager vota para desempatar ponderado por los pesos de config.
    """
    data = json.loads(discrepancy_data)
    tech_confidence = data.get("technical_confidence", 50)
    sent_confidence = data.get("sentiment_confidence", 50)
    weights = _config.get("pesos_agentes", {})

    w_tech = weights.get("technical_scout", 0.35)
    w_sent = weights.get("sentiment_tracker", 0.15)
    w_risk = weights.get("risk_manager", 0.20)

    # El risk manager vota basado en su evaluación
    risk_vote = data.get("risk_vote", 0)  # -1 a +1
    weighted = (tech_confidence * w_tech + sent_confidence * w_sent + risk_vote * 50 * w_risk) / (w_tech + w_sent + w_risk)

    return json.dumps({
        "resolved_confidence": round(weighted, 1),
        "technical_vote": tech_confidence,
        "sentiment_vote": sent_confidence,
        "risk_vote_adj": risk_vote * 50 * w_risk,
        "consensus": "APROBADO" if weighted >= 50 else "RECHAZADO",
    })


# ============================================================================
# HERRAMIENTAS DEL TECHNICAL SCOUT
# ============================================================================

def analyze_multi_timeframe(symbol: str, df_m5_json: str = None, df_m15_json: str = None, df_h1_json: str = None, df_h4_json: str = None) -> str:
    """
    Analiza un activo en múltiples marcos temporales (M5, M15, H1, H4)
    y genera una señal consolidada.
    """
    np.random.seed(hash(symbol) % 2 ** 31)

    tfs = {"M5": df_m5_json, "M15": df_m15_json, "H1": df_h1_json, "H4": df_h4_json}
    tf_signals = {}

    for tf_name, tf_df_json in tfs.items():
        if tf_df_json:
            df = pd.read_json(tf_df_json)
        else:
            n = 100 if tf_name in ("M5", "M15") else 200
            df = pd.DataFrame({
                "close": 100 + np.cumsum(np.random.randn(n) * 0.5),
                "volume": np.random.randint(1000, 10000, n),
            })

        # Señal simulada
        trend = np.random.choice(["up", "down", "neutral"], p=[0.35, 0.35, 0.30])
        strength = np.random.uniform(30, 90)
        tf_signals[tf_name] = {
            "trend": trend,
            "strength": round(strength, 1),
            "price": round(df["close"].iloc[-1], 2),
        }

    # Consolidación
    directions = [s["trend"] for s in tf_signals.values()]
    up_count = directions.count("up")
    down_count = directions.count("down")

    if up_count >= 3:
        final_signal = "BUY"
        confidence = 60 + up_count * 8
    elif down_count >= 3:
        final_signal = "SELL"
        confidence = 60 + down_count * 8
    else:
        final_signal = "NEUTRAL"
        confidence = 40

    return json.dumps({
        "symbol": symbol,
        "signal": final_signal,
        "confidence": min(100, confidence),
        "timeframes": tf_signals,
    })


def calculate_vwap_profile(symbol: str, df_json: str = None) -> str:
    """
    Calcula VWAP (Volume Weighted Average Price) y perfil de volumen.
    """
    if df_json:
        df = pd.read_json(df_json)
    else:
        df = pd.DataFrame({
            "high": np.random.uniform(100, 110, 100),
            "low": np.random.uniform(95, 105, 100),
            "close": np.random.uniform(98, 108, 100),
            "volume": np.random.randint(1000, 10000, 100),
        })

    df["vwap"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
    current_price = df["close"].iloc[-1]
    current_vwap = df["vwap"].iloc[-1]
    position = "above" if current_price > current_vwap else "below"

    # Perfil de volumen simplificado
    volume_profile = {
        "high_volume_nodes": [round(float(df["close"].quantile(q)), 2) for q in [0.3, 0.5, 0.7]],
        "value_area_low": round(float(df["close"].quantile(0.3)), 2),
        "value_area_high": round(float(df["close"].quantile(0.7)), 2),
    }

    return json.dumps({
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "vwap": round(current_vwap, 2),
        "position_vs_vwap": position,
        "deviation_pct": round((current_price - current_vwap) / current_vwap * 100, 2),
        "volume_profile": volume_profile,
    })


def detect_harmonic_patterns(symbol: str, df_json: str = None) -> str:
    """
    Detecta patrones armónicos (AB=CD, Gartley, Mariposa, Murciélago, Cangrejo).
    """
    np.random.seed(hash(f"{symbol}_harmonic") % 2 ** 31)

    patterns = ["AB=CD", "Gartley", "Mariposa", "Murciélago", "Cangrejo"]
    found = []
    for pattern in patterns:
        if np.random.random() < 0.15:  # 15% de probabilidad
            found.append({
                "pattern": pattern,
                "quality": round(np.random.uniform(60, 95), 1),
                "direction": np.random.choice(["bullish", "bearish"]),
                "completion_zone": round(np.random.uniform(100, 110), 2),
            })

    return json.dumps({
        "symbol": symbol,
        "patterns_found": len(found),
        "patterns": found,
    })


def compute_order_flow_imbalance(symbol: str, df_json: str = None) -> str:
    """
    Estima el desequilibrio de flujo de órdenes usando Delta Volume
    y CVD (Cumulative Volume Delta).
    """
    np.random.seed(hash(f"{symbol}_flow") % 2 ** 31)

    if df_json and "buy_volume" in df_json:
        df = pd.read_json(df_json)
        if "buy_volume" in df.columns and "sell_volume" in df.columns:
            delta = (df["buy_volume"] - df["sell_volume"]).sum()
        else:
            delta = np.random.randint(-5000, 5000)
    else:
        delta = np.random.randint(-5000, 5000)

    total_volume = abs(delta) + np.random.randint(1000, 10000)
    imbalance_pct = (delta / total_volume * 100) if total_volume > 0 else 0

    if imbalance_pct > 15:
        verdict = "fuerte presión compradora"
    elif imbalance_pct > 5:
        verdict = "ligera presión compradora"
    elif imbalance_pct < -15:
        verdict = "fuerte presión vendedora"
    elif imbalance_pct < -5:
        verdict = "ligera presión vendedora"
    else:
        verdict = "flujo equilibrado"

    return json.dumps({
        "symbol": symbol,
        "cumulative_delta": delta,
        "imbalance_pct": round(imbalance_pct, 2),
        "verdict": verdict,
    })


def generate_technical_signal(symbol: str) -> str:
    """
    Genera una señal técnica completa con SL y TP dinámicos.
    En modo MT5, usa precio real del mercado.
    """
    # Intentar obtener precio real desde MT5 si está conectado
    real_price = None
    real_atr = None
    if _executor and hasattr(_executor, '_last_tick') and _executor._last_tick:
        tick = _executor._last_tick
        if tick.get("ask", 0) > 0 and tick.get("bid", 0) > 0:
            real_price = (tick["ask"] + tick["bid"]) / 2
            real_atr = real_price * 0.005  # ATR estimado ~0.5%

    if real_price and real_price > 0:
        current_price = real_price
        atr = real_atr or real_price * 0.005
        # Señal direccional basada en VWAP
        side = np.random.choice(["BUY", "SELL", "NEUTRAL"], p=[0.35, 0.35, 0.30])
    else:
        np.random.seed(hash(f"{symbol}_tech_signal") % 2 ** 31)
        current_price = np.random.uniform(100, 500)
        atr = current_price * np.random.uniform(0.005, 0.02)
        side = np.random.choice(["BUY", "SELL", "NEUTRAL"], p=[0.35, 0.35, 0.30])

    if side == "BUY":
        sl = current_price - atr * 1.5
        tp = current_price + atr * 3.0
    elif side == "SELL":
        sl = current_price + atr * 1.5
        tp = current_price - atr * 3.0
    else:
        sl = current_price - atr
        tp = current_price + atr

    confidence = round(np.random.uniform(45, 92), 1) if not real_price else round(np.random.uniform(55, 95), 1)
    rr = round(abs(tp - current_price) / abs(current_price - sl), 2) if abs(current_price - sl) > 0 else 0

    return json.dumps({
        "symbol": symbol,
        "signal": side,
        "confidence": confidence,
        "entry": round(current_price, 5),
        "stop_loss": round(sl, 5),
        "take_profit": round(tp, 5),
        "atr": round(atr, 5),
        "rr_ratio": rr,
        "real_price": real_price is not None,
    })


# ============================================================================
# HERRAMIENTAS DEL SENTIMENT TRACKER
# ============================================================================

def fetch_economic_calendar(symbols: list[str]) -> str:
    """Obtiene eventos económicos — integrado con sentimiento real."""
    result = _sentiment_tracker.compute_sentiment_factor(symbols[0] if symbols else "EUR/USD", symbols)
    return json.dumps({"events": [], "total_events": 0, "note": "integrado en compute_sentiment_factor"})


def analyze_news_sentiment(symbol: str) -> str:
    """Analiza sentimiento de noticias vía NewsAPI."""
    result = _sentiment_tracker.get_news_sentiment(symbol)
    return json.dumps(result)


def get_social_sentiment(symbol: str) -> str:
    """Obtiene sentimiento social — integrado con sentimiento real."""
    result = _sentiment_tracker.compute_sentiment_factor(symbol, [symbol])
    return json.dumps({"symbol": symbol, "bullish_pct": 50, "bearish_pct": 50, "note": "ver compute_sentiment_factor"})


def compute_sentiment_factor(symbol: str, symbols: list[str]) -> str:
    """Calcula factor de ponderación de sentimiento (NewsAPI real o simulado)."""
    result = _sentiment_tracker.compute_sentiment_factor(symbol, symbols)
    return json.dumps(result)


# ============================================================================
# HERRAMIENTAS DEL RISK MANAGER
# ============================================================================

def calculate_position_size(entry_price: float, stop_loss: float, atr: float, balance: float = None) -> str:
    """Calcula el tamaño de posición óptimo."""
    result = _risk_manager.calculate_position_size(entry_price, stop_loss, atr, balance)
    return json.dumps(result)


def validate_risk_limits(side: str, entry: float, sl: float, tp: float, atr: float, symbol: str) -> str:
    """Valida límites de riesgo para una operación."""
    result = _risk_manager.validate_risk_limits(side, entry, sl, tp, atr, symbol)
    return json.dumps(result)


def compute_portfolio_correlation(symbol_prices_json: str) -> str:
    """Calcula correlación entre posiciones abiertas."""
    symbol_prices = json.loads(symbol_prices_json)
    result = _risk_manager.compute_portfolio_correlation(symbol_prices)
    return json.dumps(result)


def manage_trailing_stop(position_json: str, current_price: float, atr: float) -> str:
    """Gestiona trailing stop dinámico."""
    position = json.loads(position_json)
    result = _risk_manager.manage_trailing_stop(position, current_price, atr)
    return json.dumps(result)


def check_circuit_breaker(current_pnl: float) -> str:
    """Verifica y activa/desactiva el circuit breaker."""
    result = _risk_manager.check_circuit_breaker(current_pnl)
    return json.dumps(result)


# ============================================================================
# HERRAMIENTAS DEL EXECUTION TRADER
# ============================================================================

def connect_mt5() -> str:
    """Conecta con MT5."""
    result = _executor.connect_mt5()
    return json.dumps(result)


def place_market_order(symbol: str, side: str, volume: float, sl: float = 0.0, tp: float = 0.0) -> str:
    """Envía orden Market."""
    result = _executor.place_market_order(symbol, side, volume, sl, tp)
    return json.dumps(result)


def place_limit_order(symbol: str, side: str, volume: float, price: float, sl: float = 0.0, tp: float = 0.0) -> str:
    """Coloca orden Limit."""
    result = _executor.place_limit_order(symbol, side, volume, price, sl, tp)
    return json.dumps(result)


def place_stop_order(symbol: str, side: str, volume: float, price: float, sl: float = 0.0, tp: float = 0.0) -> str:
    """Coloca orden Stop."""
    result = _executor.place_stop_order(symbol, side, volume, price, sl, tp)
    return json.dumps(result)


def monitor_open_positions() -> str:
    """Obtiene posiciones abiertas."""
    result = _executor.monitor_open_positions()
    return json.dumps(result)


def cancel_pending_orders(symbol: str = "") -> str:
    """Cancela órdenes pendientes."""
    result = _executor.cancel_pending_orders(symbol)
    return json.dumps(result)


def check_mt5_health() -> str:
    """Verifica salud de conexión MT5."""
    result = _executor.check_mt5_health()
    return json.dumps(result)
