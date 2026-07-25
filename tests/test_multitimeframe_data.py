import pandas as pd

from data_feed import resample_ohlcv_to_timeframe


def test_resample_ohlcv_to_hourly():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01 00:00:00", periods=6, freq="5min", tz="UTC"),
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103, 104],
            "close": [101, 102, 103, 104, 105, 106],
            "volume": [10, 20, 30, 40, 50, 60],
        }
    )

    hourly = resample_ohlcv_to_timeframe(df, "1h")

    assert len(hourly) == 1
    assert hourly.iloc[0]["open"] == 100
    assert hourly.iloc[0]["high"] == 106
    assert hourly.iloc[0]["low"] == 99
    assert hourly.iloc[0]["close"] == 106
    assert hourly.iloc[0]["volume"] == 210
