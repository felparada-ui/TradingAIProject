"""
Paper Trading — Un solo ciclo de la estrategia MACD Cross 1H.
Descarga datos, analiza, y reporta por Telegram sin loop infinito.
Ideal para probar que todo funciona antes del paper trading continuo.
"""

import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

import ccxt
import pandas as pd
import logging
from datetime import datetime, timezone

from config import STRATEGY
from strategies.ema_trend_scalping import generate_signals
from risk_manager import RiskManager
from notifications import notify_trade_open, notify_trade_close, notify_system_start

logging.basicConfig(level=logging.INFO)

def main():
    print("=" * 58)
    print("  PAPER TRADING — CICLO UNICO MACD CROSS 1H")
    print("=" * 58)

    # 1. Descargar datos
    print("\n📥 Descargando datos BCH/USDT 1H...")
    ex = ccxt.binance({"enableRateLimit": True})
    bars = ex.fetch_ohlcv("BCH/USDT", timeframe="1h", limit=300)
    df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"  {len(df)} velas descargadas")

    # 2. Calcular señales
    print("\n📊 Generando senales MACD Cross...")
    data = generate_signals(df, STRATEGY)
    data = data.dropna(subset=["ema_fast", "ema_slow", "ema_trend", "adx", "atr"]).reset_index(drop=True)
    
    # Ultimas 5 velas con senal
    signals = data[data["signal"] != 0]
    print(f"  Senales encontradas en total: {len(signals)}")

    # 3. Simular trades sobre datos historicos (backtest ligero)
    from backtest import run_backtest
    trades, equity, metrics = run_backtest(df, STRATEGY, initial_capital=200.0)

    print("\n📊 RESULTADOS DEL BACKTEST:")
    print(f"  Trades totales : {metrics.get('total_trades', 0)}")
    print(f"  Win Rate       : {metrics.get('win_rate_pct', 0):.1f}%")
    print(f"  Profit Factor  : {metrics.get('profit_factor', 0):.2f}")
    print(f"  Retorno Total  : {metrics.get('total_return_pct', 0):+.2f}%")
    print(f"  Drawdown Max   : {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Equity Final   : ${metrics.get('final_equity', 200):.2f}")

    # 4. Ver ultima senal detectada
    if not signals.empty:
        last_signal = signals.iloc[-1]
        print(f"\n📡 Ultima senal: {'LONG' if last_signal['signal'] == 1 else 'SHORT'}")
        print(f"  Fecha  : {last_signal['timestamp']}")
        print(f"  Precio : ${last_signal['close']:.2f}")
        print(f"  ADX    : {last_signal['adx']:.1f}")
        print(f"  MACD   : {last_signal['macd']:.2f}")

    # 5. Reportar por Telegram
    print("\n📤 Enviando reporte por Telegram...")
    from notifications import _send_message
    
    ret = metrics.get("total_return_pct", 0)
    pf = metrics.get("profit_factor", 0)
    wr = metrics.get("win_rate_pct", 0)
    dd = metrics.get("max_drawdown_pct", 0)
    eq = metrics.get("final_equity", 200)
    trades_n = metrics.get("total_trades", 0)
    
    msg = (
        f"<b>📊 REPORTE PAPER TRADING — MACD Cross 1H</b>\n\n"
        f"<b>📈 Rendimiento historico:</b>\n"
        f"  Trades: {trades_n} | Win Rate: {wr:.1f}%\n"
        f"  Profit Factor: {pf:.2f} | Retorno: {ret:+.2f}%\n"
        f"  Drawdown: {dd:.2f}% | Equity: ${eq:.2f}\n\n"
        f"<b>⚙️ Configuracion activa:</b>\n"
        f"  Estrategia: MACD Cross 1H\n"
        f"  Activo: BCH/USDT | Capital: $200\n"
        f"  SL: ATR*1.0 | TP: ATR*3.0 | Riesgo: 0.5%/trade\n\n"
        f"<b>📡 Ultima vela:</b>\n"
        f"  Precio: ${data['close'].iloc[-1]:.2f}\n"
        f"  ADX: {data['adx'].iloc[-1]:.1f} | MACD: {data['macd'].iloc[-1]:.2f}\n"
        f"  Senal actual: {'LONG' if data['signal'].iloc[-1]==1 else 'SHORT' if data['signal'].iloc[-1]==-1 else 'NEUTRO'}\n\n"
        f"<b>🟡 Modo PAPER — Sin dinero real</b>\n"
        f"<i>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
    )
    ok = _send_message(msg)
    print(f"  {'✅ Reporte enviado' if ok else '❌ Error al enviar'}")

    print("\n" + "=" * 58)
    print("  ✅ Ciclo completado")
    print("  Para ejecucion continua: python main_bot.py --mode paper")
    print("=" * 58)


if __name__ == "__main__":
    main()
