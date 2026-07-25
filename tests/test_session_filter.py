import unittest

import pandas as pd

from indicators import session_filter


class SessionFilterTest(unittest.TestCase):
    def test_session_filter_uses_chile_window(self):
        timestamps = pd.to_datetime([
            "2024-01-01 11:30:00",
            "2024-01-01 14:00:00",
            "2024-01-01 02:30:00",
            "2024-01-01 10:00:00",
            "2024-01-01 08:30:00",
            "2024-01-01 23:30:00",
        ])

        result = session_filter(
            timestamps,
            weekdays=[0, 1, 2, 3, 4],
            timezone_name="America/Santiago",
            start_local="08:30",
            end_local="23:30",
        )

        self.assertEqual(result.tolist(), [True, True, False, False, False, True])


if __name__ == "__main__":
    unittest.main()
