#!/usr/bin/env python3
"""
Backtest Ensemble: EMA Trend Scalping + VWAP Mean Reversion
Ejecuta ambas estrategias sobre el mismo dataset y muestra métricas separadas + globales.
"""

import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import pandas as pd
import numpy as np
from datetime import timezone
from config import STRATEGY
from data_feed import load_from_csv
from indicators import add_all_indicators
from strategies.ema_trend_scalping import generate_signals as generate_ema_signals
from strategies.vwap_mean_reversion import generate_signals as generate_vwap_signals
from strategies.donchian_breakout import generate_signals as generate_donchian_signals
from risk_manager import RiskManager

CSV = "/workspaces/TradingAIProject/data/btc_usdt_m5.csv"
INITIAL_CAPITAL = 200.0


def backtest_strategy(
    data: pd.DataFrame,
    strategy_name: str,
    signal_col: str,
    stop_mult: float,
    tp_override_col: str = None,
    tp_use_dynamic: bool = False,
    tp_mult: float = 2.0,
) -> dict:
    """
    Ejecuta backtest genérico para una estrategia.
    
    Args:
        data: DataFrame con columnas: signal, atr, close, high, low, in_session
        strategy_name: nombre para reporte
        signal_col: columna de señal (1/-1/0)
        stop_mult: multiplicador ATR para SL
        tp_override_col: si se especifica, usa esa columna como TP (ej: 'vwap')
        tp_use_dynamic: si True, actualiza TP cada vela con tp_override_col
    """
    data = data.copy()
    data = data.dropna(subset=["ema_fast", "ema_slow", "ema_trend", "adx", "atr", "close"]).reset_index(drop=True)
    
    rm = RiskManager(STRATEGY, INITIAL_CAPITAL)
    position = None
    trades = []
    eq_values = []
    eq_ts = []

    for i, row in enumerate(data.itertuples(index=True)):
        ts = row.timestamp
        eq_ts.append(ts)
        eq_values.append(rm.equity)

        rm.reset_day_if_needed(ts)

        if rm.circuit_breaker_active:
            continue

        # Gestionar posición abierta
        if position is not None:
            # Actualizar trailing stop si aplica
            position = rm.update_trailing_stop(position, row.close, row.atr)

            # Hit stop
            if position.side == 1:
                hit_stop = row.low <= position.stop_price
                hit_tp = row.high >= position.take_profit
            else:
                hit_stop = row.high >= position.stop_price
                hit_tp = row.low <= position.take_profit

            if hit_stop or hit_tp:
                exit_price = position.stop_price if hit_stop else position.take_profit
                reason = "stop" if hit_stop else "take_profit"
                pnl = rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                trades.append({**position.__dict__, "pnl_usd": pnl, "exit_price": exit_price, "reason": reason, "strategy": strategy_name})
                position = None
            else:
                # Actualizar TP dinámico si corresponde (VWAP MR)
                if tp_use_dynamic and tp_override_col in data.columns:
                    new_tp = getattr(row, tp_override_col, None)
                    if new_tp is not None and not pd.isna(new_tp):
                        if position.side == 1 and new_tp > position.take_profit:
                            position.take_profit = new_tp
                        elif position.side == -1 and new_tp < position.take_profit:
                            position.take_profit = new_tp

        # Evaluar nueva entrada
        if position is None:
            if rm.daily_loss_hit():
                continue
            if rm.cooldown_active(i):
                continue
            if not getattr(row, "in_session", False):
                continue
            cb = rm.check_circuit_breakers()
            if cb:
                continue

            sig = getattr(row, signal_col, 0)
            if sig == 0:
                continue

            side = 1 if sig == 1 else -1
            # SL basado en ATR con multiplicador de estrategia
            atr_val = getattr(row, "atr", 0)
            if atr_val <= 0:
                continue
            stop = row.close - atr_val * stop_mult if side == 1 else row.close + atr_val * stop_mult
            
            # TP: si hay override (VWAP), usar ese; si no, usar ATR * 2 (RR 1:2)
            if tp_override_col and not tp_use_dynamic:
                tp_val = getattr(row, tp_override_col, None)
                if tp_val is not None and not pd.isna(tp_val):
                    tp = tp_val
                else:
                    tp = row.close + atr_val * tp_mult * side if side == 1 else row.close - atr_val * tp_mult
            else:
                tp = row.close + atr_val * 2.0 if side == 1 else row.close - atr_val * 2.0

            # Si TP está del lado equivocado (ej: short pero TP < entry), forzar mínimo
            if side == 1 and tp <= row.close:
                tp = row.close + atr_val * 1.0
            if side == -1 and tp >= row.close:
                tp = row.close - atr_val * 1.0

            size = rm.calc_position_size(row.close, stop)
            if size <= 0:
                continue

            position = rm.open_position(
                side=side,
                entry_price=row.close,
                atr_value=atr_val,
                entry_bar=i,
                entry_time=ts,
                regime=getattr(row, "regime", "UNKNOWN"),
                signal_quality=getattr(row, "signal_quality", 0),
                strategy=strategy_name,
            )
            if position is None:
                continue

            # Override SL/TP generados por RiskManager con parámetros de la estrategia
            position.stop_price = stop
            position.take_profit = tp

    # Cerrar posición abierta al final
    if position is not None:
        last = data.iloc[-1]
        exit_price = last["close"]
        pnl = rm.close_position(position, exit_price, len(data)-1, last["timestamp"], "end_of_data", send_notification=False)
        trades.append({**position.__dict__, "pnl_usd": pnl, "exit_price": exit_price, "reason": "end_of_data", "strategy": strategy_name})
        position = None

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame({"timestamp": eq_ts, "equity": eq_values})
    metrics = compute_metrics(trades_df, equity_df, INITIAL_CAPITAL)
    return metrics, trades_df, equity_df


