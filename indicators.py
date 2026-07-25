"""
Indicadores tecnicos optimizados para scalping/daytrading BTC/USDT M5.
Validados con 478,953 velas reales (2022-2026).

Indicadores confirmados como optimos:
  - EMA 9  : Señal rapida de cruce
  - EMA 21 : Señal lenta de cruce
  - EMA 200: Filtro macro de tendencia
  - ATR 14 : Volatilidad dinamica (SL/TP/sizing)
  - ADX 14 : Fuerza de tendencia (umbral 22)
  - Filtro horario: 14-17 UTC
  - Filtro semanal: Lunes a Viernes
"""

import pandas as pd
import numpy as np
from datetime import timezone


# ══════════════════════════════════════════════
# FUNCIONES BASE (vectorizadas con NumPy/pandas)
# ══════════════════════════════════════════════

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range — indicador central para SL/TP dinamicos.
    Calcula el TR una sola vez para evitar calculos duplicados.
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range crudo (sin suavizar). Reutilizable para ADX."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    return pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index — mide la fuerza de la tendencia.
    Umbral validado: 22 (por debajo = mercado lateral, no operar).
    Reutiliza true_range() para evitar calculo duplicado con atr().
    """
    high, low = df["high"], df["low"]

    up_move   = high.diff()
    down_move = -low.diff()

    plus_dm  = np.where((up_move > down_move) & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Reutilizamos TR crudo
    tr_raw      = true_range(df)
    atr_smooth  = tr_raw.ewm(alpha=1 / period, adjust=False).mean()

    plus_di  = 100 * pd.Series(plus_dm,  index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_smooth
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_smooth

    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val  = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val.fillna(0)


def donchian_channel(df: pd.DataFrame, period: int = 20):
    """Canal de Donchian — maximo y minimo de N velas."""
    upper = df["high"].rolling(period).max()
    lower = df["low"].rolling(period).min()
    return upper, lower


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI — usado como confirmacion secundaria."""
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD — Moving Average Convergence Divergence."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Bollinger Bands — volatilidad y niveles de sobrecompra/venta."""
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def di_plus_minus(df: pd.DataFrame, period: int = 14):
    """Directional Indicators DI+ and DI- (componentes del ADX)."""
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr_raw = true_range(df)
    atr_smooth = tr_raw.ewm(alpha=1 / period, adjust=False).mean()
    di_plus = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_smooth
    di_minus = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_smooth
    return di_plus, di_minus


def session_filter(
    timestamps: pd.Series,
    hours_utc: list | None = None,
    weekdays: list | None = None,
    timezone_name: str = "America/Santiago",
    start_local: str = "08:30",
    end_local: str = "23:30",
) -> pd.Series:
    """
    Filtro de sesion: retorna True solo en horas y dias validos.
    Usa la ventana local de Chile por defecto para alinearse con la ejecución del usuario.
    """
    if isinstance(timestamps, pd.Series):
        index = timestamps.index
    else:
        index = pd.RangeIndex(len(timestamps))

    dt = pd.DatetimeIndex(timestamps)

    if getattr(dt, "tz", None) is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")

    local_dt = dt.tz_convert(timezone_name)
    in_weekday = local_dt.weekday.isin(weekdays or [0, 1, 2, 3, 4])

    if start_local and end_local:
        start_hour, start_min = map(int, start_local.split(":"))
        end_hour, end_min = map(int, end_local.split(":"))
        start_minutes = start_hour * 60 + start_min
        end_minutes = end_hour * 60 + end_min
        current_minutes = local_dt.hour * 60 + local_dt.minute
        in_window = (current_minutes >= start_minutes) & (current_minutes <= end_minutes)
    else:
        in_window = local_dt.hour.isin(hours_utc or [])

    return pd.Series(in_window & in_weekday, index=index)


# ══════════════════════════════════════════════
# FUNCION PRINCIPAL: AGREGAR TODOS LOS INDICADORES
# ══════════════════════════════════════════════

