"""
Punto de entrada principal del sistema de trading.

Modos de uso:
  # Backtest completo con CSV local BTC/USDT H1
  python main_bot.py --mode backtest --csv btc_usdt_h1.csv

  # Backtest con rango de fechas (walk-forward)
  python main_bot.py --mode backtest --csv btc_usdt_h1.csv --date-from 2024-01-01 --date-to 2024-12-31

  # Paper trading en vivo (RECOMENDADO primero — sin dinero real)
  python main_bot.py --mode paper --capital 200

  # Trading en vivo REAL (solo con credenciales en .env)
  python main_bot.py --mode live --capital 200

  # Crew de agentes IA (ciclo horario)
  python main_bot.py --mode crew --cycle hourly

  # Test de conexion Telegram
  python main_bot.py --mode test-telegram
"""

import argparse
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/trading_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def run_backtest_mode(csv_path: str, capital: float, date_from: str, date_to: str):
    from config import STRATEGY
    from backtest import run_backtest_from_csv, plot_equity_curve

    print("\n" + "=" * 58)
    print("  BACKTEST  |  BCH/USDT 1H  |  EMA 5/13/150")
    print("=" * 58)

    if not Path(csv_path).exists():
        logger.error(f"CSV no encontrado: {csv_path}")
        sys.exit(1)

    trades_df, equity_df, metrics = run_backtest_from_csv(
        csv_path       = csv_path,
        cfg            = STRATEGY,
        initial_capital= capital,
        date_from      = date_from,
        date_to        = date_to,
    )

    print("\n  RESULTADOS:")
    print("=" * 58)
    labels = {
        "total_trades"           : "Total operaciones",
        "win_rate_pct"           : "Win Rate por trade (%)",
        "day_win_rate_pct"       : "Dias positivos (%)",
        "profit_factor"          : "Profit Factor",
        "total_return_pct"       : "Retorno total (%)",
        "monthly_return_avg_pct" : "Retorno mensual promedio (%)",
        "max_drawdown_pct"       : "Drawdown maximo (%)",
        "sharpe_approx"          : "Sharpe aprox. anualizado",
        "avg_win_usd"            : "Ganancia media/trade (USD)",
        "avg_loss_usd"           : "Perdida media/trade (USD)",
        "final_equity"           : "Capital final (USD)",
        "total_days_analyzed"    : "Total dias analizados",
    }
    for k, lbl in labels.items():
        if k in metrics:
            print(f"  {lbl:<40}: {metrics[k]}")

    print("\n  OBJETIVOS INSTITUCIONALES:")
    checks = [
        ("Dias positivos > 60%",   metrics.get("day_win_rate_pct",0) > 60,      f"{metrics.get('day_win_rate_pct',0):.1f}%"),
        ("Retorno mensual 1.5-3%", 1.5 <= metrics.get("monthly_return_avg_pct",0) <= 3.0, f"{metrics.get('monthly_return_avg_pct',0):.2f}%"),
        ("Sharpe > 1.5",           metrics.get("sharpe_approx",0) > 1.5,        f"{metrics.get('sharpe_approx',0):.2f}"),
        ("Profit Factor > 1.3",    metrics.get("profit_factor",0) > 1.3,        f"{metrics.get('profit_factor',0):.2f}"),
        ("Max Drawdown < 10%",     abs(metrics.get("max_drawdown_pct",0)) < 10, f"{metrics.get('max_drawdown_pct',0):.2f}%"),
    ]
    for lbl, ok, val in checks:
        print(f"  {'OK' if ok else 'NO'} {lbl:<38}: {val}")

    if not equity_df.empty:
        plot_equity_curve(equity_df, "equity_curve.png")
        print("\n  Curva de equity guardada en equity_curve.png")
    if not trades_df.empty:
        trades_df.to_csv("trades_backtest.csv", index=False)
        print("  Detalle de trades guardado en trades_backtest.csv")
    print()


def run_paper_mode(capital: float, csv_warmup: str = None):
    from config import STRATEGY
    from live_engine import LiveEngine
    print("\n" + "=" * 58)
    print(f"  PAPER TRADING  |  EMA 5/13/150  |  BCH/USDT 1H  |  SIN DINERO REAL")
    print(f"  Capital inicial: ${capital:.2f} USD")
    print("=" * 58)
    engine = LiveEngine(initial_capital=capital, mode="PAPER", csv_warmup_path=csv_warmup)
    engine.run()


def run_live_mode(capital: float, csv_warmup: str = None):
    from config import EXCHANGE, STRATEGY
    from live_engine import LiveEngine
    print("\n" + "=" * 58)
    print(f"  TRADING EN VIVO  |  EMA 5/13/150  |  BCH/USDT 1H")
    print(f"  Capital: ${capital:.2f} | Exchange: Binance {'TESTNET' if EXCHANGE.sandbox else 'REAL'}")
    print("=" * 58)
    if not EXCHANGE.sandbox:
        print("\n  ADVERTENCIA: SANDBOX=FALSE. Esto usa DINERO REAL.")
        confirm = input("  Escribe 'CONFIRMO' para continuar: ")
        if confirm.strip().upper() != "CONFIRMO":
            print("  Cancelado.")
            return
    engine = LiveEngine(initial_capital=capital, mode="LIVE", csv_warmup_path=csv_warmup)
    engine.run()


def run_crew_mode(cycle: str):
    try:
        from crew import build_hourly_crew, build_daily_crew
        print(f"\n  Iniciando CrewAI - ciclo: {cycle.upper()}")
        crew = build_hourly_crew() if cycle == "hourly" else build_daily_crew()
        result = crew.kickoff()
        print(result)
    except Exception as e:
        logger.error(f"Error en crew: {e}")


def run_test_telegram():
    from notifications import _send_message
    from config import TELEGRAM, STRATEGY
    print("\n  Probando conexion Telegram...")
    ok = _send_message(
        "<b>TEST EXITOSO</b>\n\n"
        "El bot de trading esta correctamente conectado a Telegram.\n\n"
        "<b>Sistema:</b> ATFS | BTC/USDT H1\n"
        "<b>Estado:</b> Listo para operar\n"
        "<b>Capital inicial:</b> $200 USD (Paper)"
    )
    print("  OK - Mensaje enviado!" if ok else "  ERROR - Verifica .env")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot BTC/USDT H1 - ATFS")
    parser.add_argument("--mode",      choices=["backtest","paper","live","crew","test-telegram"], required=True)
    parser.add_argument("--csv",       type=str,   default=None)
    parser.add_argument("--capital",   type=float, default=200.0)
    parser.add_argument("--date-from", type=str,   default=None)
    parser.add_argument("--date-to",   type=str,   default=None)
    parser.add_argument("--cycle",     type=str,   default="hourly", choices=["hourly","daily"])
    args = parser.parse_args()

    if   args.mode == "backtest":      run_backtest_mode(args.csv, args.capital, args.date_from, args.date_to)
    elif args.mode == "paper":         run_paper_mode(args.capital, args.csv)
    elif args.mode == "live":          run_live_mode(args.capital, args.csv)
    elif args.mode == "crew":          run_crew_mode(args.cycle)
    elif args.mode == "test-telegram": run_test_telegram()
