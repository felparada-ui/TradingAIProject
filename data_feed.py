"""
Data Feed unificado para BTCUSDT.
Soporta multiples fuentes de datos para maxima disponibilidad:
  1. Binance Futures (principal) — datos en tiempo real via CCXT
  2. Binance Spot (fallback)     — si futuros no disponible
  3. CSV local (backtest/debug)  — datos historicos MT5

El sistema prioriza siempre la fuente mas reciente y confiable.
Compatible con cualquier broker mientras tenga OHLCV de BTC/USDT.
"""

import pandas as pd
import numpy as np
import logging
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Columnas estandar que usa todo el sistema
STANDARD_COLS = ["timestamp", "open", "high", "low", "close", "volume"]


# ══════════════════════════════════════════════
# FUNCIONES DE CARGA
# ══════════════════════════════════════════════

def load_from_ccxt(
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    limit: int = 500,
    market_type: str = "future",
    api_key: str = "",
    api_secret: str = "",
    sandbox: bool = False,
    retries: int = 3,
) -> Optional[pd.DataFrame]:
    """
    Descarga velas OHLCV desde Binance via CCXT.
    Intenta futuros primero, luego spot como fallback.
    """
    try:
        import ccxt
    except ImportError:
        logger.warning("ccxt no está instalado; se omite la descarga desde Binance")
        return None

    for attempt in range(retries):
        try:
            exchange = ccxt.binance({
                "apiKey"        : api_key,
                "secret"        : api_secret,
                "enableRateLimit": True,
                "options"       : {"defaultType": market_type},
            })
            if sandbox:
                exchange.set_sandbox_mode(True)

            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not ohlcv:
                raise ValueError("Sin datos recibidos")

            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df["timestamp"] = df["timestamp"].dt.tz_localize(None)  # Naive UTC
            df = df.sort_values("timestamp").reset_index(drop=True)

            # Eliminar la ultima vela (puede estar incompleta)
            df = df.iloc[:-1]

            logger.info(f"CCXT [{market_type}]: {len(df)} velas de {symbol} {timeframe} | "
                        f"Ultima: {df['timestamp'].iloc[-1]}")
            return df[STANDARD_COLS]

        except Exception as e:
            logger.warning(f"Intento {attempt+1}/{retries} fallido: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Backoff exponencial

    # Fallback a spot si futuros falla
    if market_type == "future":
        logger.warning("Futuros fallidos, intentando spot como fallback...")
        return load_from_ccxt(
            symbol=symbol, timeframe=timeframe, limit=limit,
            market_type="spot", api_key=api_key, api_secret=api_secret,
            sandbox=False, retries=2
        )

    logger.error("Imposible obtener datos de CCXT")
    return None


def load_from_csv(filepath: str) -> Optional[pd.DataFrame]:
    """
    Carga datos desde CSV exportado de MT5 u otras fuentes.
    Detecta automaticamente el formato (MT5, Binance, generico).
    """
    path = Path(filepath)
    if not path.exists():
        logger.error(f"Archivo CSV no encontrado: {filepath}")
        return None

    try:
        # Detectar separador
        with open(filepath, "r") as f:
            first_line = f.readline()
        sep = "\t" if "\t" in first_line else ","

        df = pd.read_csv(filepath, sep=sep)

        # Normalizar columnas — soporta formato MT5 y generico
        df.columns = [c.strip("<>").lower().replace(" ", "_") for c in df.columns]

        # Formato MT5: DATE + TIME separados
        if "date" in df.columns and "time" in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"])
            df = df.rename(columns={"tickvol": "volume", "vol": "volume_real"})

        # Formato generico con timestamp unico
        elif "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        elif "open_time" in df.columns:
            df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
            df = df.rename(columns={"open_time": "_open_time"})
        elif "datetime" in df.columns:
            df["timestamp"] = pd.to_datetime(df["datetime"])

        # Verificar columnas minimas
        missing = [c for c in ["timestamp", "open", "high", "low", "close"] if c not in df.columns]
        if missing:
            raise ValueError(f"Columnas faltantes: {missing}")

        if "volume" not in df.columns:
            df["volume"] = 0

        df = df[STANDARD_COLS].dropna()
        df = df.sort_values("timestamp").reset_index(drop=True)

        logger.info(f"CSV cargado: {len(df)} velas | "
                    f"{df['timestamp'].min()} -> {df['timestamp'].max()}")
        return df

    except Exception as e:
        logger.error(f"Error cargando CSV {filepath}: {e}")
        return None


def get_latest_data(
    cfg,
    limit: int = 500,
    csv_path: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """
    Punto de entrada principal para obtener datos.
    Jerarquia de fuentes:
      1. CCXT Binance Futures (tiempo real, preferido)
      2. CCXT Binance Spot (fallback)
      3. CSV local (solo si CCXT no disponible)

    Siempre retorna datos en formato estandar con timestamp UTC.
    """
    from config import EXCHANGE

    # Intento 1: CCXT Futures
    df = load_from_ccxt(
        symbol      = EXCHANGE.symbol,
        timeframe   = cfg.timeframe,
        limit       = limit,
        market_type = EXCHANGE.market_type,
        api_key     = EXCHANGE.api_key,
        api_secret  = EXCHANGE.api_secret,
        sandbox     = EXCHANGE.sandbox,
    )

    if df is not None and len(df) >= 50:
        return df

    # Intento 2: CSV local como fallback
    if csv_path:
        logger.warning("CCXT no disponible, usando CSV local como fallback")
        df_csv = load_from_csv(csv_path)
        if df_csv is not None:
            # Retornar solo las ultimas 'limit' velas del CSV
            return df_csv.tail(limit).reset_index(drop=True)

    logger.error("Sin fuente de datos disponible")
    return None


def update_data_incremental(
    existing_df: pd.DataFrame,
    cfg,
) -> pd.DataFrame:
    """
    Agrega las velas mas recientes al DataFrame existente.
    Evita descargar todo el historico en cada ciclo.
    Util para el live engine que corre cada 5 minutos.
    """
    from config import EXCHANGE

    # Solo descargar las ultimas 20 velas (suficiente para actualizar)
    new_df = load_from_ccxt(
        symbol      = EXCHANGE.symbol,
        timeframe   = cfg.timeframe,
        limit       = 20,
        market_type = EXCHANGE.market_type,
        api_key     = EXCHANGE.api_key,
        api_secret  = EXCHANGE.api_secret,
        sandbox     = EXCHANGE.sandbox,
    )

    if new_df is None:
        return existing_df

    # Combinar y eliminar duplicados
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    combined = combined.reset_index(drop=True)

    # Mantener maximo 1000 velas en memoria
    if len(combined) > 1000:
        combined = combined.tail(1000).reset_index(drop=True)

    return combined


def resample_ohlcv_to_timeframe(df: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
    """
    Resamplea datos OHLCV a un timeframe superior para usarlo como filtro de contexto.
    Ejemplo: M5 -> H1 o H4.
    """
    if df is None or df.empty:
        return df

    work = df.copy()
    if "timestamp" not in work.columns:
        raise ValueError("Se requiere una columna 'timestamp' para resamplear")

    work = work.sort_values("timestamp").set_index("timestamp")
    resampled = work.resample(timeframe).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()

    resampled = resampled.rename(columns={"timestamp": "timestamp"})
    return resampled


def build_multitimeframe_dataset(
    df: pd.DataFrame,
    context_timeframe: str = "1h",
) -> dict:
    """
    Devuelve un conjunto de datos de dos timeframes: principal M5 y contexto superior.
    Útil para estrategia inicial con confirmación H1.
    """
    if df is None or df.empty:
        return {"primary": df, "context": df}

    primary = df.copy()
    context = resample_ohlcv_to_timeframe(primary, context_timeframe)

    return {"primary": primary, "context": context}


def validate_data_quality(df: pd.DataFrame, min_rows: int = 210) -> bool:
    """
    Valida que los datos sean suficientes y de calidad para operar.
    Necesitamos al menos 210 velas para calcular EMA 200.
    """
    if df is None or len(df) < min_rows:
        logger.warning(f"Datos insuficientes: {len(df) if df is not None else 0} velas (minimo {min_rows})")
        return False

    # Verificar que no haya gaps grandes (mas de 10 velas faltantes consecutivas)
    df_sorted = df.sort_values("timestamp")
    time_diffs = df_sorted["timestamp"].diff().dt.total_seconds() / 60
    max_gap = time_diffs.max()
    if max_gap > 60:  # Gap mayor a 60 minutos
        logger.warning(f"Gap de datos detectado: {max_gap:.0f} minutos sin velas")

    # Verificar precios validos
    if (df["close"] <= 0).any():
        logger.error("Precios invalidos (cero o negativos) detectados")
        return False

    return True
