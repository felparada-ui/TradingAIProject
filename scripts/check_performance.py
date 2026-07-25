"""
Herramienta rápida para verificar el estado de la estrategia.
Responde: ¿Voy ganando o perdiendo? ¿Estoy dentro de lo esperado?
"""

import sys
sys.path.insert(0, "/workspaces/TradingAIProject")

from tools.performance_tracker import check_performance, BACKTEST_EXPECTED
import json

CAPITAL = 200.0  # Capital en paper trading

print("=" * 60)
print("  📊 VERIFICACION DE RENDIMIENTO — ¿LA ESTRATEGIA SIRVE?")
print("=" * 60)

print(f"\n🎯 OBJETIVOS (basados en backtest de 4.5 años):")
print(f"  Retorno anual esperado: +{BACKTEST_EXPECTED['annual_return_pct']}%")
print(f"  Win Rate esperado: {BACKTEST_EXPECTED['win_rate']}%")
print(f"  Profit Factor esperado: {BACKTEST_EXPECTED['profit_factor']}")
print(f"  Trades por mes esperados: ~{BACKTEST_EXPECTED['trades_per_month']}")
print(f"  Drawdown max esperado: {BACKTEST_EXPECTED['max_drawdown_pct']}%")
print(f"  Capital: ${CAPITAL}")

result = check_performance(CAPITAL, send_telegram=True)

print(f"\n📋 RESULTADO ACTUAL:")
if result.get("status") == "SIN DATOS":
    print("  ⏳ Sin operaciones registradas aún.")
    print("  El bot está esperando condiciones óptimas de mercado.")
    print("  Cuando ejecute un trade, el tracker empezará a reportar.")
else:
    real = result.get("real", {})
    exp = result.get("expected", {})
    
    print(f"  Trades ejecutados: {real.get('total_trades', 0)}")
    print(f"  Retorno: {real.get('total_return_pct', 0):+.2f}%")
    print(f"  Win Rate: {real.get('win_rate_pct', 0)}%")
    print(f"  Profit Factor: {real.get('profit_factor', 0)}")
    print(f"  Capital actual: ${real.get('current_capital', CAPITAL):.2f}")
    print(f"\n  {result.get('veredict', 'Sin veredicto')}")

print(f"\n¿CÓMO SÉ SI SIRVE?")
print(f"  {'='*40}")
print(f"  ✅ BUENO: PF > 1.0 despues de 10+ trades")
print(f"  ✅ MUY BUENO: PF > 1.2 y WR > 35%")
print(f"  ✅ EXCELENTE: Coincide con backtest (+20%/4.5 años)")
print(f"  ⚠️  REVISAR: PF < 1.0 despues de 15+ trades")
print(f"  ❌ MALO: Perdidas consistentes 3 meses seguidos")
print(f"  {'='*40}")

print(f"\n📤 Reporte enviado a Telegram")
