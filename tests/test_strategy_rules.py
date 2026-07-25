import pandas as pd
from types import SimpleNamespace

from strategies.ema_trend_scalping import generate_signals


def build_trend_frame() -> pd.DataFrame:
    times = pd.date_range("2024-01-01 00:00:00", periods=260, freq="5min", tz="UTC")
    close = 100.0
    rows = []
    for i, ts in enumerate(times):
        if i < 80:
            close += 0.2
        elif i < 160:
            close += 0.5
        else:
            close += 0.3
        open_ = close - 0.1
        high = close + 0.5
        low = close - 0.5
        rows.append({
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000,
        })
    return pd.DataFrame(rows)


def test_generate_signals_adds_multitimeframe_context():
    df = build_trend_frame()
    cfg = SimpleNamespace(
        ema_fast=9,
        ema_slow=21,
        ema_trend=200,
        adx_period=14,
        adx_threshold=20.0,
        atr_period=14,
        session_hours_utc=list(range(8, 21)),
        trading_days=[0, 1, 2, 3, 4],
        donchian_period=20,
    )

    out = generate_signals(df, cfg)

    assert "trend_context" in out.columns
    assert "entry_quality" in out.columns
    assert out["signal"].abs().sum() > 0
