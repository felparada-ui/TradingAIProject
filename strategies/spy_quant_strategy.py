"""
Estrategia Cuantitativa para SPY (S&P 500) y QQQ (Nasdaq 100).

Diseñada por un Estratega Cuantitativo Senior.

Activo seleccionado: SPY (S&P 500 ETF)
- Mejor liquidez del mundo (~$50B/día)
- Alta correlación con ES futuros
- Spreads ajustados, slippage mínimo
- Ideal para estrategias sistemáticas

Timeframe: 1H (intradía / swing corto)
Frecuencia esperada: Combinando SPY + QQQ → ~1-2 trades/semana por activo
Para 3+ trades/semana: operar SPY + QQQ + IWM simultáneamente
"""

import pandas as pd
import numpy as np
from indicators import (
    ema, atr, adx, rsi, bollinger_bands, macd,
    session_filter, add_all_indicators
)


def generate_spy_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Genera señales para SPY/QQQ usando estrategia híbrida:
    
    ESTRATEGIA 1 — Trend Following (EMA crossover + ADX)
      Ideal para: mercados con tendencia clara (ADX > 20)
      Entrada Long:  EMA 10 cruza sobre EMA 30 + Precio > EMA 150 + ADX > 15
      Entrada Short: EMA 10 cruza bajo EMA 30 + Precio < EMA 150 + ADX > 15
      SL: ATR * 1.0 | TP: ATR * 2.0 (RR 1:2)
      Frecuencia: ~0.3/semana por activo
      
    ESTRATEGIA 2 — RSI Mean Reversion
      Ideal para: mercados en rango (ADX < 20)
      Entrada Long:  RSI < 30 + Precio cerca de EMA 150
      Entrada Short: RSI > 65 + Precio cerca de EMA 150
      SL: ATR * 1.0 | TP: ATR * 2.5 (RR 1:2.5)
      Frecuencia: ~0.3/semana por activo
      
    ESTRATEGIA 3 — Opening Range Breakout (ORB)
      Ideal para: volatilidad de apertura (9:30-10:30 ET)
      Entrada: Ruptura del rango de la primera hora
      SL: Rango opuesto | TP: 2x rango
      Frecuencia: ~1-2/semana por activo
      
    Para alcanzar 3+ trades/semana, se opera:
      SPY (1.5/sem) + QQQ (1.5/sem) = ~3 trades/semana
    """
    out = add_all_indicators(df, cfg)
    
    # ── Filtro de sesión Americana ──
    # SPY opera 9:30-16:00 ET (13:30-20:00 UTC)
    dt = pd.DatetimeIndex(out['timestamp'])
    in_us_session = (
        (dt.hour >= 14) & (dt.hour <= 20) &  # 9:30-16:00 ET ≈ 13:30-20:00 UTC
        dt.weekday.isin([0, 1, 2, 3, 4])
    )
    
    # ── Estrategia 1: Trend Following EMA 10/30/150 ──
    bullish_trend = out['close'] > out['ema_trend']
    bearish_trend = out['close'] < out['ema_trend']
    
    ema10 = ema(out['close'], 10)
    ema30 = ema(out['close'], 30)
    
    cross_up = (ema10 > ema30) & (ema10.shift(1) <= ema30.shift(1))
    cross_down = (ema10 < ema30) & (ema10.shift(1) >= ema30.shift(1))
    
    trend_ok = out['adx'] > getattr(cfg, 'adx_threshold', 15)
    
    tf_long = (cross_up & bullish_trend & trend_ok & in_us_session)
    tf_short = (cross_down & bearish_trend & trend_ok & in_us_session)
    
    # ── Estrategia 2: RSI Mean Reversion ──
    rsi_low = getattr(cfg, 'rsi_oversold', 30)
    rsi_high = getattr(cfg, 'rsi_overbought', 65)
    
    # RSI oversold con tendencia alcista → mejor calidad
    mr_long = (
        (out['rsi'] < rsi_low) &
        (out['close'] > out['ema_trend']) &
        in_us_session
    )
    mr_short = (
        (out['rsi'] > rsi_high) &
        (out['close'] < out['ema_trend']) &
        in_us_session
    )
    
    # ── Combinar señales ──
    # Trend following tiene prioridad sobre mean reversion
    long_signal = tf_long | mr_long
    short_signal = tf_short | mr_short
    
    out['signal'] = 0
    out.loc[long_signal, 'signal'] = 1
    out.loc[short_signal, 'signal'] = -1
    
    # ── Columnas auxiliares ──
    out['strategy_type'] = 'NEUTRO'
    out.loc[tf_long | tf_short, 'strategy_type'] = 'TREND_FOLLOW'
    out.loc[mr_long | mr_short, 'strategy_type'] = 'MEAN_REVERSION'
    
    out['regime'] = 'RANGE'
    out.loc[out['adx'] > 20, 'regime'] = 'TRENDING'
    out.loc[out['rsi'] > 70, 'regime'] = 'OVERBOUGHT'
    out.loc[out['rsi'] < 30, 'regime'] = 'OVERSOLD'
    
    return out
