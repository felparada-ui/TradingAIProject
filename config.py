"""
Configuracion central del sistema de trading.
MEJOR ESTRATEGIA (validada 4.5 años BCH/USDT 1H):
  EMA 5/13/150 + ADX 22 + TP 1.8 (sin trailing)
  Resultados: +20.38% retorno, PF 1.35, WR 43%, DD max -4.27%
  186 trades en 4.5 años (2022-2026)
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
    strategy_type: str = "ema_cross"    # ema_cross (ganadora: +20.38% en 4.5 años)
    timeframe: str = "1h"

    # --- Indicadores (EMA 5/13/150 optimo para BCH 1H) ---
    ema_fast: int = 5
    ema_slow: int = 13
    ema_trend: int = 150
    adx_period: int = 14
    adx_threshold: float = 22.0

    # --- ATR ---
    atr_period: int = 14
    atr_sl_mult: float = 1.0
    atr_tp_mult: float = 1.8
    use_trailing_stop: bool = False     # Trailing empeora resultados
    trailing_atr_mult: float = 0.8

    # --- Filtros de sesion ---
    session_timezone: str = "America/Santiago"
    session_start_local: str = "08:30"
    session_end_local: str = "23:30"
    session_hours_utc: list = field(default_factory=lambda: list(range(0, 24)))
    trading_days: list = field(default_factory=lambda: [0, 1, 2, 3, 4])
    best_hours_utc: list = field(default_factory=lambda: [13, 14, 15, 16, 17])

    # --- Filtro de volatilidad minima ---
    min_atr_pct: float = 0.0005
    min_signal_quality: int = 2
    min_entry_quality: int = 1
    min_body_ratio: float = 0.5
    min_momentum_3: float = 0.2

    # --- Estrategia hibrida ---
    hybrid_strategy_enabled: bool = False
    context_timeframe: str = "1h"
    context_adx_threshold: float = 20.0
    context_min_trend_strength: float = 0.0

    # --- Gestion de capital ---
    risk_per_trade: float = 0.005       # 0.5% por trade
    max_daily_loss: float = 0.08        # Circuit breaker diario: -8%
    max_drawdown_total: float = 0.20    # Circuit breaker total: -20%
    cooldown_bars_after_loss: int = 3
    max_concurrent_positions: int = 1
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
    symbol: str = "BCH/USDT"            # Par principal (optimizado para EMA 5/13/150)
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