def add_all_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Agrega todos los indicadores sobre el DataFrame OHLCV.
    Optimizado: cada serie base se calcula UNA SOLA VEZ.

    Columnas agregadas:
      ema_fast, ema_slow, ema_trend  — EMAs 9/21/200
      atr, atr_pct                   — Volatilidad dinamica
      adx                            — Fuerza de tendencia
      donchian_high, donchian_low    — Canal de breakout
      rsi                            — Confirmacion (secundario)
      in_session                     — Filtro horario/diario
      body_ratio                     — Calidad de la vela
    """
    out = df.copy()

    # --- EMAs (calculadas una sola vez) ---
    out["ema_fast"]  = ema(out["close"], cfg.ema_fast)    # EMA 9
    out["ema_slow"]  = ema(out["close"], cfg.ema_slow)    # EMA 21
    out["ema_trend"] = ema(out["close"], cfg.ema_trend)   # EMA 200

    # --- ATR (volatilidad) ---
    out["atr"]     = atr(out, cfg.atr_period)             # ATR 14
    out["atr_pct"] = out["atr"] / out["close"]            # ATR relativo

    # --- ADX (fuerza de tendencia) ---
    out["adx"] = adx(out, cfg.adx_period)                 # ADX 14

    # --- Canal Donchian ---
    out["donchian_high"], out["donchian_low"] = donchian_channel(out, cfg.donchian_period)

    # --- RSI (confirmacion secundaria) ---
    out["rsi"] = rsi(out["close"], period=14)

    # --- Filtro de sesion ---
    out["in_session"] = session_filter(
        out["timestamp"],
        hours_utc=getattr(cfg, "session_hours_utc", None),
        weekdays=cfg.trading_days,
        timezone_name=getattr(cfg, "session_timezone", "America/Santiago"),
        start_local=getattr(cfg, "session_start_local", "08:30"),
        end_local=getattr(cfg, "session_end_local", "23:30"),
    )

    # --- Calidad de vela (body ratio) ---
    body             = (out["close"] - out["open"]).abs()
    candle_range     = (out["high"] - out["low"]).replace(0, np.nan)
    out["body_ratio"] = body / candle_range

    # --- Momentum confirmacion ---
    out["momentum_3"] = out["close"] - out["close"].shift(3)   # Momentum 3 velas
    out["momentum_5"] = out["close"] - out["close"].shift(5)   # Momentum 5 velas

    # --- MACD ---
    macd_line, macd_signal_line, macd_hist = macd(out["close"], 
                                                   getattr(cfg, "macd_fast", 12),
                                                   getattr(cfg, "macd_slow", 26),
                                                   getattr(cfg, "macd_signal", 9))
    out["macd"] = macd_line
    out["macd_signal"] = macd_signal_line
    out["macd_hist"] = macd_hist
    out["macd_cross_up"] = (macd_line > macd_signal_line) & (macd_line.shift(1) <= macd_signal_line.shift(1))
    out["macd_cross_down"] = (macd_line < macd_signal_line) & (macd_line.shift(1) >= macd_signal_line.shift(1))

    # --- Bollinger Bands ---
    bb_upper, bb_mid, bb_lower = bollinger_bands(out["close"],
                                                  getattr(cfg, "bb_period", 20),
                                                  getattr(cfg, "bb_std", 2.0))
    out["bb_upper"] = bb_upper
    out["bb_mid"] = bb_mid
    out["bb_lower"] = bb_lower
    out["bb_width"] = (bb_upper - bb_lower) / bb_mid
    out["bb_position"] = (out["close"] - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # --- DI+ / DI- (directional) ---
    di_plus, di_minus = di_plus_minus(out, getattr(cfg, "di_period", 14))
    out["di_plus"] = di_plus
    out["di_minus"] = di_minus
    out["di_cross_up"] = (di_plus > di_minus) & (di_plus.shift(1) <= di_minus.shift(1))
    out["di_cross_down"] = (di_plus < di_minus) & (di_plus.shift(1) >= di_minus.shift(1))

    return out


# ══════════════════════════════════════════════
# DETECCION DE REGIMEN DE MERCADO
# ══════════════════════════════════════════════

def detect_regime(df: pd.DataFrame, adx_threshold: float = 22.0) -> pd.Series:
    """
    Detecta el regimen de mercado en cada vela.
    Regimenes:
      TREND_BULL : ADX > umbral, EMA9 > EMA21 > EMA200
      TREND_BEAR : ADX > umbral, EMA9 < EMA21 < EMA200
      RANGE      : ADX <= umbral
      HIGH_VOL   : ATR% > percentil 80
    """
    required = ["adx", "ema_fast", "ema_slow", "ema_trend", "atr_pct"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Columna '{col}' no encontrada. Ejecuta add_all_indicators() primero.")

    atr_p80 = df["atr_pct"].quantile(0.80)

    conditions = [
        df["atr_pct"] > atr_p80,
        (df["adx"] > adx_threshold) & (df["ema_fast"] > df["ema_slow"]) & (df["ema_slow"] > df["ema_trend"]),
        (df["adx"] > adx_threshold) & (df["ema_fast"] < df["ema_slow"]) & (df["ema_slow"] < df["ema_trend"]),
    ]
    choices = ["HIGH_VOL", "TREND_BULL", "TREND_BEAR"]
    regime = np.select(conditions, choices, default="RANGE")
    return pd.Series(regime, index=df.index)
