"""
Búsqueda masiva de estrategias — prueba todas las combinaciones de
indicadores, timeframes, parámetros y lógicas de entrada para encontrar
una estrategia con retorno positivo y consistente.
"""

import itertools
from copy import deepcopy

from config import StrategyConfig


# ── ESTRATEGIAS DISPONIBLES ──────────────────────────────────
STRATEGY_TYPES = [
    "ema_cross",         # Cruce EMA 9/21 con filtro EMA 200
    "ema_strict",        # Cruce EMA + ADX alto + RSI filtrado
    "macd_cross",        # Cruce MACD linea/señal
    "rsi_reversal",      # RSI sobrecompra/venta con tendencia
    "bb_breakout",       # Breakout de Bandas de Bollinger
    "di_cross",          # Cruce DI+/DI-
    "donchian_breakout", # Ruptura Donchian
    "ma_price_pullback", # Pullback a media movil
    "momentum_breakout", # Ruptura por momentum fuerte
    "combined_strong",   # Combinacion de multiples confirmaciones
]


def build_strategy_candidates(base_cfg, strategy_types=None):
    """Genera una lista de configuraciones para probar cada tipo de estrategia."""
    if strategy_types is None:
        strategy_types = STRATEGY_TYPES

    candidates = []
    for st in strategy_types:
        params = _strategy_params(st)
        for p in params:
            cfg = deepcopy(base_cfg)
            cfg.strategy_type = st
            for k, v in p.items():
                setattr(cfg, k, v)
            candidates.append(cfg)
    return candidates


