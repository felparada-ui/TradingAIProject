"""
Suite Completa de Escenarios de Backtest

Ejecuta múltiples configuraciones y genera un reporte comparativo
con métricas de rendimiento para cada escenario.
"""

import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.autotrading_crew import tools as crew_tools
from src.autotrading_crew.backtest import BacktestSimulator

REPORT_DIR = "data/backtest_results"


def load_base_config() -> dict:
    with open("src/autotrading_crew/config/config.yaml") as f:
        return yaml.safe_load(f)


def run_scenario(name: str, config: dict, symbols: list[str], days: int, use_real: bool = False, **kwargs) -> dict:
    """Ejecuta un escenario y devuelve métricas."""
    print(f"\n{'#'*70}")
    print(f"  ESCENARIO: {name}")
    print(f"  Símbolos: {symbols} | Días: {days}")
    print(f"  Fuente: {'🌐 REAL (CCXT/CSV)' if use_real else '⚙️  SINTÉTICO'}")
    print(f"{'#'*70}")

    sim = BacktestSimulator(config, symbols=symbols)
    report = sim.run(days=days, use_real_data=use_real)

    return {
        "scenario": name,
        "symbols": symbols,
        "days": days,
        "trades": report.get("total_trades", 0),
        "return_pct": report.get("retorno_total_pct", 0),
        "win_rate_pct": report.get("win_rate_pct", 0),
        "profit_factor": report.get("profit_factor", 0),
        "sharpe_ratio": report.get("sharpe_ratio", 0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0),
        "capital_final": report.get("capital_final", 0),
        "regimen_stats": report.get("regimen_stats", {}),
    }


def print_comparison_table(results: list[dict]):
    """Imprime tabla comparativa de todos los escenarios."""
    print(f"\n{'='*100}")
    print(f"  📊 TABLA COMPARATIVA — {len(results)} ESCENARIOS")
    print(f"{'='*100}")
    print(f"{'Escenario':30s} {'Trades':>6s} {'Retorno%':>9s} {'WinRate%':>8s} "
          f"{'PF':>7s} {'Sharpe':>7s} {'DD%':>6s} {'Cap.Final':>10s}")
    print("-" * 100)

    for r in results:
        reg_info = ""
        if r.get("regimen_stats"):
            rs = r["regimen_stats"]
            reg_info = " | ".join(f"{k}:{v['trades']}t" for k, v in rs.items())

        print(f"{r['scenario']:30s} {r['trades']:>6d} {r['return_pct']:>+8.2f}% "
              f"{r['win_rate_pct']:>7.1f}% {r['profit_factor']:>7.2f} "
              f"{r['sharpe_ratio']:>7.2f} {r['max_drawdown_pct']:>6.2f}% "
              f"${r['capital_final']:>8.2f}")
        if reg_info:
            print(f"{'':30s}   Regímenes: {reg_info}")

    print("=" * 100)


