import itertools
from copy import deepcopy

from config import StrategyConfig


def build_candidate_configs(base_cfg: StrategyConfig, adx_thresholds=None, atr_tp_mults=None):
    """Genera combinaciones de configuraciones para optimizar la estrategia."""
    adx_thresholds = adx_thresholds or [18.0, 22.0, 25.0]
    atr_tp_mults = atr_tp_mults or [2.0, 2.5, 3.0]

    candidates = []
    for adx_threshold, atr_tp_mult in itertools.product(adx_thresholds, atr_tp_mults):
        cfg = deepcopy(base_cfg)
        cfg.adx_threshold = adx_threshold
        cfg.atr_tp_mult = atr_tp_mult
        candidates.append(cfg)

    return candidates


def rank_candidates(candidates, data, initial_capital=200.0, metric_name="total_return_pct"):
    """Evalúa candidatos y devuelve una lista ordenada por métrica objetivo."""
    from backtest import run_backtest

    scored = []
    for cfg in candidates:
        trades, equity, metrics = run_backtest(data, cfg, initial_capital=initial_capital)
        if "error" in metrics:
            continue
        metrics = dict(metrics)
        metrics["cfg"] = cfg
        scored.append(metrics)

    scored.sort(key=lambda item: item.get(metric_name, float("-inf")), reverse=True)
    return scored
