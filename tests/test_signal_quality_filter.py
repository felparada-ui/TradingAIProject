import unittest

import numpy as np
import pandas as pd

from config import StrategyConfig
from strategies.ema_trend_scalping import generate_signals


class SignalQualityFilterTest(unittest.TestCase):
    def test_signal_column_exists(self):
        timestamps = pd.date_range("2024-01-01 08:00:00", periods=400, freq="h")
        close = np.linspace(100, 160, len(timestamps))
        open_ = close - 0.05
        high = close + 0.8
        low = close - 0.8
        volume = np.ones(len(timestamps)) * 1000

        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })

        cfg = StrategyConfig()
        cfg.strategy_type = "macd_cross"
        cfg.session_hours_utc = list(range(0, 24))
        cfg.trading_days = [0, 1, 2, 3, 4]
        cfg.adx_threshold = 20.0
        cfg.atr_tp_mult = 3.0
        cfg.use_trailing_stop = False

        out = generate_signals(df, cfg)

        self.assertIn("signal", out.columns)


if __name__ == "__main__":
    unittest.main()
