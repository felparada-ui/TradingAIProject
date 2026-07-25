"""
Diagnóstico de conexión MetaTrader 5 — ICMarketsSC Demo

Ejecutar EN WINDOWS con MT5 instalado:
    python scripts/diagnostico_mt5.py

Verifica:
  - MT5 instalado y versión
  - Conexión al servidor ICMarketsSC-Demo
  - Estado de la cuenta demo
  - Símbolos disponibles y spreads
"""

import os
import sys
from datetime import datetime

# ─── Intentar importar MT5 ────────────────────────────────────────────────
try:
    import MetaTrader5 as mt5
    print("✅ MetaTrader5 instalado")
except ImportError:
    print("❌ MetaTrader5 NO instalado")
    print("   Solución: pip install MetaTrader5")
    sys.exit(1)

# ─── Credenciales desde .env o variables ──────────────────────────────────
LOGIN = int(os.getenv("MT5_LOGIN", "52947731"))
PASSWORD = os.getenv("MT5_PASSWORD", "XX17bJ$SAct5YG")
SERVER = os.getenv("MT5_SERVER", "ICMarketsSC-Demo")

print(f"\n{'='*60}")
print(f"  DIAGNÓSTICO MT5 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}")
print(f"  Servidor: {SERVER}")
print(f"  Cuenta:   {LOGIN}")
print(f"{'='*60}")

# ─── Paso 1: Inicializar MT5 ──────────────────────────────────────────────
print("\n📡 [1/5] Inicializando terminal MT5...")
if not mt5.initialize():
    error = mt5.last_error()
    print(f"   ❌ Error: {error}")
    print("   ⚠️  Asegúrate de que MetaTrader 5 esté instalado")
    sys.exit(1)
print("   ✅ Terminal inicializada")

# ─── Paso 2: Autenticar ───────────────────────────────────────────────────
print(f"\n🔐 [2/5] Autenticando en {SERVER}...")
authorized = mt5.login(LOGIN, password=PASSWORD, server=SERVER)
if not authorized:
    error = mt5.last_error()
    print(f"   ❌ Error de autenticación: {error}")
    print("   ⚠️  Verifica credenciales en .env")
    mt5.shutdown()
    sys.exit(1)
print("   ✅ Autenticación exitosa")

# ─── Paso 3: Info de cuenta ───────────────────────────────────────────────
print("\n💰 [3/5] Información de la cuenta:")
account_info = mt5.account_info()
if account_info:
    print(f"   • Servidor:    {account_info.server}")
    print(f"   • Cuenta:      {account_info.login}")
    print(f"   • Balance:     ${account_info.balance:.2f}")
    print(f"   • Equity:      ${account_info.equity:.2f}")
    print(f"   • Margen libre: ${account_info.margin_free:.2f}")
    print(f"   • Apalancamiento: 1:{account_info.leverage}")
    print(f"   • Moneda:      {account_info.currency}")
    print(f"   • Nombre:      {account_info.name}")
else:
    print("   ❌ No se pudo obtener información de la cuenta")

# ─── Paso 4: Símbolos y spreads ───────────────────────────────────────────
print("\n📊 [4/5] Verificando símbolos disponibles...")
symbols_to_check = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "BTCUSD", "ETHUSD",
    "SP500", "US30", "NAS100",
    "XAUUSD", "XAGUSD",
    "BCHUSD", "LTCUSD", "XRPUSD",
]

print(f"   {'Símbolo':12s} {'Bid':>10s} {'Ask':>10s} {'Spread':>7s} {'Trade':>6s}")
print(f"   {'-'*45}")
available = 0
for symbol in symbols_to_check:
    info = mt5.symbol_info(symbol)
    if info and info.visible:
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            spread = (tick.ask - tick.bid) / info.point if info.point > 0 else 0
            print(f"   {symbol:12s} {tick.bid:>10.5f} {tick.ask:>10.5f} {spread:>7.1f} {'✅' if info.trade_mode else '❌':>6s}")
            available += 1
        else:
            print(f"   {symbol:12s} {'N/A':>10s} {'N/A':>10s} {'N/A':>7s}")
    else:
        # Intentar activar el símbolo
        if mt5.symbol_select(symbol, True):
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                info = mt5.symbol_info(symbol)
                spread = (tick.ask - tick.bid) / info.point if info and info.point > 0 else 0
                print(f"   {symbol:12s} {tick.bid:>10.5f} {tick.ask:>10.5f} {spread:>7.1f} {'✅' if info and info.trade_mode else '❌':>6s}")
                available += 1
        else:
            print(f"   {symbol:12s} {'oculto':>10s}")

print(f"\n   Total símbolos disponibles: {available}/{len(symbols_to_check)}")

# ─── Paso 5: Posiciones abiertas ──────────────────────────────────────────
print("\n📋 [5/5] Posiciones abiertas:")
positions = mt5.positions_get()
if positions and len(positions) > 0:
    for pos in positions:
        print(f"   • {pos.symbol:8s} {'BUY' if pos.type == 0 else 'SELL':5s} "
              f"Vol: {pos.volume:.2f} | Entry: {pos.price_open:.5f} | "
              f"SL: {pos.sl:.5f} | TP: {pos.tp:.5f} | "
              f"PnL: ${pos.profit:.2f}")
else:
    print("   ✅ Sin posiciones abiertas")

# ─── Resumen final ────────────────────────────────────────────────────────
print(f"\n{'='*60}")
if available > 0:
    print(f"  ✅ DIAGNÓSTICO COMPLETADO — {available} símbolos disponibles")
    print(f"  Listo para operar con Autotrading Crew")
else:
    print(f"  ⚠️  DIAGNÓSTICO COMPLETADO — Sin símbolos disponibles")
    print(f"  Revisa la configuración del servidor")
print(f"{'='*60}")

# ─── Limpiar ──────────────────────────────────────────────────────────────
mt5.shutdown()