def run_all_scenarios():
    """Ejecuta todos los escenarios de backtest."""
    os.makedirs(REPORT_DIR, exist_ok=True)

    config = load_base_config()
    crew_tools.initialize(config)

    all_results = []

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 1: Multi-activo estándar
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Multi-activo (Forex+Crypto+ETF)",
        config,
        symbols=["EUR/USD", "BTC/USD", "SPY"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 2: Solo Forex
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Forex (EUR/USD + GBP/USD)",
        config,
        symbols=["EUR/USD", "GBP/USD"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 3: Solo Crypto
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Crypto (BTC + ETH + BCH)",
        config,
        symbols=["BTC/USD", "ETH/USD", "BCH/USD"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 4: Solo ETFs
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "ETFs (SPY + QQQ + IWM)",
        config,
        symbols=["SPY", "QQQ", "IWM"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 5: Largo plazo (1 año)
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Largo plazo (365d, BTC+SPY)",
        config,
        symbols=["BTC/USD", "SPY"],
        days=365,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 6: Corto plazo (30 días)
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Corto plazo (30d, 5 activos)",
        config,
        symbols=["EUR/USD", "BTC/USD", "SPY", "BCH/USD", "ETH/USD"],
        days=30,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 7: Riesgo agresivo
    # ═════════════════════════════════════════════════════════════════════
    agg_config = load_base_config()
    agg_config["riesgo"]["riesgo_maximo_por_operacion"] = 3.0
    agg_config["riesgo"]["take_profit_minimo_rr"] = 1.2
    agg_config["riesgo"]["trailing_activacion"] = 1.0
    crew_tools.initialize(agg_config)
    r = run_scenario(
        "Riesgo agresivo (3%, RR≥1.2)",
        agg_config,
        symbols=["BTC/USD", "SPY", "EUR/USD"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 8: Riesgo conservador
    # ═════════════════════════════════════════════════════════════════════
    cons_config = load_base_config()
    cons_config["riesgo"]["riesgo_maximo_por_operacion"] = 0.5
    cons_config["riesgo"]["take_profit_minimo_rr"] = 3.0
    cons_config["riesgo"]["trailing_activacion"] = 1.5
    crew_tools.initialize(cons_config)
    r = run_scenario(
        "Riesgo conservador (0.5%, RR≥3.0)",
        cons_config,
        symbols=["EUR/USD", "SPY", "BTC/USD"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 9: Un solo activo (BTC)
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Single: BTC/USD",
        config,
        symbols=["BTC/USD"],
        days=180,
    )
    all_results.append(r)

    # ═════════════════════════════════════════════════════════════════════
    # ESCENARIO 10: Todos los activos disponibles
    # ═════════════════════════════════════════════════════════════════════
    r = run_scenario(
        "Todos los activos (7 símbolos)",
        config,
        symbols=["EUR/USD", "GBP/USD", "BTC/USD", "ETH/USD", "SPY", "QQQ", "IWM"],
        days=90,
    )
    all_results.append(r)

    # ─── Imprimir tabla comparativa ──────────────────────────────────────
    print_comparison_table(all_results)

    # ─── Guardar resultados completos ────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(REPORT_DIR, f"escenarios_comparativa_{timestamp}.json")
    with open(report_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n📁 Reporte completo guardado: {report_file}")

    # ─── Generar markdown de conclusiones ────────────────────────────────
    generate_conclusions_md(all_results, timestamp)

    return all_results


def generate_conclusions_md(results: list[dict], timestamp: str):
    """Genera archivo markdown con conclusiones de la comparativa."""
    lines = [
        f"# Informe Comparativo de Escenarios — {timestamp}",
        "",
        f"Total de escenarios ejecutados: **{len(results)}**",
        "",
        "## Resumen Ejecutivo",
        "",
        "| Escenario | Trades | Retorno | Win Rate | Profit Factor | Sharpe | DD Máx |",
        "|-----------|--------|---------|----------|--------------|--------|--------|",
    ]

    for r in results:
        lines.append(
            f"| {r['scenario']} | {r['trades']} | {r['return_pct']:+.2f}% | "
            f"{r['win_rate_pct']:.1f}% | {r['profit_factor']:.2f} | "
            f"{r['sharpe_ratio']:.2f} | {r['max_drawdown_pct']:.2f}% |"
        )

    lines += [
        "",
        "## Mejor escenario por métrica",
        "",
    ]

    metrics = [
        ("Retorno total", "return_pct", max),
        ("Win Rate", "win_rate_pct", max),
        ("Profit Factor", "profit_factor", max),
        ("Sharpe Ratio", "sharpe_ratio", max),
        ("Menor Drawdown", "max_drawdown_pct", min),
    ]

    for metric_name, key, func in metrics:
        best = func(results, key=lambda r: r.get(key, 0) if key != "max_drawdown_pct" else -r.get(key, 0))
        lines.append(f"- **{metric_name}**: *{best['scenario']}* → {best.get(key, 0)}")

    lines += [
        "",
        "## Desglose por régimen de mercado",
        "",
    ]

    for r in results:
        if r.get("regimen_stats"):
            lines.append(f"### {r['scenario']}")
            for regime, stats in r["regimen_stats"].items():
                lines.append(f"- {regime}: {stats['trades']} trades, {stats['win_rate']}% WR, ${stats['pnl_usd']:+.2f}")
            lines.append("")

    lines += [
        "",
        "## Recomendaciones",
        "",
        "- Analizar qué configuración de riesgo maximiza el Sharpe Ratio",
        "- Verificar consistencia entre regímenes de mercado",
        "- Identificar activos con mejor relación riesgo/retorno",
    ]

    md_file = os.path.join(REPORT_DIR, f"INFORME_COMPARATIVO_{timestamp}.md")
    with open(md_file, "w") as f:
        f.write("\n".join(lines))
    print(f"📄 Informe markdown guardado: {md_file}")


if __name__ == "__main__":
    start = time.time()
    run_all_scenarios()
    elapsed = time.time() - start
    print(f"\n⏱️  Tiempo total: {elapsed:.1f}s")
