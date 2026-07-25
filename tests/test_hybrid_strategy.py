import unittest

import pandas as pd
import numpy as np

from config import StrategyConfig
from strategies.ema_trend_scalping import generate_signals


class HybridStrategyTest(unittest.TestCase):
    def test_hybrid_mode_adds_context_columns(self):
        timestamps = pd.date_range("2024-01-01 00:00:00", periods=260, freq="5min")
        close = np.linspace(100, 140, len(timestamps))
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": 1000,
        })

        cfg = StrategyConfig()
        cfg.timeframe = "5m"
        cfg.hybrid_strategy_enabled = True
        cfg.context_timeframe = "1h"

        out = generate_signals(df, cfg)

        self.assertIn("context_trend", out.columns)
        self.assertIn("context_signal_confirm", out.columns)


if __name__ == "__main__":
    unittest.main()
