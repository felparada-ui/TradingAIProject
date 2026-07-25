"""
Script para Windows — Prueba de conexión a MT5 Demo Exness.
Ejecutar en una máquina con MetaTrader 5 instalado.

1. pip install MetaTrader5
2. Copiar .env con credenciales
3. python test_mt5_connection.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

LOGIN = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER = os.getenv("MT5_SERVER", "")

print("=" * 60)
print("  PRUEBA DE CONEXION — MT5 DEMO EXNESS")
print("=" * 60)
print(f"\n📋 Credenciales:")
print(f"  Login: {LOGIN}")
print(f"  Server: {SERVER}")
print(f"  Password: {'*' * len(PASSWORD) if PASSWORD else 'VACIA'}")

try:
    import MetaTrader5 as mt5
    print("\n✅ MetaTrader5 instalado correctamente")
except ImportError:
    print("\n❌ MetaTrader5 no instalado")
    print("   Ejecuta: pip install MetaTrader5")
    sys.exit(1)

print("\n🔌 Inicializando MT5...")
if not mt5.initialize():
    print(f"❌ Error de inicialización: {mt5.last_error()}")
    sys.exit(1)

print("✅ MT5 inicializado")

print(f"\n🔑 Conectando a cuenta demo...")
authorized = mt5.login(LOGIN, password=PASSWORD, server=SERVER)
if not authorized:
    print(f"❌ Error de login: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

account = mt5.account_info()
if account:
    account_type = "DEMO" if account.trade_mode == 0 else "REAL"
    print(f"\n✅ CONEXION EXITOSA")
    print(f"  Nombre: {account.name}")
    print(f"  Balance: ${account.balance:.2f}")
    print(f"  Equity: ${account.equity:.2f}")
    print(f"  Profit: ${account.profit:.2f}")
    print(f"  Margen libre: ${account.margin_free:.2f}")
    print(f"  Apalancamiento: 1:{account.leverage}")
    print(f"  Tipo: {account_type}")
    print(f"  Servidor: {account.server}")
else:
    print(f"❌ No se pudo obtener información de la cuenta")

# Probar obtener símbolos disponibles
print("\n📊 Probando datos de mercado...")
symbol = "BCHUSD"
if mt5.symbol_select(symbol, True):
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        print(f"  {symbol}: Bid={tick.bid} Ask={tick.ask}")
    else:
        print(f"  {symbol}: Sin datos disponibles")
else:
    print(f"  {symbol}: No disponible en este broker")

mt5.shutdown()
print("\n✅ Prueba completada")
