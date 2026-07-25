"""
Proveedor de datos multi-fuente para la Autotrading Crew.

Soporta:
  1. CCXT (Binance) — datos reales de crypto en tiempo real
  2. CSV local — datos históricos desde MT5
  3. Simulado — datos sintéticos para desarrollo

Prioriza fuentes reales sobre simuladas automáticamente.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

STANDARD_COLS = ["timestamp", "open", "high", "low", "close", "volume"]

# Mapeo de símbolos del sistema a símbolos de exchange
SYMBOL_TO_EXCHANGE = {
    "BTC/USD": "BTC/USDT",
    "ETH/USD": "ETH/USDT",
    "BCH/USD": "BCH/USDT",
    "SOL/USD": "SOL/USDT",
    "LTC/USD": "LTC/USDT",
    "XRP/USD": "XRP/USDT",
    "EUR/USD": None,  # Forex no disponible en Binance
    "GBP/USD": None,
    "USD/JPY": None,
    "SPY": None,      # ETFs no disponibles en Binance
    "QQQ": None,
    "IWM": None,
}


class DataProvider:
    """
    Proveedor unificado de datos. Usa CCXT para crypto, CSV para MT5,
    y datos sintéticos como fallback universal.
    """

    def __init__(self, config: dict):
        self.config = config
        self._ccxt_cache: dict[str, pd.DataFrame] = {}
        self._csv_cache: dict[str, pd.DataFrame] = {}

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        days: int = 180,
    ) -> Optional[pd.DataFrame]:
        """
        Obtiene velas OHLCV para un símbolo.
        Prioriza: CCXT real → CSV local → Sintético
        """
        # 1. Intentar CCXT (solo crypto)
        exchange_symbol = SYMBOL_TO_EXCHANGE.get(symbol.upper())
        if exchange_symbol:
            df = self._fetch_from_ccxt(exchange_symbol, timeframe, days)
            if df is not None:
                logger.info(f"📡 Datos reales CCXT para {symbol}: {len(df)} velas")
                return df

        # 2. Intentar CSV local
        csv_path = f"data/{symbol.replace('/', '_')}_{timeframe}.csv"
        df = self._load_from_csv(csv_path)
        if df is not None:
            logger.info(f"💾 Datos CSV para {symbol}: {len(df)} velas")
            return df

        # 3. Fallback: sintético
        logger.warning(f"⚙️  Sin fuente real para {symbol} — usando datos sintéticos")
        return self._generate_synthetic(symbol, days, timeframe)

    def fetch_multi_asset(self, symbols: list[str], timeframe: str = "1h", days: int = 180) -> dict[str, pd.DataFrame]:
        """Obtiene datos para múltiples activos."""
        result = {}
        for symbol in symbols:
            df = self.fetch_ohlcv(symbol, timeframe, days)
            if df is not None:
                result[symbol] = df
        return result

    # ------------------------------------------------------------------
    # CCXT (Binance)
    # ------------------------------------------------------------------

    def _fetch_from_ccxt(self, symbol: str, timeframe: str, days: int) -> Optional[pd.DataFrame]:
        """Descarga velas desde Binance via CCXT."""
        cache_key = f"{symbol}_{timeframe}_{days}"
        if cache_key in self._ccxt_cache:
            return self._ccxt_cache[cache_key]

        try:
            import ccxt
        except ImportError:
            logger.debug("ccxt no instalado")
            return None

        try:
            exchange = ccxt.binance({"enableRateLimit": True})
            limit = min(days * 24, 1000)  # CCXT max 1000 velas
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not ohlcv:
                return None

            df = pd.DataFrame(ohlcv, columns=STANDARD_COLS)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.sort_values("timestamp").reset_index(drop=True)
            df = df.iloc[:-1]  # Quitar última vela incompleta

            self._ccxt_cache[cache_key] = df
            return df

        except Exception as e:
            logger.debug(f"Error CCXT {symbol}: {e}")
            return None

    # ------------------------------------------------------------------
    # CSV (MT5 exports)
    # ------------------------------------------------------------------

    def _load_from_csv(self, filepath: str) -> Optional[pd.DataFrame]:
        """Carga datos desde CSV exportado de MT5."""
        if filepath in self._csv_cache:
            return self._csv_cache[filepath]

        path = Path(filepath)
        if not path.exists():
            return None

        try:
            with open(filepath, "r") as f:
                first_line = f.readline()
            sep = "\t" if "\t" in first_line else ","

            df = pd.read_csv(filepath, sep=sep)
            df.columns = [c.strip("<>").lower().replace(" ", "_") for c in df.columns]

            if "date" in df.columns and "time" in df.columns:
                df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"])
                df = df.rename(columns={"tickvol": "volume", "vol": "volume_real"})
            elif "timestamp" not in df.columns and "time" in df.columns:
                df["timestamp"] = pd.to_datetime(df["time"], unit="s")
            elif "timestamp" not in df.columns:
                logger.warning(f"CSV {filepath}: sin columna temporal")
                return None

            df = df.sort_values("timestamp").reset_index(drop=True)
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            self._csv_cache[filepath] = df
            return df

        except Exception as e:
            logger.warning(f"Error leyendo CSV {filepath}: {e}")
            return None

    # ------------------------------------------------------------------
    # Generador sintético (mejorado con cambios de régimen)
    # ------------------------------------------------------------------

    def _generate_synthetic(self, symbol: str, days: int, timeframe: str) -> pd.DataFrame:
        """Genera datos sintéticos con cambios de régimen realistas."""
        np.random.seed(hash(f"{symbol}_data_provider") % 2 ** 31)

        n_bars = days * (24 if timeframe == "1h" else 96)
        base_prices = {"EUR/USD": 1.08, "BTC/USD": 45000, "SPY": 480,
                       "ETH/USD": 2800, "BCH/USD": 350, "SOL/USD": 140,
                       "GBP/USD": 1.26, "USD/JPY": 150, "XAU/USD": 2300}
        base_price = base_prices.get(symbol.upper(), 100)

        vol_pct = {"BTC/USD": 0.025, "ETH/USD": 0.030}.get(symbol.upper(), 0.008)
        vol_per_bar = vol_pct / np.sqrt(24) * 2

        price_min = base_price * 0.80
        price_max = base_price * 1.20

        prices = np.zeros(n_bars)
        prices[0] = base_price
        current = base_price
        n_seg = 6
        seg_len = n_bars // n_seg

        for seg in range(n_seg):
            start = seg * seg_len
            end = min(start + seg_len, n_bars)
            n = end - start

            # Ciclo: tendencia → tendencia → rango → rango → alta_vol → tendencia
            cycle = seg % 6
            if cycle < 2:
                drift = (1 if np.random.random() > 0.4 else -1) * vol_per_bar * 0.4
                vol = vol_per_bar * 0.7
            elif cycle < 4:
                drift = 0.0
                vol = vol_per_bar * 0.4
            else:
                drift = (1 if np.random.random() > 0.5 else -1) * vol_per_bar * 1.2
                vol = vol_per_bar * 2.0

            for i in range(n):
                idx = start + i
                if idx >= n_bars:
                    break
                ret = np.random.randn() * vol + drift
                current *= (1 + ret)
                current = max(min(current, price_max), price_min)
                prices[idx] = current

        for i in range(n_bars):
            if prices[i] == 0:
                prices[i] = prices[i - 1] if i > 0 else base_price

        dates = pd.date_range(end=datetime.now(), periods=n_bars, freq=timeframe.replace("h", "h"))
        spread = prices * 0.001
        daily_vol = np.abs(np.diff(prices, prepend=prices[0])) * 0.5

        return pd.DataFrame({
            "timestamp": dates,
            "open": prices,
            "high": prices + daily_vol + np.abs(np.random.randn(n_bars) * spread),
            "low": prices - daily_vol - np.abs(np.random.randn(n_bars) * spread),
            "close": prices,
            "volume": np.random.randint(500, 50000, n_bars),
        })
