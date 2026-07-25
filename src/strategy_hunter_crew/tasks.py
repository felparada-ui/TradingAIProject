"""
Strategy Hunter Crew — Herramientas y tareas.
Busca estrategias ganadoras en múltiples activos y timeframes.
"""

import os, json, ccxt, time
import pandas as pd
import numpy as np
from crewai import Task
from crewai.tools import tool
from copy import deepcopy

from config import StrategyConfig
from backtest import run_backtest


# ── ACTIVOS DISPONIBLES PARA BUSQUEDA ──
ASSETS = {
    "BCH/USDT": {"name": "Bitcoin Cash", "symbol": "BCH/USDT", "active": True},
    "BTC/USDT": {"name": "Bitcoin", "symbol": "BTC/USDT", "active": True},
    "ETH/USDT": {"name": "Ethereum", "symbol": "ETH/USDT", "active": True},
    "SOL/USDT": {"name": "Solana", "symbol": "SOL/USDT", "active": True},
    "LINK/USDT": {"name": "Chainlink", "symbol": "LINK/USDT", "active": True},
    "ADA/USDT": {"name": "Cardano", "symbol": "ADA/USDT", "active": True},
    "DOT/USDT": {"name": "Polkadot", "symbol": "DOT/USDT", "active": True},
    "AVAX/USDT": {"name": "Avalanche", "symbol": "AVAX/USDT", "active": True},
}

TIMEFRAMES = ["1h", "4h"]
STRATEGY_TYPES = ["ema_cross", "macd_cross", "rsi_reversal", "bb_breakout", "di_cross", "donchian_breakout"]


# ── HERRAMIENTAS ─────────────────────────────────────────────

@tool
def fetch_multi_asset_data(symbol: str = "BCH/USDT", timeframe: str = "1h", since_year: int = 2022) -> dict:
    """
    Descarga datos OHLCV históricos de un activo desde el año indicado.
    
    Args:
        symbol: Par de trading (ej: 'BCH/USDT')
        timeframe: Timeframe ('1h', '4h')
        since_year: Año de inicio (ej: 2022)
    
    Returns:
        Dict con info de la descarga
    """
    ex = ccxt.binance({"enableRateLimit": True})
    since = ex.parse8601(f"{since_year}-01-01T00:00:00Z")
    all_bars = []
    
    while True:
        try:
            bars = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
            if not bars:
                break
            all_bars.extend(bars)
            since = bars[-1][0] + 3600000
            time.sleep(0.3)
            if len(bars) < 1000:
                break
        except Exception as e:
            break
    
    df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    path = f"data/historical/{symbol.replace('/', '_')}_{timeframe}_{since_year}.parquet"
    df.to_parquet(path)
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": len(df),
        "from": str(df["timestamp"].min()),
        "to": str(df["timestamp"].max()),
        "file": path,
    }


