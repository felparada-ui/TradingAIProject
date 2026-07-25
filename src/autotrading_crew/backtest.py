"""
Backtesting del Sistema Multi-Agente de Autotrading.

Simula el comportamiento completo de la Crew usando datos históricos
descargados o generados, permitiendo validar la lógica de decisión
antes del live-testing en demo de MT5.

Genera reportes automáticos con:
  - Win Rate
  - Sharpe Ratio
  - Máximo Drawdown
  - Profit Factor
  - Distribución de señales por régimen
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.autotrading_crew import tools as crew_tools
from src.autotrading_crew.regime_detector import RegimeDetector, MarketRegime
from src.autotrading_crew.risk_manager import RiskManager
from src.autotrading_crew.data_provider import DataProvider
from src.autotrading_crew.strategies import breakout, mean_reversion, momentum

# Dispatch de estrategias por régimen
STRATEGIES = {
    "tendencia": breakout,
    "rango": mean_reversion,
    "alta_volatilidad": momentum,
}

logger = logging.getLogger(__name__)


# ============================================================================
#  GENERADOR DE DATOS HISTÓRICOS SIMULADOS
# ============================================================================

def generate_historical_data(
    symbol: str,
    days: int = 365,
    timeframe: str = "1h",
    seed: int = 42,
    regime_bias: str = None,
) -> pd.DataFrame:
    """
    Genera datos OHLCV sintéticos con CAMBIOS DE RÉGIMEN explícitos.

    Los datos contienen períodos de:
      - Tendencia alcista/bajista (breakout)
      - Lateralización (rango / mean reversion)
      - Alta volatilidad (momentum)

    Args:
        regime_bias: Si se especifica ('trend', 'range', 'high_vol'), fuerza
                     el régimen dominante en los datos.
    """
    np.random.seed(seed + hash(symbol) % 1000)

    n_bars = days * (24 if timeframe == "1h" else 96 if timeframe == "15min" else 288)
    # Precios base realistas por activo
    base_prices = {"EUR/USD": 1.08, "BTC/USD": 45000, "SPY": 480, "BCH/USD": 350,
                   "IWM": 200, "QQQ": 380, "GBP/USD": 1.26, "ETH/USD": 2800}
    base_price = base_prices.get(symbol.upper(), 100)

    # Volatilidad diaria realista (%)
    daily_vol_pct = {"EUR/USD": 0.005, "GBP/USD": 0.005, "BTC/USD": 0.025,
                     "ETH/USD": 0.030, "BCH/USD": 0.035, "SPY": 0.010,
                     "QQQ": 0.012, "IWM": 0.013}.get(symbol.upper(), 0.010)
    # Convertir a volatilidad por vela (1h) x3 para generar patrones tradeables
    vol_per_bar = daily_vol_pct / np.sqrt(24) * 3.0

    # Límites de precio realistas (no más de ±30% del base)
    price_min = base_price * 0.70
    price_max = base_price * 1.30

    # ─── Cambios de régimen en el tiempo ────────────────────────────
    n_segments = 8 + np.random.randint(0, 4)
    segment_len = n_bars // n_segments

    prices = np.zeros(n_bars)
    prices[0] = base_price
    current_price = base_price

    regime_log = []
    # Para reversión a la media en rango
    range_mean = base_price

    for seg in range(n_segments):
        start = seg * segment_len
        end = min(start + segment_len, n_bars)
        seg_bars = end - start

        # Determinar régimen de este segmento
        if regime_bias:
            chosen = regime_bias
        else:
            cycle_pos = (seg % 6)
            if cycle_pos < 2:
                chosen = "trend"
            elif cycle_pos < 4:
                chosen = "range"
            else:
                chosen = "high_vol"

        regime_log.append(chosen)

        if chosen == "trend":
            # Tendencia direccional suave
            direction = 1 if np.random.random() > 0.35 else -1
            drift = direction * vol_per_bar * 0.5
            vol = vol_per_bar * 0.8
        elif chosen == "range":
            # Reversión a la media — oscila alrededor del nivel actual
            drift = 0.0
            vol = vol_per_bar * 0.5
            range_mean = current_price
        else:  # high_vol
            # Alta volatilidad con posible breakout
            direction = 1 if np.random.random() > 0.4 else -1
            drift = direction * vol_per_bar * 1.0
            vol = vol_per_bar * 2.0

        for i in range(seg_bars):
            idx = start + i
            if idx >= n_bars:
                break

            if chosen == "range":
                # Reversión a la media hacia range_mean
                deviation = (current_price - range_mean) / range_mean
                mean_revert = -deviation * 0.01  # Fuerza de reversión
                ret = np.random.randn() * vol + mean_revert
            else:
                ret = np.random.randn() * vol + drift

            # Ocasionalmente gaps pequeños (noticias)
            if np.random.random() < 0.003:
                ret += np.random.randn() * vol * 2

            current_price = current_price * (1 + ret)
            # Mantener dentro de rangos realistas
            if current_price < price_min:
                current_price = price_min * 1.001
            if current_price > price_max:
                current_price = price_max * 0.999
            prices[idx] = current_price

    # Rellenar precios restantes (si n_bars no es múltiplo exacto)
    for i in range(n_bars):
        if prices[i] == 0:
            prices[i] = prices[i - 1] if i > 0 else base_price

    # Construir OHLCV realista
    spreads = prices * np.random.uniform(0.0001, 0.003, n_bars)
    daily_vol = np.abs(np.diff(prices, prepend=prices[0])) * 0.5
    highs = prices + daily_vol + np.abs(np.random.randn(n_bars) * spreads * 0.3)
    lows = prices - daily_vol - np.abs(np.random.randn(n_bars) * spreads * 0.3)
    volumes = np.random.randint(500, 50000, n_bars)

    dates = pd.date_range(
        end=datetime.now(),
        periods=n_bars,
        freq=timeframe.replace("min", "min").replace("h", "h"),
    )

    df = pd.DataFrame({
        "open": prices,
        "high": np.maximum(highs, prices * 1.001),
        "low": np.minimum(lows, prices * 0.999),
        "close": prices,
        "volume": volumes,
    }, index=dates)

    df["regime_segments"] = str(regime_log)
    return df


# ============================================================================
#  SIMULADOR DE BACKTEST
# ============================================================================

class BacktestSimulator:
    """
    Simula el pipeline completo de la Crew con datos históricos.
    """

    def __init__(self, config: dict, symbols: list[str] = None):
        self.config = config
        self.symbols = symbols or ["EUR/USD", "BTC/USD", "SPY"]
        self.regime_detector = RegimeDetector(config)
        self.risk_manager = RiskManager(config)
        self.data_provider = DataProvider(config)
        self.trades: list[dict] = []
        self.equity_curve: list[float] = [config.get("general", {}).get("capital_inicial", 10000)]
        self.capital = self.equity_curve[0]

    def run(self, days: int = 180, use_real_data: bool = False) -> dict:
        """
        Ejecuta backtest sobre N días de datos históricos.

        Args:
            days: Días de historia
            use_real_data: Si True, intenta CCRT/CSV antes de sintético
        """
        print(f"\n{'='*60}")
        print(f"  📊 BACKTEST — {days} días en {len(self.symbols)} activos")
        if use_real_data:
            print(f"  🌐 Fuente: CCXT/CSV (con fallback sintético)")
        else:
            print(f"  ⚙️  Fuente: datos sintéticos")
        print(f"{'='*60}")

        # Generar datos para cada símbolo
        market_data = {}
        for symbol in self.symbols:
            print(f"   Cargando datos para {symbol}...")
            if use_real_data:
                df = self.data_provider.fetch_ohlcv(symbol, "1h", days)
            else:
                df = self.data_provider._generate_synthetic(symbol, days, "1h")
            if df is not None:
                market_data[symbol] = df
            else:
                print(f"   ⚠️  Sin datos para {symbol} — omitiendo")
                continue

        # Iterar sobre el periodo de backtest (cada 5 velas = ~5h en H1)
        step = 5
        total_bars = min(len(df) for df in market_data.values())
        signals_generated = 0
        trades_executed = 0
        last_progress = 0

        for i in range(200, total_bars, step):
            # Mostrar progreso cada 10%
            pct = (i - 200) / (total_bars - 200) * 100
            if pct - last_progress >= 10:
                last_progress = pct
                print(f"   Progreso: {pct:.0f}% | Señales: {signals_generated} | Trades: {trades_executed}")
            # ─── FASE 1: DETECTAR RÉGIMEN ────────────────────────────────
            regimes = {}
            for symbol in self.symbols:
                df_window = market_data[symbol].iloc[:i]
                regime = self.regime_detector.detect(df_window)
                regimes[symbol] = regime

            # Seleccionar el mejor activo (el de régimen más definido)
            best_symbol = max(
                regimes,
                key=lambda s: regimes[s]["confidence"] + (
                    50 if regimes[s]["regime"] != MarketRegime.UNDEFINED else 0
                ),
            )
            best_regime = regimes[best_symbol]

            if best_regime["regime"] == MarketRegime.UNDEFINED:
                continue

            # ─── FASE 2: GENERAR SEÑAL TÉCNICA ────────────────────────────
            df = market_data[best_symbol].iloc[:i]
            close = df["close"].values
            high = df["high"].values
            low = df["low"].values

            # Seleccionar estrategia según régimen (dispatch directo)
            strategy_name = best_regime["regime_name"]
            strategy_module = STRATEGIES.get(strategy_name, breakout)
            signal = strategy_module.generate_entry_signal(df, self.config)

            if signal["signal"] == "NEUTRAL":
                continue

            signals_generated += 1

            # ─── FASE 3: VALIDAR RIESGO ────────────────────────────────────
            atr = signal.get("atr", 0)
            validation = self.risk_manager.validate_risk_limits(
                side=signal["signal"],
                entry=signal["entry"],
                sl=signal["stop_loss"],
                tp=signal["take_profit"],
                atr=atr,
                symbol=best_symbol,
            )

            if not validation["approved"]:
                continue

            # Calcular tamaño de posición
            pos_size = self.risk_manager.calculate_position_size(
                entry_price=signal["entry"],
                stop_loss=signal["stop_loss"],
                atr=atr,
            )

            if "error" in pos_size:
                continue

            # ─── SIMULAR EJECUCIÓN ─────────────────────────────────────────
            # Buscar precio de salida en las próximas velas
            lookahead = min(i + 30, total_bars)
            future_df = market_data[best_symbol].iloc[i:lookahead]
            entry_price = signal["entry"]
            sl_price = signal["stop_loss"]
            tp_price = signal["take_profit"]

            exit_price = None
            exit_reason = "holding"
            exit_idx = i

            for j in range(len(future_df)):
                bar = future_df.iloc[j]
                if signal["signal"] == "BUY":
                    if bar["low"] <= sl_price:
                        exit_price = sl_price
                        exit_reason = "stop_loss"
                        exit_idx = i + j
                        break
                    if bar["high"] >= tp_price:
                        exit_price = tp_price
                        exit_reason = "take_profit"
                        exit_idx = i + j
                        break
                else:
                    if bar["high"] >= sl_price:
                        exit_price = sl_price
                        exit_reason = "stop_loss"
                        exit_idx = i + j
                        break
                    if bar["low"] <= tp_price:
                        exit_price = tp_price
                        exit_reason = "take_profit"
                        exit_idx = i + j
                        break

            # Si no se ejecutó SL/TP, cerrar al final de la ventana
            if exit_price is None:
                exit_price = future_df.iloc[-1]["close"]
                exit_reason = "time_exit"
                exit_idx = i + len(future_df) - 1

            # Calcular PnL bruto
            if signal["signal"] == "BUY":
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - exit_price) / entry_price

            gross_pnl = pnl_pct * pos_size.get("position_value", entry_price)
            actual_units = pos_size.get("units", 1)
            lot_size = pos_size.get("lot_size", actual_units / 1000)

            # ─── Calcular swap (overnight fee) ─────────────────────────────
            bars_held = (exit_idx - i)  # velas de 1h
            days_held = bars_held / 24.0

            # Tasa de swap según tipo de activo
            riesgo_cfg = self.config.get("riesgo", {})
            if any(c in best_symbol.upper() for c in ["BTC", "ETH", "SOL", "BCH", "LTC", "XRP"]):
                swap_rate = riesgo_cfg.get("swap_diario_crypto", 0.50)
            elif any(c in best_symbol.upper() for c in ["SPY", "QQQ", "IWM", "DIA"]):
                swap_rate = riesgo_cfg.get("swap_diario_etf", 0.10)
            else:
                swap_rate = riesgo_cfg.get("swap_diario_forex", 0.15)

            swap_cost = -days_held * swap_rate * lot_size
            net_pnl = gross_pnl + swap_cost

            trade = {
                "symbol": best_symbol,
                "side": signal["signal"],
                "regime": strategy_name,
                "entry_time": str(df["timestamp"].iloc[-1]) if "timestamp" in df.columns else str(df.index[-1]),
                "exit_time": str(market_data[best_symbol]["timestamp"].iloc[exit_idx]) if "timestamp" in market_data[best_symbol].columns else str(market_data[best_symbol].index[exit_idx]),
                "entry_price": round(entry_price, 5),
                "exit_price": round(exit_price, 5),
                "stop_loss": round(sl_price, 5),
                "take_profit": round(tp_price, 5),
                "units": actual_units,
                "lot_size": round(lot_size, 2),
                "pnl_pct": round(pnl_pct * 100, 2),
                "pnl_usd": round(gross_pnl, 2),
                "swap_usd": round(swap_cost, 2),
                "net_pnl_usd": round(net_pnl, 2),
                "days_held": round(days_held, 1),
                "bars_held": bars_held,
                "exit_reason": exit_reason,
                "confidence": signal.get("confidence", 50),
                "rr_ratio": validation.get("rr", 0),
            }
            self.trades.append(trade)
            self.capital += net_pnl  # Usar neto (con swap)
            self.equity_curve.append(self.capital)
            trades_executed += 1

            if trades_executed % 10 == 0:
                print(f"   ... {trades_executed} trades ejecutados (equity: ${self.capital:.2f})")

        return self._generate_report(signals_generated, trades_executed)

    def _generate_report(self, total_signals: int, total_trades: int) -> dict:
        """Genera el reporte final de rendimiento."""
        print(f"\n{'='*60}")
        print(f"  📈 REPORTE DE BACKTEST")
        print(f"{'='*60}")

        if not self.trades:
            print("   No se ejecutaron trades.")
            return {}

        df_trades = pd.DataFrame(self.trades)
        equity = pd.Series(self.equity_curve)

        # Usar net_pnl_usd si existe, sino pnl_usd (backward compat)
        pnl_col = "net_pnl_usd" if "net_pnl_usd" in df_trades.columns else "pnl_usd"

        # Métricas básicas (con swap incluido)
        total_pnl = df_trades[pnl_col].sum()
        total_swap = df_trades["swap_usd"].sum() if "swap_usd" in df_trades.columns else 0
        wins = df_trades[df_trades[pnl_col] > 0]
        losses = df_trades[df_trades[pnl_col] < 0]
        win_rate = len(wins) / len(df_trades) * 100 if len(df_trades) > 0 else 0

        avg_win = wins[pnl_col].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses[pnl_col].mean()) if len(losses) > 0 else 1
        profit_factor = abs(wins[pnl_col].sum() / losses[pnl_col].sum()) if len(losses) > 0 and losses[pnl_col].sum() != 0 else float("inf")

        # Drawdown
        peak = equity.cummax()
        drawdown = (equity - peak) / peak * 100
        max_drawdown = drawdown.min()

        # Sharpe Ratio
        returns = df_trades["pnl_pct"] / 100
        sharpe = np.sqrt(252 * 24) * returns.mean() / returns.std() if returns.std() > 0 else 0

        # Distribución por régimen
        regime_stats = {}
        for regime in df_trades["regime"].unique():
            subset = df_trades[df_trades["regime"] == regime]
            regime_wins = subset[subset[pnl_col] > 0]
            regime_stats[regime] = {
                "trades": len(subset),
                "win_rate": round(len(regime_wins) / len(subset) * 100, 1),
                "pnl_usd": round(subset[pnl_col].sum(), 2),
                "swap_usd": round(subset["swap_usd"].sum(), 2) if "swap_usd" in subset.columns else 0,
            }

        report = {
            "periodo": f"{len(self.equity_curve) * 5} velas",
            "capital_inicial": round(self.equity_curve[0], 2),
            "capital_final": round(self.capital, 2),
            "retorno_total_pct": round((self.capital - self.equity_curve[0]) / self.equity_curve[0] * 100, 2),
            "total_signals": total_signals,
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "best_trade_usd": round(df_trades[pnl_col].max(), 2),
            "worst_trade_usd": round(df_trades[pnl_col].min(), 2),
            "total_swap_usd": round(total_swap, 2),
            "regimen_stats": regime_stats,
            "trades": self.trades,
        }

        # Imprimir resumen
        swap_line = f" | Swap: ${total_swap:.2f}" if total_swap != 0 else ""
        print(f"   Capital: ${report['capital_inicial']:.2f} → ${report['capital_final']:.2f}")
        print(f"   Retorno: {report['retorno_total_pct']:+.2f}%{swap_line}")
        print(f"   Trades:  {report['total_trades']} ({report['win_rate_pct']:.1f}% win rate)")
        print(f"   PF:      {report['profit_factor']:.2f}")
        print(f"   Sharpe:  {report['sharpe_ratio']:.2f}")
        print(f"   DD Máx:  {report['max_drawdown_pct']:.2f}%")
        print(f"\n   Desglose por régimen:")
        for regime, stats in regime_stats.items():
            print(f"     • {regime:20s}: {stats['trades']} trades | "
                  f"{stats['win_rate']}% WR | ${stats['pnl_usd']:+.2f}")

        # Guardar reporte a archivo
        report_dir = self.config.get("logging", {}).get("reportes_dir", "data/backtest_results/")
        os.makedirs(report_dir, exist_ok=True)
        report_file = os.path.join(report_dir, f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n   📁 Reporte guardado: {report_file}")

        return report


# ============================================================================
#  PUNTO DE ENTRADA
# ============================================================================

def run_backtest(config: dict):
    """Ejecuta el backtest y muestra resultados."""
    simulator = BacktestSimulator(config)
    report = simulator.run(days=180)

    if not report:
        print("\n❌ Backtest completado sin resultados.")

    return report


if __name__ == "__main__":
    # Ejecución directa para pruebas
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "config", "config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    crew_tools.initialize(cfg)
    run_backtest(cfg)
