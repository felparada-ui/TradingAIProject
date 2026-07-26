"""
KILL SWITCH — Cierra todas las posiciones abiertas en MT5 inmediatamente.

Uso:
    python scripts/emergency_close.py
    python scripts/emergency_close.py --symbol BTCUSD  # Cerrar solo un símbolo

Útil para:
  - Detener pérdidas si el bot se descontrola
  - Limpiar posiciones antes de reiniciar el bot
  - Emergencia si el circuit breaker no se activó
"""

import os
import sys
from datetime import datetime

# ─── Cargar .env ────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

LOGIN = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER = os.getenv("MT5_SERVER", "")

try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌ MetaTrader5 no instalado. pip install MetaTrader5")
    sys.exit(1)


def close_all_positions(symbol_filter: str = None):
    """Cierra todas las posiciones (o las de un símbolo específico)."""
    if not mt5.initialize():
        print(f"❌ Error inicializando MT5: {mt5.last_error()}")
        return False

    if LOGIN and PASSWORD:
        if not mt5.login(LOGIN, password=PASSWORD, server=SERVER):
            print(f"❌ Error de autenticación: {mt5.last_error()}")
            mt5.shutdown()
            return False

    account = mt5.account_info()
    if account:
        print(f"✅ Conectado: {account.server} | Balance: ${account.balance:.2f}")

    # Obtener posiciones
    if symbol_filter:
        positions = mt5.positions_get(symbol=symbol_filter)
        label = f"símbolo {symbol_filter}"
    else:
        positions = mt5.positions_get()
        label = "TODOS los símbolos"

    if positions is None or len(positions) == 0:
        print(f"✅ No hay posiciones abiertas en {label}")
        mt5.shutdown()
        return True

    print(f"\n⚠️  Cerrando {len(positions)} posiciones en {label}...")
    closed = 0
    errors = 0
    total_pnl = 0

    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        volume = pos.volume
        pnl = pos.profit
        side = "BUY" if pos.type == 0 else "SELL"

        # Determinar tipo de orden contraria
        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 202401,
            "comment": "EMERGENCY CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            total_pnl += pnl
            print(f"  ✅ Cerrado {symbol:10s} {side:5s} Vol:{volume:.2f} PnL:${pnl:.2f}")
        else:
            errors += 1
            print(f"  ❌ Error cerrando {symbol}: {result.comment} (código {result.retcode})")

    print(f"\n{'='*50}")
    print(f"  Resumen:")
    print(f"  Cerradas: {closed}")
    print(f"  Errores:  {errors}")
    print(f"  PnL total: ${total_pnl:.2f}")
    print(f"{'='*50}")

    mt5.shutdown()
    return errors == 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kill Switch - Cierra posiciones en MT5")
    parser.add_argument("--symbol", type=str, default=None, help="Símbolo específico (ej: EURUSD)")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  🛑 KILL SWITCH — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    print(f"  ¿Estás seguro de cerrar todas las posiciones?")
    confirm = input("  Escribe 'CONFIRMAR' para continuar: ")
    if confirm == "CONFIRMAR":
        close_all_positions(args.symbol)
    else:
        print("  Cancelado.")