@tool
def grid_search_strategy(symbol: str = "BCH/USDT", timeframe: str = "1h", 
                          strategy_type: str = "ema_cross", max_combinations: int = 50) -> str:
    """
    Ejecuta una búsqueda grid de parámetros para un tipo de estrategia.
    Prueba múltiples combinaciones y retorna las mejores.
    
    Args:
        symbol: Par de trading
        timeframe: Timeframe
        strategy_type: Tipo de estrategia (ema_cross, macd_cross, etc.)
        max_combinations: Máximo de combinaciones a probar
    
    Returns:
        String con JSON de resultados
    """
    # Cargar datos
    safe_symbol = symbol.replace("/", "_")
    path = f"data/historical/{safe_symbol}_{timeframe}_2022.parquet"
    if not os.path.exists(path):
        return f"ERROR: Datos no encontrados para {symbol} {timeframe}. Ejecuta fetch_multi_asset_data primero."
    df = pd.read_parquet(path)
    
    base = StrategyConfig()
    base.session_hours_utc = list(range(0, 24))
    base.trading_days = [0, 1, 2, 3, 4]
    base.atr_sl_mult = 1.0
    base.use_trailing_stop = False
    base.risk_per_trade = 0.005
    
    results = []
    tested = 0
    
    if strategy_type == "ema_cross":
        for ema_fast, ema_slow in [(5, 13), (9, 21), (10, 30), (13, 26), (20, 50)]:
            for ema_trend in [100, 150, 200]:
                for adx_th in [15, 18, 20, 22]:
                    for tp_mult in [1.8, 2.0, 2.5]:
                        if tested >= max_combinations:
                            break
                        cfg = deepcopy(base)
                        cfg.strategy_type = "ema_cross"
                        cfg.timeframe = timeframe
                        cfg.ema_fast = ema_fast; cfg.ema_slow = ema_slow; cfg.ema_trend = ema_trend
                        cfg.adx_threshold = float(adx_th); cfg.atr_tp_mult = tp_mult
                        trades, _, metrics = run_backtest(df, cfg, initial_capital=200.0)
                        if "error" not in metrics:
                            results.append({
                                "params": f"EMA {ema_fast}/{ema_slow}/{ema_trend} ADX {adx_th} TP {tp_mult}",
                                "trades": metrics["total_trades"],
                                "win_rate": round(metrics["win_rate_pct"], 1),
                                "profit_factor": round(metrics["profit_factor"], 2),
                                "return_pct": round(metrics["total_return_pct"], 2),
                                "drawdown": round(metrics["max_drawdown_pct"], 2),
                                "equity": round(metrics["final_equity"], 2),
                            })
                        tested += 1
    
    elif strategy_type == "macd_cross":
        for macd_fast, macd_slow, macd_sig in [(8, 21, 7), (12, 26, 9), (14, 30, 12)]:
            for adx_th in [10, 15, 20]:
                for tp_mult in [2.0, 2.5, 3.0]:
                    if tested >= max_combinations:
                        break
                    cfg = deepcopy(base)
                    cfg.strategy_type = "macd_cross"
                    cfg.timeframe = timeframe
                    cfg.macd_fast = macd_fast; cfg.macd_slow = macd_slow; cfg.macd_signal = macd_sig
                    cfg.adx_threshold = float(adx_th); cfg.atr_tp_mult = tp_mult
                    trades, _, metrics = run_backtest(df, cfg, initial_capital=200.0)
                    if "error" not in metrics:
                        results.append({
                            "params": f"MACD({macd_fast},{macd_slow},{macd_sig}) ADX {adx_th} TP {tp_mult}",
                            "trades": metrics["total_trades"],
                            "win_rate": round(metrics["win_rate_pct"], 1),
                            "profit_factor": round(metrics["profit_factor"], 2),
                            "return_pct": round(metrics["total_return_pct"], 2),
                            "drawdown": round(metrics["max_drawdown_pct"], 2),
                            "equity": round(metrics["final_equity"], 2),
                        })
                    tested += 1
    
    results.sort(key=lambda x: x["return_pct"], reverse=True)
    top10 = results[:10]
    
    # Guardar resultados
    output = {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy_type": strategy_type,
        "tested": tested,
        "top_results": top10,
    }
    
    out_path = f"data/backtest_results/hunt_{safe_symbol}_{timeframe}_{strategy_type}.json"
    os.makedirs("data/backtest_results", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    return json.dumps(output, indent=2, default=str)


@tool
def validate_on_multiple_assets(strategy_params: str, symbol_list: str = "BTC/USDT,ETH/USDT,SOL/USDT") -> str:
    """
    Valida una configuracion de estrategia en múltiples activos.
    
    Args:
        strategy_params: String con params, ej: "EMA 5/13/150 ADX 22 TP 1.8"
        symbol_list: Comma-separated symbols to test
    
    Returns:
        JSON con resultados por activo
    """
    import re
    match = re.search(r'EMA\s+(\d+)/(\d+)/(\d+)\s+ADX\s+(\d+(?:\.\d+)?)\s+TP\s+(\d+(?:\.\d+)?)', strategy_params)
    if not match:
        return json.dumps({"error": f"No se pudo parsear: {strategy_params}"})
    
    ema_fast, ema_slow, ema_trend = int(match.group(1)), int(match.group(2)), int(match.group(3))
    adx_th, tp_mult = float(match.group(4)), float(match.group(5))
    
    symbols = [s.strip() for s in symbol_list.split(",")]
    results = []
    
    for symbol in symbols:
        safe = symbol.replace("/", "_")
        path = f"data/historical/{safe}_1h_2022.parquet"
        if not os.path.exists(path):
            results.append({"symbol": symbol, "error": "Datos no disponibles"})
            continue
        
        df = pd.read_parquet(path)
        cfg = StrategyConfig()
        cfg.strategy_type = "ema_cross"; cfg.timeframe = "1h"
        cfg.ema_fast = ema_fast; cfg.ema_slow = ema_slow; cfg.ema_trend = ema_trend
        cfg.adx_threshold = adx_th; cfg.atr_tp_mult = tp_mult
        cfg.session_hours_utc = list(range(0, 24))
        cfg.trading_days = [0, 1, 2, 3, 4]
        cfg.atr_sl_mult = 1.0; cfg.use_trailing_stop = False; cfg.risk_per_trade = 0.005
        
        trades, _, metrics = run_backtest(df, cfg, initial_capital=200.0)
        if "error" not in metrics:
            ret = float(metrics["total_return_pct"])
            results.append({
                "symbol": symbol,
                "trades": int(metrics["total_trades"]),
                "win_rate": float(round(metrics["win_rate_pct"], 1)),
                "profit_factor": float(round(metrics["profit_factor"], 2)),
                "return_pct": float(round(metrics["total_return_pct"], 2)),
                "drawdown": float(round(metrics["max_drawdown_pct"], 2)),
                "equity": float(round(metrics["final_equity"], 2)),
                "works": bool(ret > 0),
            })
    
    return json.dumps({"strategy": strategy_params, "results": results}, indent=2, default=str)


@tool
def get_strategy_portfolio() -> str:
    """
    Retorna el portfolio actual de estrategias descubiertas y rankeadas.
    """
    portfolio_path = "data/backtest_results/strategy_portfolio.json"
    if os.path.exists(portfolio_path):
        with open(portfolio_path) as f:
            return json.dumps(json.load(f), indent=2)
    return json.dumps({"strategies": [], "message": "Portfolio vacio. Ejecuta búsquedas primero."})


@tool
def save_to_portfolio(strategy_json: str) -> str:
    """
    Guarda una estrategia validada en el portfolio.
    
    Args:
        strategy_json: JSON string con la estrategia y sus métricas
    """
    data = json.loads(strategy_json)
    portfolio_path = "data/backtest_results/strategy_portfolio.json"
    
    portfolio = {"strategies": []}
    if os.path.exists(portfolio_path):
        with open(portfolio_path) as f:
            portfolio = json.load(f)
    
    portfolio["strategies"].append(data)
    portfolio["strategies"].sort(key=lambda x: x.get("score", 0), reverse=True)
    
    with open(portfolio_path, "w") as f:
        json.dump(portfolio, f, indent=2, default=str)
    
    return f"✅ Estrategia guardada. Portfolio ahora tiene {len(portfolio['strategies'])} estrategias."


# ── TAREAS ───────────────────────────────────────────────────

def create_data_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Data Engineer. Prepara los datos para la búsqueda de estrategias.
        
        1. Descarga datos de BCH/USDT, BTC/USDT, ETH/USDT, SOL/USDT en 1h desde 2022.
        2. Descarga también en 4h para cada activo.
        3. Usa fetch_multi_asset_data para cada combinación.
        4. Reporta cuántos datos están disponibles.
        """,
        expected_output="Reporte de datos descargados para todos los activos y timeframes.",
        agent=agent_obj,
    )


def create_search_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Strategy Searcher. Busca estrategias ganadoras.
        
        1. Para BCH/USDT 1H, ejecuta grid_search_strategy con cada tipo: ema_cross, macd_cross, rsi_reversal, bb_breakout, di_cross, donchian_breakout.
        2. Encuentra las 3 mejores configuraciones de cada tipo.
        3. Prioriza estrategias con Profit Factor > 1.2 y retorno positivo.
        4. Reporta los hallazgos.
        """,
        expected_output="Reporte con las mejores estrategias encontradas en BCH/USDT 1H.",
        agent=agent_obj,
    )


