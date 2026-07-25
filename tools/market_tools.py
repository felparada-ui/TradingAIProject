"""
Herramientas de mercado para la crew de trading.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from crewai.tools import BaseTool
from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators
from strategies.atfs import generate_signals


class FetchOHLCVTool(BaseTool):
    name: str = "fetch_ohlcv"
    description: str = "Obtiene datos OHLCV de BTC/USDT H1 desde CSV local"

    def _run(self, csv_path: str = "/workspaces/TradingAIProject/data/btc_usdt_h1.csv", limit: int = 200) -> str:
        try:
            df = load_from_csv(csv_path)
            if df is None:
                return "Error: no se pudo cargar el CSV"
            df = add_all_indicators(df.tail(limit).reset_index(drop=True), STRATEGY)
            data = generate_signals(df, STRATEGY)
            last = data.iloc[-1]
            return (
                f"BTC/USDT H1 | Close: {last['close']:.2f} | ADX: {last['adx']:.1f} | "
                f"ATR: {last['atr']:.2f} | Regime: {last.get('regime','?')} | "
                f"Signal ATFS: {last.get('signal_atfs',0)} | "
                f"RSI: {last.get('rsi',0):.1f}"
            )
        except Exception as e:
            return f"Error: {e}"


class DetectMarketRegimeTool(BaseTool):
    name: str = "detect_market_regime"
    description: str = "Detecta el régimen actual del mercado BTC/USDT H1"

    def _run(self, csv_path: str = "/workspaces/TradingAIProject/data/btc_usdt_h1.csv") -> str:
        try:
            df = load_from_csv(csv_path)
            if df is None:
                return "Error: no se pudo cargar el CSV"
            data = generate_signals(df.tail(200).reset_index(drop=True), STRATEGY)
            regime_counts = data["regime"].value_counts()
            current = data.iloc[-1]["regime"]
            return f"Régimen actual: {current}\nDistribución últimas 200 velas:\n{regime_counts.to_string()}"
        except Exception as e:
            return f"Error: {e}"


class FetchFundingRateTool(BaseTool):
    name: str = "fetch_funding_rate"
    description: str = "Obtiene la funding rate de BTC/USDT (placeholder)"

    def _run(self) -> str:
        return "Funding rate: No disponible en modo backtest"


class FetchLiquidationsTool(BaseTool):
    name: str = "fetch_liquidations"
    description: str = "Obtiene liquidaciones de BTC/USDT (placeholder)"

    def _run(self) -> str:
        return "Liquidaciones: No disponible en modo backtest"


fetch_ohlcv_tool = FetchOHLCVTool()
detect_market_regime_tool = DetectMarketRegimeTool()
fetch_funding_rate_tool = FetchFundingRateTool()
fetch_liquidations_tool = FetchLiquidationsTool()
