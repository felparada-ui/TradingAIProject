"""
Estrategia principal: Generador universal de señales.

MEJOR ESTRATEGIA ENCONTRADA (validada 4.5 años BCH/USDT 1H):
  EMA 5/13/150 + ADX 22 + TP 1.8 (sin trailing)
  Resultados: +20.38% retorno, PF 1.35, WR 43%, DD max -4.27%
  186 trades en 4.5 años (2022-2026)
  
  No funciona en BTC/ETH — es especifica de BCH/USDT 1H.
"""

import pandas as pd
import numpy as np
from indicators import add_all_indicators, ema, session_filter


def generate_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Generador universal de señales — soporta multiples tipos de estrategia.
    Segun cfg.strategy_type, aplica una logica de entrada diferente.

    Tipos soportados:
      ema_cross          — Cruce EMA 9/21 con filtro EMA 200
      ema_strict         — EMA cross + ADX alto + RSI + body ratio
      macd_cross         — Cruce MACD linea/señal
      rsi_reversal       — RSI sobrecompra/venta con tendencia
      bb_breakout        — Breakout de Bandas de Bollinger
      di_cross           — Cruce DI+/DI-
      donchian_breakout  — Ruptura Donchian
      ma_price_pullback   — Pullback a media movil
      momentum_breakout  — Ruptura por momentum fuerte
      combined_strong    — Combinacion de multiples confirmaciones

    Returns:
        DataFrame con columna 'signal': 1=long, -1=short, 0=sin operacion
    """
    out = add_all_indicators(df, cfg)

    strategy_type = getattr(cfg, "strategy_type", "ema_cross")

    # Variables comunes
    in_session = out["in_session"]
    hp = getattr(cfg, "best_hours_utc", list(range(8, 21)))
    dt = pd.DatetimeIndex(out["timestamp"])
    is_premium_hour = dt.hour.isin(hp)

    # ── Generar señal segun tipo de estrategia ────────────────
    if strategy_type == "rsi_reversal":
        long_signal  = (
            (out["rsi"] < getattr(cfg, "rsi_oversold", 30)) &
            (out["close"] > out["ema_trend"]) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )
        short_signal = (
            (out["rsi"] > getattr(cfg, "rsi_overbought", 70)) &
            (out["close"] < out["ema_trend"]) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )

    elif strategy_type == "macd_cross":
        cross_up   = out["macd_cross_up"]
        cross_down = out["macd_cross_down"]
        long_signal  = cross_up & (out["close"] > out["ema_trend"]) & (out["adx"] > cfg.adx_threshold) & in_session
        short_signal = cross_down & (out["close"] < out["ema_trend"]) & (out["adx"] > cfg.adx_threshold) & in_session

    elif strategy_type == "bb_breakout":
        long_signal  = (
            (out["close"] > out["bb_upper"]) &
            (out["close"].shift(1) <= out["bb_upper"].shift(1)) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )
        short_signal = (
            (out["close"] < out["bb_lower"]) &
            (out["close"].shift(1) >= out["bb_lower"].shift(1)) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )

    elif strategy_type == "di_cross":
        di_period = getattr(cfg, "di_period", 14)
        # Usamos la columna ya calculada o la calculamos sobre la marcha
        di_up = out["di_cross_up"]
        di_down = out["di_cross_down"]
        long_signal  = di_up & (out["adx"] > cfg.adx_threshold) & in_session
        short_signal = di_down & (out["adx"] > cfg.adx_threshold) & in_session

    elif strategy_type == "donchian_breakout":
        donchian_period = getattr(cfg, "donchian_period", 20)
        long_signal  = (
            (out["close"] > out["donchian_high"].shift(1)) &
            (out["close"].shift(1) <= out["donchian_high"].shift(2)) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )
        short_signal = (
            (out["close"] < out["donchian_low"].shift(1)) &
            (out["close"].shift(1) >= out["donchian_low"].shift(2)) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )

    elif strategy_type == "ma_price_pullback":
        ma_period = getattr(cfg, "ma_period", 100)
        out["ma_pullback"] = ema(out["close"], ma_period)
        pullback_pct = getattr(cfg, "pullback_pct", 0.01)
        long_signal  = (
            (out["close"] > out["ma_pullback"]) &
            ((out["close"] - out["ma_pullback"]) / out["ma_pullback"] < pullback_pct) &
            (out["adx"] > cfg.adx_threshold) &
            in_session &
            (out["momentum_3"] > 0)
        )
        short_signal = (
            (out["close"] < out["ma_pullback"]) &
            ((out["ma_pullback"] - out["close"]) / out["ma_pullback"] < pullback_pct) &
            (out["adx"] > cfg.adx_threshold) &
            in_session &
            (out["momentum_3"] < 0)
        )

    elif strategy_type == "momentum_breakout":
        mom_period = getattr(cfg, "mom_period", 5)
        mom_threshold = getattr(cfg, "mom_threshold", 0.002)
        out["mom_col"] = out["close"] - out["close"].shift(mom_period)
        mom_pct = out["mom_col"] / out["close"].shift(mom_period)
        long_signal = (
            (mom_pct > mom_threshold) &
            (out["close"] > out["ema_trend"]) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )
        short_signal = (
            (mom_pct < -mom_threshold) &
            (out["close"] < out["ema_trend"]) &
            (out["adx"] > cfg.adx_threshold) &
            in_session
        )

    elif strategy_type == "combined_strong":
        bullish_macro = out["close"] > out["ema_trend"]
        bearish_macro = out["close"] < out["ema_trend"]

        cross_up   = (
            (out["ema_fast"] > out["ema_slow"]) &
            (out["ema_fast"].shift(1) <= out["ema_slow"].shift(1))
        )
        cross_down = (
            (out["ema_fast"] < out["ema_slow"]) &
            (out["ema_fast"].shift(1) >= out["ema_slow"].shift(1))
        )

        trend_ok = out["adx"] > cfg.adx_threshold
        base_candidate_long = bullish_macro & cross_up & trend_ok & in_session
        base_candidate_short = bearish_macro & cross_down & trend_ok & in_session

        out["signal_quality"] = 0
        for mask in [base_candidate_long, base_candidate_short]:
            if mask.sum() == 0:
                continue
            out.loc[mask, "signal_quality"] = (
                (out.loc[mask, "adx"] > 25).astype(int) +
                (out.loc[mask, "body_ratio"] > 0.5).astype(int) +
                (out.loc[mask, "momentum_3"].abs() > 0).astype(int) +
                (out.loc[mask, "rsi"].between(40, 65)).astype(int) +
                (out.loc[mask, "atr_pct"] > out["atr_pct"].median()).astype(int)
            )

        out["entry_quality"] = 0
        if base_candidate_long.sum() > 0:
            out.loc[base_candidate_long, "entry_quality"] = (
                (out.loc[base_candidate_long, "close"] > out.loc[base_candidate_long, "ema_trend"]).astype(int) +
                (out.loc[base_candidate_long, "adx"] > 25).astype(int) +
                (out.loc[base_candidate_long, "rsi"].between(40, 65)).astype(int)
            )
        if base_candidate_short.sum() > 0:
            out.loc[base_candidate_short, "entry_quality"] = (
                (out.loc[base_candidate_short, "close"] < out.loc[base_candidate_short, "ema_trend"]).astype(int) +
                (out.loc[base_candidate_short, "adx"] > 25).astype(int) +
                (out.loc[base_candidate_short, "rsi"].between(40, 65)).astype(int)
            )

        quality_ok = out["signal_quality"] >= getattr(cfg, "min_signal_quality", 2)
        entry_ok = out["entry_quality"] >= getattr(cfg, "min_entry_quality", 1)
        body_ok = out["body_ratio"] >= getattr(cfg, "min_body_ratio", 0.4)
        mom_ok = out["momentum_3"].abs() >= getattr(cfg, "min_momentum_3", 0.1)

        macd_ok = (
            ((out["macd"] > out["macd_signal"]) & bullish_macro) |
            ((out["macd"] < out["macd_signal"]) & bearish_macro)
        )

        rsi_ok = out["rsi"].between(35, 70)

        di_ok = (
            ((out["di_plus"] > out["di_minus"]) & bullish_macro) |
            ((out["di_plus"] < out["di_minus"]) & bearish_macro)
        )

        long_signal = (
            base_candidate_long & quality_ok & entry_ok & body_ok & mom_ok &
            macd_ok & rsi_ok & di_ok & is_premium_hour
        )
        short_signal = (
            base_candidate_short & quality_ok & entry_ok & body_ok & mom_ok &
            macd_ok & rsi_ok & di_ok & is_premium_hour
        )

    else:  # "ema_cross" por defecto
        bullish_macro = out["close"] > out["ema_trend"]
        bearish_macro = out["close"] < out["ema_trend"]

        cross_up   = (
            (out["ema_fast"] > out["ema_slow"]) &
            (out["ema_fast"].shift(1) <= out["ema_slow"].shift(1))
        )
        cross_down = (
            (out["ema_fast"] < out["ema_slow"]) &
            (out["ema_fast"].shift(1) >= out["ema_slow"].shift(1))
        )

        trend_ok = out["adx"] > cfg.adx_threshold

        # Calcular signal_quality y entry_quality para todas las velas candidatas
        candidate_long = bullish_macro & cross_up & trend_ok & in_session
        candidate_short = bearish_macro & cross_down & trend_ok & in_session

        out["signal_quality"] = 0
        for mask in [candidate_long, candidate_short]:
            if mask.sum() == 0:
                continue
            out.loc[mask, "signal_quality"] = (
                (out.loc[mask, "adx"] > 25).astype(int) +
                (out.loc[mask, "body_ratio"] > 0.5).astype(int) +
                (out.loc[mask, "momentum_3"].abs() > 0).astype(int) +
                (out.loc[mask, "rsi"].between(40, 65)).astype(int) +
                (out.loc[mask, "atr_pct"] > out["atr_pct"].median()).astype(int)
            )

        out["entry_quality"] = 0
        if candidate_long.sum() > 0:
            out.loc[candidate_long, "entry_quality"] = (
                (out.loc[candidate_long, "close"] > out.loc[candidate_long, "ema_trend"]).astype(int) +
                (out.loc[candidate_long, "adx"] > 25).astype(int) +
                (out.loc[candidate_long, "rsi"].between(40, 65)).astype(int)
            )
        if candidate_short.sum() > 0:
            out.loc[candidate_short, "entry_quality"] = (
                (out.loc[candidate_short, "close"] < out.loc[candidate_short, "ema_trend"]).astype(int) +
                (out.loc[candidate_short, "adx"] > 25).astype(int) +
                (out.loc[candidate_short, "rsi"].between(40, 65)).astype(int)
            )

        quality_ok = out["signal_quality"] >= getattr(cfg, "min_signal_quality", 1)
        entry_ok = out["entry_quality"] >= getattr(cfg, "min_entry_quality", 0)
        body_ok = out["body_ratio"] >= getattr(cfg, "min_body_ratio", 0.1)

        long_signal  = candidate_long & quality_ok & entry_ok & body_ok
        short_signal = candidate_short & quality_ok & entry_ok & body_ok

    # ── Asignar señal ────────────────────────────────────────
    out["signal"] = 0
    out.loc[long_signal,  "signal"] = 1
    out.loc[short_signal, "signal"] = -1

    # ── Columnas auxiliares ──────────────────────────────────
    atr_p80 = out["atr_pct"].quantile(0.80)
    out["regime"] = "RANGE"
    if "ema_trend" in out.columns:
        bullish = out["close"] > out["ema_trend"]
        bearish = out["close"] < out["ema_trend"]
        out.loc[(out["adx"] > cfg.adx_threshold) & bullish, "regime"] = "TREND_BULL"
        out.loc[(out["adx"] > cfg.adx_threshold) & bearish, "regime"] = "TREND_BEAR"
    out.loc[out["atr_pct"] > atr_p80, "regime"] = "HIGH_VOL"

    return out