def create_validation_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Cross-Asset Validator. Valida estrategias en múltiples activos.
        
        1. Toma las estrategias encontradas por el Strategy Searcher.
        2. Usa validate_on_multiple_assets para probarlas en BTC, ETH, SOL.
        3. Solo aprueba estrategias que den retorno positivo en al menos 2 de 3 activos.
        4. Reporta cuáles pasan el filtro.
        """,
        expected_output="Reporte de validación multi-activo con estrategias aprobadas.",
        agent=agent_obj,
    )


def create_curator_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Strategy Curator. Mantén el portfolio actualizado.
        
        1. Usa get_strategy_portfolio para ver las estrategias existentes.
        2. Con las nuevas estrategias validadas, calcula un score combinado:
           Score = return_pct * 0.4 + profit_factor * 30 + win_rate * 0.3
        3. Usa save_to_portfolio para guardar las mejores.
        4. Reporta el ranking completo.
        """,
        expected_output="Portfolio actualizado con ranking de estrategias.",
        agent=agent_obj,
    )


def create_reporter_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Reporter. Genera un resumen ejecutivo de los hallazgos.
        
        1. Toma los resultados de todos los agentes anteriores.
        2. Genera un reporte claro con:
           - Mejores estrategias encontradas
           - En qué activos funcionan
           - Recomendaciones de implementación
        3. El reporte debe ser accionable para el equipo de trading.
        """,
        expected_output="Reporte ejecutivo con las mejores estrategias para implementar.",
        agent=agent_obj,
    )
