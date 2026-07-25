#!/usr/bin/env python3
"""Quick test: load BCH H1 CSV and inspect format."""
import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

from data_feed import load_from_csv

path = "/workspaces/TradingAIProject/data/historical/BCHUSDm_H1_202110271700_202607232100.csv"
df = load_from_csv(path)
print(f"Loaded rows: {len(df)}")
print(df.head())
print(df.dtypes)
print("Columns:", df.columns.tolist())
