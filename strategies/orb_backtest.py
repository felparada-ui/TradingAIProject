"""
Backtest especializado para ORB (Opening Range Breakout).
Usa SL/TP basados en el rango de apertura (no ATR).
"""

import pandas as pd
import numpy as np
import logging
from config import StrategyConfig
from strategies.orb_breakout import generate_orb_signals

logger = logging.getLogger(__name__)


def run_orb_backtest(
    df: pd.DataFrame,
    cfg,
    initial_capital: float = 10000.0,
) -> tuple:
    """
    Backtest para estrategia ORB en 15min.
    SL/TP se calculan desde el rango de apertura, no desde ATR.
    """
    data = generate_orb_signals(df, cfg)
    
    capital = initial_capital
    equity = initial_capital
    position = None
    trades = []
    
    eq_timestamps = []
    eq_values = []
    
    for i, row in data.iterrows():
        ts = row.get('timestamp', i)
        eq_timestamps.append(ts)
        eq_values.append(equity)
        
        # Gestionar posición abierta
        if position is not None:
            sl = position['stop_price']
            tp = position['take_profit']
            side = position['side']
            
            hit_stop = (row['low'] <= sl) if side == 1 else (row['high'] >= sl)
            hit_tp = (row['high'] >= tp) if side == 1 else (row['low'] <= tp)
            
            if hit_stop or hit_tp:
                exit_price = sl if hit_stop else tp
                reason = 'stop_loss' if hit_stop else 'take_profit'
                
                pnl = (exit_price - position['entry_price']) * position['size'] * side
                equity += pnl
                
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': ts,
                    'side': 'LONG' if side == 1 else 'SHORT',
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'size': position['size'],
                    'pnl_usd': round(pnl, 2),
                    'pnl_pct': round(pnl / (position['entry_price'] * position['size']) * 100, 2),
                    'reason': reason,
                    'entry_range_high': position.get('range_high'),
                    'entry_range_low': position.get('range_low'),
                })
                position = None
        
        # Evaluar nueva entrada
        if position is None and row['signal'] != 0:
            entry_price = row['close']
            side = row['signal']
            orb_sl = row.get('orb_sl', entry_price * 0.99)
            orb_tp = row.get('orb_tp', entry_price * 1.01)
            
            risk_per_trade = equity * getattr(cfg, 'risk_per_trade', 0.005)
            risk_distance = abs(entry_price - orb_sl)
            size = risk_per_trade / risk_distance if risk_distance > 0 else 0
            
            if size > 0:
                position = {
                    'side': side,
                    'entry_price': entry_price,
                    'stop_price': orb_sl,
                    'take_profit': orb_tp,
                    'size': size,
                    'entry_time': ts,
                    'range_high': row.get('orb_range_high'),
                    'range_low': row.get('orb_range_low'),
                }
    
    # Cerrar posición abierta al final
    if position is not None:
        last_row = data.iloc[-1]
        pnl = (last_row['close'] - position['entry_price']) * position['size'] * position['side']
        equity += pnl
        trades.append({
            'entry_time': position['entry_time'],
            'exit_time': last_row.get('timestamp', data.index[-1]),
            'side': 'LONG' if position['side'] == 1 else 'SHORT',
            'entry_price': position['entry_price'],
            'exit_price': last_row['close'],
            'size': position['size'],
            'pnl_usd': round(pnl, 2),
            'pnl_pct': round(pnl / (position['entry_price'] * position['size']) * 100, 2),
            'reason': 'end_of_data',
        })
    
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame({'timestamp': eq_timestamps, 'equity': eq_values})
    
    metrics = _compute_orb_metrics(trades_df, equity_df, initial_capital)
    
    return trades_df, equity_df, metrics


def _compute_orb_metrics(trades_df, equity_df, initial_capital):
    """Calcula métricas para backtest ORB."""
    if trades_df.empty:
        return {'total_trades': 0, 'message': 'Sin operaciones'}
    
    wins = trades_df[trades_df['pnl_usd'] > 0]
    losses = trades_df[trades_df['pnl_usd'] <= 0]
    
    final_equity = equity_df['equity'].iloc[-1]
    total_return = (final_equity - initial_capital) / initial_capital * 100
    
    gross_profit = wins['pnl_usd'].sum()
    gross_loss = abs(losses['pnl_usd'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    running_max = equity_df['equity'].cummax()
    drawdown = (equity_df['equity'] - running_max) / running_max
    max_dd = drawdown.min() * 100
    
    returns = equity_df['equity'].pct_change().dropna()
    sharpe = returns.mean() / returns.std() * np.sqrt(252 * 26) if returns.std() > 0 else 0  # 15min bars
    
    return {
        'total_trades': len(trades_df),
        'win_rate_pct': round(len(wins) / len(trades_df) * 100, 2),
        'profit_factor': round(profit_factor, 2),
        'total_return_pct': round(total_return, 2),
        'max_drawdown_pct': round(max_dd, 2),
        'sharpe_approx': round(sharpe, 2),
        'avg_win_usd': round(wins['pnl_usd'].mean(), 2) if len(wins) else 0,
        'avg_loss_usd': round(losses['pnl_usd'].mean(), 2) if len(losses) else 0,
        'final_equity': round(final_equity, 2),
    }