def compute_metrics(trades_df, equity_df, initial_capital):
    if trades_df.empty:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_approx": 0.0,
            "avg_win_usd": 0.0,
            "avg_loss_usd": 0.0,
            "final_equity": initial_capital,
        }

    wins = trades_df[trades_df["pnl_usd"] > 0]
    losses = trades_df[trades_df["pnl_usd"] <= 0]
    final_equity = equity_df["equity"].iloc[-1]
    total_return = (final_equity - initial_capital) / initial_capital * 100
    gross_profit = wins["pnl_usd"].sum()
    gross_loss = abs(losses["pnl_usd"].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max) / running_max
    max_dd = drawdown.min() * 100

    returns = equity_df["equity"].pct_change().dropna()
    bars_per_year = 252 * 24 * 12
    sharpe = (returns.mean() / returns.std() * np.sqrt(bars_per_year)) if returns.std() > 0 else 0

    win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) else 0

    return {
        "total_trades": len(trades_df),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_approx": round(sharpe, 2),
        "avg_win_usd": round(wins["pnl_usd"].mean(), 4) if len(wins) else 0,
        "avg_loss_usd": round(losses["pnl_usd"].mean(), 4) if len(losses) else 0,
        "final_equity": round(final_equity, 2),
    }


def main():
    print("\n" + "=" * 58)
    print("  BACKTEST ENSEMBLE | BTC/USDT M5 | EMA + VWAP MR")
    print("=" * 58)

    df = load_from_csv(CSV)
    if df is None:
        print("No se pudo cargar el CSV.")
        return

    # Indicadores base
    data = add_all_indicators(df, STRATEGY)
    data = data.dropna(subset=["ema_fast", "ema_slow", "ema_trend", "adx", "atr", "close"]).reset_index(drop=True)
    print(f"Filas válidas: {len(data)}")

    # Señales EMA (estrategia actual)
    data_ema = generate_ema_signals(data.copy(), STRATEGY)
    data_ema["signal_ema"] = data_ema["signal"]
    data_ema["regime_ema"] = data_ema["regime"]
    data_ema["signal_quality_ema"] = data_ema["signal_quality"]

    # Señales VWAP MR (nueva estrategia)
    data_vwap = generate_vwap_signals(data.copy(), STRATEGY)
    data_vwap["signal_vwap"] = data_vwap["signal_vwap"]
    data_vwap["regime_vwap"] = data_vwap["regime_vwap"]
    data_vwap["signal_quality_vwap"] = data_vwap["signal_quality_vwap"]

    # Señales Donchian Breakout
    data_don = generate_donchian_signals(data.copy(), STRATEGY)
    data_don["signal_donchian"] = data_don["signal_donchian"]
    data_don["signal_quality_donchian"] = data_don["signal_quality_donchian"]

    # Combinar columnas de señales en un solo DataFrame
    combined = data.copy()
    combined["signal_ema"] = data_ema["signal_ema"]
    combined["signal_vwap"] = data_vwap["signal_vwap"]
    combined["signal_donchian"] = data_don["signal_donchian"]
    combined["regime_ema"] = data_ema["regime_ema"]
    combined["regime_vwap"] = data_vwap["regime_vwap"]
    combined["signal_quality_ema"] = data_ema["signal_quality_ema"]
    combined["signal_quality_vwap"] = data_vwap["signal_quality_vwap"]
    combined["vwap"] = data_vwap["vwap"]
    combined["vwap_lower"] = data_vwap["vwap_lower"]
    combined["vwap_upper"] = data_vwap["vwap_upper"]

    # Backtest EMA solo (baseline)
    metrics_ema, trades_ema, equity_ema = backtest_strategy(
        data=combined,
        strategy_name="EMA_Trend",
        signal_col="signal_ema",
        stop_mult=1.0,
        tp_override_col=None,
        tp_use_dynamic=False,
    )

    # Backtest VWAP solo
    metrics_vwap, trades_vwap, equity_vwap = backtest_strategy(
        data=combined,
        strategy_name="VWAP_MR",
        signal_col="signal_vwap",
        stop_mult=1.0,
        tp_override_col="vwap",
        tp_use_dynamic=False,
    )

    # Backtest VWAP dinámico (TP actualizado a VWAP en cada vela)
    metrics_vwap_dyn, trades_vwap_dyn, equity_vwap_dyn = backtest_strategy(
        data=combined,
        strategy_name="VWAP_MR_DYN",
        signal_col="signal_vwap",
        stop_mult=1.0,
        tp_override_col="vwap",
        tp_use_dynamic=True,
    )

    # Backtest Donchian solo
    metrics_donchian, trades_donchian, equity_donchian = backtest_strategy(
        data=combined,
        strategy_name="Donchian_Breakout",
        signal_col="signal_donchian",
        stop_mult=1.5,
        tp_mult=3.0,
    )

    # Backtest EMA + VWAP ensemble (una posición a la vez)
    def backtest_ensemble(data, stop_mult_ema=1.0, stop_mult_vwap=1.0):
        rm = RiskManager(STRATEGY, INITIAL_CAPITAL)
        position = None
        trades = []
        eq_values = []
        eq_ts = []

        for i, row in enumerate(data.itertuples(index=True)):
            ts = row.timestamp
            eq_ts.append(ts)
            eq_values.append(rm.equity)

            rm.reset_day_if_needed(ts)
            if rm.circuit_breaker_active:
                continue

            if position is not None:
                position = rm.update_trailing_stop(position, row.close, row.atr)
                if position.side == 1:
                    hit_stop = row.low <= position.stop_price
                    hit_tp = row.high >= position.take_profit
                else:
                    hit_stop = row.high >= position.stop_price
                    hit_tp = row.low <= position.take_profit

                if hit_stop or hit_tp:
                    exit_price = position.stop_price if hit_stop else position.take_profit
                    reason = "stop" if hit_stop else "take_profit"
                    pnl = rm.close_position(position, exit_price, i, ts, reason, send_notification=False)
                    trades.append({**position.__dict__, "pnl_usd": pnl, "exit_price": exit_price, "reason": reason})
                    position = None

            if position is None:
                if rm.daily_loss_hit() or rm.cooldown_active(i) or not getattr(row, "in_session", False):
                    continue
                cb = rm.check_circuit_breakers()
                if cb:
                    continue

                # Prioridad: EMA primero, luego VWAP
                sig = None
                strategy_name = None
                stop_m = None
                tp_val = None
                tp_dynamic = False

                if getattr(row, "signal_ema", 0) != 0:
                    sig = getattr(row, "signal_ema", 0)
                    strategy_name = "EMA_Trend"
                    stop_m = stop_mult_ema
                    tp_val = row.close + getattr(row, "atr", 0) * 2.0 if sig == 1 else row.close - getattr(row, "atr", 0) * 2.0
                elif getattr(row, "signal_vwap", 0) != 0:
                    sig = getattr(row, "signal_vwap", 0)
                    strategy_name = "VWAP_MR"
                    stop_m = stop_mult_vwap
                    tp_val = row.vwap if hasattr(row, "vwap") else None
                    tp_dynamic = True

                if sig is None:
                    continue

                side = 1 if sig == 1 else -1
                atr_val = getattr(row, "atr", 0)
                if atr_val <= 0:
                    continue
                stop = row.close - atr_val * stop_m if side == 1 else row.close + atr_val * stop_m
                if tp_val is None:
                    tp_val = row.close + atr_val * 2.0 if side == 1 else row.close - atr_val * 2.0

                size = rm.calc_position_size(row.close, stop)
                if size <= 0:
                    continue

                position = rm.open_position(
                    side=side,
                    entry_price=row.close,
                    atr_value=atr_val,
                    entry_bar=i,
                    entry_time=ts,
                    regime=getattr(row, "regime", "UNKNOWN"),
                    signal_quality=getattr(row, "signal_quality", 0),
                    strategy=strategy_name,
                )
                if position is None:
                    continue

                position.stop_price = stop
                position.take_profit = tp_val
                position._tp_dynamic = tp_dynamic
                position._tp_col = "vwap" if tp_dynamic else None

                # Si es dinámico, actualizar TP cada vela
                if tp_dynamic:
                    if side == 1 and row.vwap > position.take_profit:
                        position.take_profit = row.vwap
                    elif side == -1 and row.vwap < position.take_profit:
                        position.take_profit = row.vwap

        if position is not None:
            last = data.iloc[-1]
            pnl = rm.close_position(position, last["close"], len(data)-1, last["timestamp"], "end_of_data", send_notification=False)
            trades.append({**position.__dict__, "pnl_usd": pnl, "exit_price": last["close"], "reason": "end_of_data"})

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame({"timestamp": eq_ts, "equity": eq_values})
        metrics = compute_metrics(trades_df, equity_df, INITIAL_CAPITAL)
        return metrics, trades_df, equity_df

    metrics_ens, trades_ens, equity_ens = backtest_ensemble(combined)

    # --- Mostrar resultados ---
    print("\n" + "=" * 58)
    print("  RESULTADOS")
    print("=" * 58)

    def print_metrics(name, m):
        print(f"\n[{name}]")
        print(f"  Trades              : {m['total_trades']}")
        print(f"  Win Rate            : {m['win_rate_pct']:.2f}%")
        print(f"  Profit Factor       : {m['profit_factor']:.2f}")
        print(f"  Retorno total       : {m['total_return_pct']:.2f}%")
        print(f"  Max Drawdown        : {m['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe              : {m['sharpe_approx']:.2f}")
        print(f"  Avg Win/Loss        : ${m['avg_win_usd']:.4f} / ${m['avg_loss_usd']:.4f}")
        print(f"  Capital final       : ${m['final_equity']:.2f}")

    print_metrics("EMA Trend (baseline)", metrics_ema)
    print_metrics("VWAP Mean Reversion (TP fijo=VWAP entrada)", metrics_vwap)
    print_metrics("VWAP Mean Reversion (TP dinámico=VWAP actual)", metrics_vwap_dyn)
    print_metrics("Donchian Breakout (ADX>25, RR 1:3)", metrics_donchian)
    print_metrics("ENSEMBLE EMA + VWAP (1 posicion a la vez)", metrics_ens)

    # Guardar resultados
    trades_ema.to_csv("trades_backtest_ema.csv", index=False)
    trades_vwap.to_csv("trades_backtest_vwap.csv", index=False)
    trades_ens.to_csv("trades_backtest_ensemble.csv", index=False)
    trades_donchian.to_csv("trades_backtest_donchian.csv", index=False)
    print("\nCSV guardados: trades_backtest_ema.csv, trades_backtest_vwap.csv, trades_backtest_donchian.csv, trades_backtest_ensemble.csv")


if __name__ == "__main__":
    main()
