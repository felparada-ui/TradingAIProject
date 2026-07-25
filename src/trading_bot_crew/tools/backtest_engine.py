import pandas as pd
import numpy as np
from typing import Dict, Any, List, Callable
import warnings
warnings.filterwarnings('ignore')

class BacktestEngine:
    def __init__(self, data: pd.DataFrame, initial_capital: float = 10000.0):
        self.data = data.copy()
        self.initial_capital = initial_capital
        self.results = {}
        self.trades = []
        
    def run_strategy(self, signal_func: Callable, **kwargs) -> Dict[str, Any]:
        self.data['signal'] = signal_func(self.data, **kwargs)
        self.data['position'] = self.data['signal'].diff().fillna(0)
        self.data['returns'] = self.data['close'].pct_change()
        self.data['strategy_returns'] = self.data['signal'].shift(1) * self.data['returns']
        self.data['equity'] = self.initial_capital * (1 + self.data['strategy_returns'].cumsum())
        self._record_trades()
        self.results = self._calculate_metrics()
        self.results['trades'] = self.trades
        self.results['equity_curve'] = self.data[['equity']]
        return self.results
    
    def _record_trades(self):
        position_changes = self.data[self.data['position'] != 0].copy()
        for idx, row in position_changes.iterrows():
            if row['position'] == 1:
                trade = {'entry_time': idx, 'entry_price': row['close'], 'position': 'long'}
                self.trades.append(trade)
            elif row['position'] == -1:
                if self.trades and self.trades[-1].get('exit_time') is None:
                    trade = self.trades[-1]
                    trade['exit_time'] = idx
                    trade['exit_price'] = row['close']
                    trade['return'] = (trade['exit_price'] - trade['entry_price']) / trade['entry_price']
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        returns = self.data['strategy_returns'].dropna()
        equity = self.data['equity'].dropna()
        if returns.empty:
            return {'error': 'No hay retornos para calcular métricas'}
        
        total_return = float(equity.iloc[-1] / self.initial_capital - 1)
        annual_volatility = float(returns.std() * np.sqrt(252))
        sharpe_ratio = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        
        cumulative_returns = (1 + returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = float(drawdown.min())
        
        if self.trades:
            trade_returns = [t.get('return', 0) for t in self.trades if 'return' in t]
            winning_trades = sum(1 for r in trade_returns if r > 0)
            win_rate = float(winning_trades / len(trade_returns)) if trade_returns else 0
            gross_profit = sum(r for r in trade_returns if r > 0)
            gross_loss = abs(sum(r for r in trade_returns if r < 0))
            profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float('inf')
            avg_win = float(np.mean([r for r in trade_returns if r > 0])) if trade_returns else 0
            avg_loss = float(np.mean([r for r in trade_returns if r < 0])) if trade_returns else 0
            ratio_avg_win_loss = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        else:
            trade_returns = []
            win_rate = 0
            profit_factor = 0
            avg_win = 0
            avg_loss = 0
            ratio_avg_win_loss = 0
        
        return {
            'total_return': total_return,
            'annual_volatility': annual_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'ratio_avg_win_loss': ratio_avg_win_loss,
            'initial_capital': self.initial_capital,
            'final_equity': float(equity.iloc[-1])
        }
