#!/usr/bin/env python3
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")
import pandas as pd
from data_feed import load_from_csv
from indicators import add_all_indicators
from config import STRATEGY

from strategies.ema_trend_scalping import generate_signals

path = "/workspaces/TradingAIProject/data/bch_usdt_h1.csv"
df = load_from_csv(path)
data = generate_signals(df, STRATEGY)
print(f"Rows: {len(data)}")
print(f"Signal counts: {(data['signal']!=0).sum()}")
print(f"In session: {data['in_session'].sum()}")
print(f"ADX > 20: {(data['adx']>20).sum()}")
print(f"Signal + in_session: {((data['signal']!=0) & data['in_session']).sum()}")
print(f"Signal + in_session + ADX>20: {((data['signal']!=0) & data['in_session'] & (data['adx']>20)).sum()}")
print("Sample signals:")
idx = data[data['signal']!=0].index[:5]
print(data.loc[idx, ['timestamp','close','ema_fast','ema_slow','ema_trend','adx','atr','in_session','signal']])
