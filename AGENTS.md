# AI Agent Guidance for TradingAIProject

## Purpose
This repository contains Python-based trading pipelines built around CrewAI agents and historical market data analysis. Use this file to understand where the main entrypoints are, how training and execution pipelines are structured, and which files to edit for agent behavior.

## Key project entrypoints
- `python src/trading_bot_crew/main.py` — main CrewAI trading bot pipeline with live/analysis/backtest tasks.
- `python src/pro_trader_crew/main.py` — non-LLM pipeline for scheduled multi-strategy index trading.
- `python src/strategy_hunter_crew/main.py` — strategy discovery and validation pipeline.
- `python src/autotrading_crew/main.py` — advanced multi-agent autotrading system with 5 specialized agents and regime-switching.
- `python src/autotrading_crew/main.py --mode backtest` — backtesting mode (synthetic data).
- `python src/autotrading_crew/main.py --mode backtest --real` — backtesting with REAL data (CCXT Binance + CSV).
- `python src/autotrading_crew/main.py --mode live` — live mode with MT5 connection + Telegram notifications.
- `python src/autotrading_crew/main.py --mode llm` — LLM-powered CrewAI mode (requires OPENAI_API_KEY).
- `python src/autotrading_crew/main.py --dashboard` — launch Streamlit monitoring dashboard.
- `streamlit run src/autotrading_crew/dashboard.py` — standalone dashboard.
- `python scripts/diagnostico_mt5.py` — MT5 connection diagnostic (run on Windows).
- `python src/autotrading_crew/run_scenarios.py` — full scenario suite (10 escenarios).

## Environment and dependencies
- Python version: `>=3.11` as declared in `pyproject.toml`.
- Project dependencies are declared in `pyproject.toml`; `requirements.txt` is also present for environment installation.
- Use a `.env` file to configure secrets, especially `OPENAI_API_KEY` for LLM-enabled flows.

## Project structure
- `src/trading_bot_crew/` — main trading Crew pipeline and task definitions.
- `src/pro_trader_crew/` — pro trader pipeline and multi-strategy execution tasks.
- `src/strategy_hunter_crew/` — strategy search, cross-asset validation, and portfolio curation.
- `src/autotrading_crew/` — advanced multi-agent autotrading system with 5 agents, regime detection, and adaptive strategies.
  - `data_provider.py` — multi-source data (CCXT real / CSV / synthetic)
  - `sentiment_real.py` — NewsAPI real sentiment (with simulated fallback)
  - `dashboard.py` — Streamlit monitoring dashboard
  - `execution_trader.py` — MT5 connector with auto-reconnect
  - `regime_detector.py` — ADX/BB/ATR/Efficiency Ratio regime classification
  - `risk_manager.py` — Kelly sizing, VaR, circuit breaker, trailing stop
  - `backtest.py` — backtesting engine (supports real & synthetic data)
  - `strategies/` — breakout (trend), mean_reversion (range), momentum (high vol)
- `config/agents.yaml` (inside each crew folder) — agent metadata, goals, backstories, and tool mappings.
- `data/` — historical market data, backtest outputs, and models.
- `logs/` — execution logs and trading logs.
- `tests/` — Python `unittest` test cases.

## Important conventions for AI coding agents
- Preserve the CrewAI pipeline structure. Each crew directory defines a set of agents in YAML and maps them to tool functions in `main.py`.
- Respect the `.env` dependency for LLM-enabled pipelines; if `OPENAI_API_KEY` is absent, some modules fall back to non-LLM/autonomous mode.
- Do not assume a frontend or web server; this repo is CLI and script driven.
- Prefer editing tool/task implementations in `src/*_crew/tasks.py` over changing agent orchestration in `main.py` unless the work is about orchestration.

## Running tests
- Use the repository test suite with Python `unittest`:
  - `python -m unittest tests/test_strategy_optimizer.py`
  - `python -m unittest discover tests`

## Notes for reviewers
- `README.md` is the canonical quick start document.
- `pyproject.toml` is the authoritative dependency and packaging file.
- `requirements.txt` is present and may be used for installations in the current environment.
- `scripts/crontab.txt` documents scheduled runs for `src/pro_trader_crew/main.py`.

## When editing
- If adding new agent behavior, update the corresponding `config/agents.yaml` and tool mapping in `main.py`.
- If adding a new strategy or backtest variant, place it in `strategies/` or `src/*_crew/tasks.py` depending on whether it is a reusable tool.
- Keep string literals and log messages in English or Spanish consistently in the same module.
