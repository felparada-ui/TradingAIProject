"""
Configuracion central del sistema de trading.
ESTRATEGIA GANADORA (validada multi-timeframe):
  BTC/USDT H1 — ATFS
  Resultados: PF 1.13, Win Rate 47.06%, Retorno +1.53%, Max DD -6.32%
  50 trades sobre ~4 años (2021-2025) con capital $200
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════
# CONFIGURACION DE ESTRATEGIA
# ══════════════════════════════════════════════
@dataclass
class StrategyConfig:
    # --- Tipo de estrategia ---
    strategy_type: str = "atfs"           # Adaptive Trend-Following System
    timeframe: str = "1h"

    # --- Indicadores base (usados por ATFS) ---
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 200
    adx_period: int = 14
    adx_threshold: float = 22.0

    # --- ATR ---
    atr_period: int = 14
    atr_sl_mult: float = 1.0
    atr_tp_mult: float = 3.0
    use_trailing_stop: bool = True
    trailing_atr_mult: float = 0.8
    time_stop_bars: int = 8

    # --- Filtros de sesion ---
    session_timezone: str = "UTC"
    session_hours_utc: list = field(default_factory=lambda: list(range(8, 21)))
    trading_days: list = field(default_factory=lambda: [0, 1, 2, 3, 4])
    best_hours_utc: list = field(default_factory=lambda: [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])

    # --- Filtro de volatilidad minima ---
    min_atr_pct: float = 0.005
    min_signal_quality: int = 2
    min_body_ratio: float = 0.5

    # --- Estrategia hibrida multitimeframe (ATFS) ---
    hybrid_strategy_enabled: bool = True
    context_timeframe: str = "4h"
    context_adx_threshold: float = 20.0

    # --- Gestion de capital ($200 inicial) ---
    risk_per_trade: float = 0.01        # 1% por trade ($2 sobre $200)
    max_daily_loss: float = 0.03        # Circuit breaker diario: -3% ($6)
    max_drawdown_total: float = 0.10    # Circuit breaker total: -10% ($20)
    cooldown_bars_after_loss: int = 3   # 3 velas de pausa tras perdida
    max_concurrent_positions: int = 1   # 1 posicion a la vez

    # --- Donchian (breakout secundario) ---
    donchian_period: int = 20

    # --- Parametros de estrategias especificas ---
    # RSI reversal
    rsi_oversold: int = 30
    rsi_overbought: int = 70

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0

    # DI
    di_period: int = 14

    # Pullback
    ma_period: int = 100
    pullback_pct: float = 0.01

    # Momentum
    mom_period: int = 5
    mom_threshold: float = 0.002

    # --- VWAP Mean Reversion ---
    vwap_band_mult: float = 0.6
    vwap_min_volume_mult: float = 0.7
    vwap_adx_max: float = 22.0
    vwap_rsi_long_max: int = 45
    vwap_rsi_short_min: int = 55

    # --- Donchian Breakout ---
    donchian_adx_min: float = 25.0


# ══════════════════════════════════════════════
# CONFIGURACION DE EXCHANGE
# ══════════════════════════════════════════════
@dataclass
class ExchangeConfig:
    # Exchange principal: Binance
    exchange_id: str = "binance"
    symbol: str = "BTC/USDT"            # Par principal (ATFS sobre BTC/USDT H1)
    symbol_alt: str = "BTCUSDT"         # Formato alternativo para algunas APIs
    market_type: str = "future"         # 'future' para perpetuos, 'spot' para spot
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
    sandbox: bool = field(default_factory=lambda: os.getenv("SANDBOX", "true").lower() == "true")
    leverage: int = 1                   # Sin apalancamiento inicial (cuenta de $200)
                                         # Aumentar SOLO despues de validar rentabilidad


# ══════════════════════════════════════════════
# CONFIGURACION DE TELEGRAM
# ══════════════════════════════════════════════
@dataclass
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    # Tipos de notificaciones
    notify_on_entry: bool = True        # Alerta al abrir posicion
    notify_on_exit: bool = True         # Alerta al cerrar posicion
    notify_on_sl: bool = True           # Alerta especial al tocar stop loss
    notify_daily_summary: bool = True   # Resumen al cierre del dia (23:59 UTC)
    notify_circuit_breaker: bool = True # Alerta critica si se activa el circuit breaker
    notify_regime_change: bool = True   # Alerta si cambia el regimen de mercado


# ══════════════════════════════════════════════
# INSTANCIAS GLOBALES
# ══════════════════════════════════════════════
STRATEGY = StrategyConfig()
EXCHANGE = ExchangeConfig()
TELEGRAM = TelegramConfig()
