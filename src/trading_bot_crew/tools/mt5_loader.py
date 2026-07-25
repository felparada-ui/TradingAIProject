import pandas as pd
import numpy as np
from ta import add_all_ta_features
from ta.trend import MACD, EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
import os
from typing import Dict, Any

class MT5DataLoader:
    """
    Herramienta para cargar datos históricos exportados desde MT5
    y calcular indicadores técnicos.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = None
        self.indicators = []
        
    def load_data(self) -> pd.DataFrame:
        """Carga el archivo CSV y prepara los datos"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.file_path}")
        
        df = pd.read_csv(self.file_path)
        df.columns = df.columns.str.lower().str.strip()
        
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                for real_col in df.columns:
                    if col in real_col:
                        df.rename(columns={real_col: col}, inplace=True)
                        break
        
        if 'time' in df.columns or 'date' in df.columns:
            time_col = 'time' if 'time' in df.columns else 'date'
            df['datetime'] = pd.to_datetime(df[time_col])
            df.set_index('datetime', inplace=True)
        
        self.data = df
        return df
    
    def add_indicators(self, df: pd.DataFrame = None) -> pd.DataFrame:
        """Agrega indicadores técnicos al DataFrame"""
        if df is None:
            df = self.data
        if df is None:
            raise ValueError("Primero debes cargar los datos con load_data()")
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                raise ValueError(f"Columna '{col}' no encontrada en los datos")
        
        df = add_all_ta_features(
            df, 
            open="open", high="high", low="low", 
            close="close", volume="volume",
            fillna=True
        )
        
        df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()
        
        macd = MACD(close=df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        bollinger = BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_high'] = bollinger.bollinger_hband()
        df['bb_mid'] = bollinger.bollinger_mavg()
        df['bb_low'] = bollinger.bollinger_lband()
        df['bb_width'] = bollinger.bollinger_wband()
        df['bb_percent'] = bollinger.bollinger_pband()
        
        df['ema_9'] = EMAIndicator(close=df['close'], window=9).ema_indicator()
        df['ema_21'] = EMAIndicator(close=df['close'], window=21).ema_indicator()
        df['ema_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
        
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        df['volatility'] = df['returns'].rolling(20).std() * np.sqrt(252)
        
        self.indicators = [col for col in df.columns if col not in ['open', 'high', 'low', 'close', 'volume']]
        self.data = df
        return df
    
    def get_statistics(self) -> Dict[str, Any]:
        """Devuelve estadísticas de los datos cargados"""
        if self.data is None:
            raise ValueError("Primero debes cargar datos con load_data()")
        
        df = self.data
        stats = {
            "total_rows": len(df),
            "start_date": str(df.index[0]) if hasattr(df.index, '__getitem__') else "N/A",
            "end_date": str(df.index[-1]) if hasattr(df.index, '__getitem__') else "N/A",
            "price_range": {
                "min": float(df['close'].min()),
                "max": float(df['close'].max()),
                "mean": float(df['close'].mean()),
                "std": float(df['close'].std())
            },
            "returns": {
                "mean": float(df.get('returns', pd.Series([0])).mean()),
                "std": float(df.get('returns', pd.Series([0])).std())
            },
            "volatility": float(df.get('volatility', pd.Series([0])).mean()),
            "total_volume": float(df['volume'].sum()),
            "max_drawdown": self._calculate_max_drawdown(df.get('returns', pd.Series([0]))),
            "indicators_count": len(self.indicators),
            "indicators": self.indicators[:10]
        }
        return stats
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        if returns.empty:
            return 0.0
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return float(drawdown.min())
    
    def get_sample_data(self, n: int = 100) -> pd.DataFrame:
        if self.data is None:
            raise ValueError("Primero debes cargar datos con load_data()")
        return self.data.head(n)
