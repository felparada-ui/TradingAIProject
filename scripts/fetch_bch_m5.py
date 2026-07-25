#!/usr/bin/env python3
"""Descarga velas OHLCV BCHUSDT M5 desde Binance Spot API pública."""
import requests
import pandas as pd
import time
from datetime import datetime, timezone

OUT = "/workspaces/TradingAIProject/data/bch_usdt_m5.csv"
SYMBOL = "BCHUSDT"
INTERVAL = "5m"
LIMIT = 1000
BASE = "https://api.binance.com/api/v3/klines"

start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
end_dt = datetime(2025, 7, 24, tzinfo=timezone.utc)

start_ms = int(start_dt.timestamp() * 1000)
end_ms = int(end_dt.timestamp() * 1000)

print(f"Descargando {SYMBOL} M5 desde {start_dt.date()} hasta {end_dt.date()} ...")

all_rows = []
cur = start_ms
while cur < end_ms:
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "startTime": cur,
        "endTime": end_ms,
        "limit": LIMIT,
    }
    for attempt in range(3):
        try:
            r = requests.get(BASE, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if not data:
                    print("Sin datos, fin.")
                    cur = end_ms
                    break
                all_rows.extend(data)
                last_open = data[-1][0]
                cur = last_open + 1
                print(f"  recibidas: {len(data)} velas | total: {len(all_rows)} | avance: {datetime.fromtimestamp(last_open/1000, tz=timezone.utc).isoformat()}")
                break
            else:
                print(f"HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(2)
    else:
        print("Fallos repetidos, abortando.")
        break
    time.sleep(0.2)

if not all_rows:
    print("No se descargaron velas.")
    exit(1)

cols = ["timestamp", "open", "high", "low", "close", "volume", "close_time",
        "quote_asset_volume", "number_of_trades", "taker_buy_base",
        "taker_buy_quote", "ignore"]
df = pd.DataFrame(all_rows, columns=cols)
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

num_cols = ["open", "high", "low", "close", "volume"]
df[num_cols] = df[num_cols].astype(float)

df = df[["timestamp", "open", "high", "low", "close", "volume"]].drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

print(f"\nVelas descargadas: {len(df)}")
print(f"Rango: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")
print(f"Guardando en {OUT}")
df.to_csv(OUT, index=False)
print("Listo.")