def _strategy_params(st):
    """Retorna lista de dicts de parametros para cada tipo de estrategia."""
    params = []

    if st == "ema_cross":
        for ema_fast, ema_slow in [(5, 13), (9, 21), (10, 30), (13, 26), (20, 50)]:
            for ema_trend in [100, 150, 200]:
                for adx_th in [15, 18, 20, 22, 25]:
                    for tp_mult in [2.0, 2.5, 3.0, 3.5]:
                        for trailing in [True, False]:
                            params.append({
                                "strategy_type": "ema_cross",
                                "ema_fast": ema_fast,
                                "ema_slow": ema_slow,
                                "ema_trend": ema_trend,
                                "adx_threshold": float(adx_th),
                                "atr_tp_mult": tp_mult,
                                "use_trailing_stop": trailing,
                                "min_signal_quality": 1,
                                "min_entry_quality": 0,
                                "min_body_ratio": 0.1,
                                "min_momentum_3": 0.0,
                            })

    elif st == "rsi_reversal":
        for rsi_oversold in [25, 30, 35]:
            for rsi_overbought in [65, 70, 75]:
                for ema_trend in [100, 150, 200]:
                    for tp_mult in [2.0, 2.5, 3.0]:
                        for adx_th in [15, 20, 25]:
                            params.append({
                                "strategy_type": "rsi_reversal",
                                "ema_trend": ema_trend,
                                "rsi_oversold": rsi_oversold,
                                "rsi_overbought": rsi_overbought,
                                "adx_threshold": float(adx_th),
                                "atr_tp_mult": tp_mult,
                                "use_trailing_stop": True,
                                "min_body_ratio": 0.2,
                            })

    elif st == "macd_cross":
        for macd_fast in [8, 12, 14]:
            for macd_slow in [21, 26, 30]:
                for macd_signal in [7, 9, 12]:
                    for adx_th in [15, 20, 22]:
                        for tp_mult in [2.0, 2.5, 3.0]:
                            for trailing in [True, False]:
                                params.append({
                                    "strategy_type": "macd_cross",
                                    "macd_fast": macd_fast,
                                    "macd_slow": macd_slow,
                                    "macd_signal": macd_signal,
                                    "adx_threshold": float(adx_th),
                                    "atr_tp_mult": tp_mult,
                                    "use_trailing_stop": trailing,
                                })

    elif st == "bb_breakout":
        for bb_period in [14, 20, 30]:
            for bb_std in [1.5, 2.0, 2.5]:
                for adx_th in [15, 20]:
                    for tp_mult in [2.0, 2.5, 3.0]:
                        params.append({
                            "strategy_type": "bb_breakout",
                            "bb_period": bb_period,
                            "bb_std": bb_std,
                            "adx_threshold": float(adx_th),
                            "atr_tp_mult": tp_mult,
                            "use_trailing_stop": True,
                        })

    elif st == "di_cross":
        for di_period in [10, 14, 20]:
            for adx_th in [18, 20, 22, 25]:
                for tp_mult in [2.0, 2.5, 3.0, 3.5]:
                    params.append({
                        "strategy_type": "di_cross",
                        "di_period": di_period,
                        "adx_threshold": float(adx_th),
                        "atr_tp_mult": tp_mult,
                        "use_trailing_stop": True,
                    })

    elif st == "donchian_breakout":
        for donchian_period in [10, 15, 20, 30]:
            for adx_th in [15, 18, 20, 22]:
                for tp_mult in [2.0, 2.5, 3.0]:
                    params.append({
                        "strategy_type": "donchian_breakout",
                        "donchian_period": donchian_period,
                        "adx_threshold": float(adx_th),
                        "atr_tp_mult": tp_mult,
                        "use_trailing_stop": True,
                    })

    elif st == "ma_price_pullback":
        for ma_period in [50, 100, 150, 200]:
            for pullback_pct in [0.005, 0.01, 0.015, 0.02]:
                for adx_th in [18, 20, 22]:
                    for tp_mult in [2.0, 2.5, 3.0, 3.5]:
                        params.append({
                            "strategy_type": "ma_price_pullback",
                            "ma_period": ma_period,
                            "pullback_pct": pullback_pct,
                            "adx_threshold": float(adx_th),
                            "atr_tp_mult": tp_mult,
                            "use_trailing_stop": True,
                        })

    elif st == "momentum_breakout":
        for mom_period in [3, 5, 8]:
            for mom_threshold in [0.001, 0.002, 0.003, 0.005]:
                for adx_th in [15, 18, 20, 22]:
                    for tp_mult in [2.0, 2.5, 3.0]:
                        params.append({
                            "strategy_type": "momentum_breakout",
                            "mom_period": mom_period,
                            "mom_threshold": mom_threshold,
                            "adx_threshold": float(adx_th),
                            "atr_tp_mult": tp_mult,
                            "use_trailing_stop": True,
                        })

    elif st == "combined_strong":
        for adx_th in [18, 20, 22, 25]:
            for tp_mult in [2.0, 2.5, 3.0, 3.5]:
                for ema_fast, ema_slow in [(9, 21), (10, 30)]:
                    params.append({
                        "strategy_type": "combined_strong",
                        "ema_fast": ema_fast,
                        "ema_slow": ema_slow,
                        "adx_threshold": float(adx_th),
                        "atr_tp_mult": tp_mult,
                        "use_trailing_stop": True,
                        "min_signal_quality": 2,
                        "min_entry_quality": 1,
                        "min_body_ratio": 0.4,
                        "min_momentum_3": 0.1,
                    })

        # combined_strong con trailing stop off y SL mas ajustado
        for adx_th in [20, 22]:
            for tp_mult in [2.5, 3.0]:
                params.append({
                    "strategy_type": "combined_strong",
                    "ema_fast": 9,
                    "ema_slow": 21,
                    "adx_threshold": float(adx_th),
                    "atr_sl_mult": 0.8,
                    "atr_tp_mult": tp_mult,
                    "use_trailing_stop": False,
                    "min_signal_quality": 2,
                    "min_entry_quality": 1,
                    "min_body_ratio": 0.5,
                    "min_momentum_3": 0.2,
                })

    return params
