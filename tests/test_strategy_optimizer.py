import unittest
from copy import deepcopy

from config import StrategyConfig
from strategy_optimizer import build_candidate_configs


class StrategyOptimizerTest(unittest.TestCase):
    def test_build_candidate_configs_returns_expected_combinations(self):
        base = StrategyConfig()
        base.timeframe = "1h"
        base.session_start_local = "08:30"
        base.session_end_local = "23:30"

        candidates = build_candidate_configs(
            base,
            adx_thresholds=[18.0, 22.0],
            atr_tp_mults=[2.0, 2.5],
        )

        self.assertEqual(len(candidates), 4)
        self.assertEqual(candidates[0].adx_threshold, 18.0)
        self.assertEqual(candidates[0].atr_tp_mult, 2.0)
        self.assertEqual(candidates[-1].adx_threshold, 22.0)
        self.assertEqual(candidates[-1].atr_tp_mult, 2.5)
        self.assertEqual(candidates[0].timeframe, "1h")


if __name__ == "__main__":
    unittest.main()
