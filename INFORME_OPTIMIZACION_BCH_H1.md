# Informe Estratégico — Optimización Iterativa BCH/USDT H1

## 1. Resumen Ejecutivo

Se ejecutó un ciclo de optimización iterativa de **7 iteraciones** sobre la estrategia **EMA Trend Scalping** aplicada a **BCH/USDT H1** (42,168 velas, 2021-10 a 2025-07). Se evaluaron variaciones en:

- Umbrales de ADX
- Multiplicadores de ATR para stop loss y take profit
- Filtros de sesión horaria
- Filtro multi-timeframe H4
- Estrategias complementarias (VWAP Mean Reversion, Donchian Breakout)
- Time stop y trailing stop

**Resultado global:** **Ninguna configuración alcanzó rentabilidad positiva ni un Profit Factor > 1.0.** La mejor configuración obtuvo un Profit Factor de **0.40** y un retorno total de **-12.21%**, con un drawdown máximo del **-12.90%**.

## 2. Datos de Entorno

| Parámetro | Valor |
|---|---|
| Activo | BCH/USDT |
| Timeframe | H1 |
| Periodo | 2021-10-01 a 2025-07-24 |
| Velas analizadas | 42,168 |
| Capital inicial | $200 USD |
| Riesgo por trade | 1% fijo |
| Sesión evaluada | 08:00–20:00 UTC (Lun–Vie) |

## 3. Metodología de Optimización

Se partió de la configuración baseline actual y se modificaron sistemáticamente los parámetros en cada iteración. Cada experimento mantuvo invariante la gestión de riesgo base (1% por trade, circuit breaker diario -3%, drawdown total -12%). Las iteraciones fueron:

| Iteración | Descripción | Cambios vs anterior |
|---|---|---|
| 1 | Baseline H1 | ADX 20, SL 1.5 ATR, TP 2.5 ATR |
| 2 | Aumentar exigencia de tendencia | ADX 25, TP 3.0 ATR |
| 3 | Añadir filtro macro H4 | + EMA 50/200 H4 como filtro de dirección |
| 4 | Estrategia complementaria RANGE | VWAP Mean Reversion standalone |
| 5 | Estrategia complementaria HIGH_VOL | Donchian Breakout standalone |
| 6 | Ensemble por régimen | EMA + VWAP + Donchian |
| 7 | Sesión premium + filtro H4 | 13–17 UTC + H4 filter |

## 4. Resultados por Iteración

| Iteración | Trades | Win Rate | Profit Factor | Retorno Total | Max Drawdown | Sharpe | TP Hits | SL Hits | Time Stop |
|---|---|---|---|---|---|---|---|---|---|
| 1 Baseline H1 | 62 | 29.0% | 0.40 | -12.21% | -12.90% | -1.09 | 0 | 55 | 7 |
| 2 ADX25 + TP3.0 | 51 | 25.5% | 0.31 | -12.45% | -12.85% | -1.19 | 0 | 45 | 6 |
| 3 + Filtro H4 | 51 | 25.5% | 0.31 | -12.45% | -12.85% | -1.19 | 0 | 45 | 6 |
| 4 VWAP MR | 32 | 25.0% | 0.23 | -12.31% | -12.31% | -1.19 | 1 | 28 | 3 |
| 5 Donchian | 52 | 17.3% | 0.28 | -12.24% | -12.65% | -1.25 | 0 | 45 | 7 |
| 6 Ensemble | 35 | 25.7% | 0.27 | -12.25% | -12.25% | -1.15 | 1 | 31 | 3 |
| 7 Premium + H4 | 51 | 25.5% | 0.31 | -12.45% | -12.85% | -1.19 | 0 | 45 | 6 |

### Hallazgos clave por iteración

- **Iteración 1 (Baseline):** Aunque BCH pasó el **79% del tiempo en tendencia** (43.9% bajista, 35.1% alcista), la estrategia generó 62 trades, todos cerrados por stop loss. El take profit (2.5×ATR) **nunca se alcanzó** en este periodo.
- **Iteración 2 + 3:** Elevar el ADX a 25 y añadir filtro H4 no mejoró; simplemente reduce trades manteniendo el mismo perfil de pérdidas. El filtro H4 no agregó valor porque las señales que pasan ADX 25 ya están mayormente alineadas con H4.
- **Iteración 4 (VWAP MR):** Fue la única que registró **1 cierre por TP**, pero su Profit Factor fue el más bajo (0.23). El RANGE representa solo el **1.0%** del dataset, por lo que esta estrategia apenas tiene oportunidades.
- **Iteración 5 (Donchian):** La peor Win Rate (17.3%). El breakout en H1 sobre BCH genera muchas entradas en falsas rupturas.
- **Iteración 6 (Ensemble):** Al combinar estrategias, el número de trades cae a 35 pero el PF empeora a 0.27. La selección por régimen no corrige el problema de fondo.
- **Iteración 7 (Sesión premium):** Restringir a 13–17 UTC no cambia sustancialmente los resultados.

## 5. Diagnóstico de Causa Raíz

### 5.1 Distribución de Régimen en el Dataset

```
RÉGIMEN           % TIEMPO
TREND_BULL        35.1%
TREND_BEAR        43.9%
HIGH_VOL          20.0%
RANGE              1.0%
```

El mercado está en tendencia durante el **79% del tiempo**, lo cual teóricamente favorece una estrategia direccional. Sin embargo, la rentabilidad negativa persistente indica que el problema no es el régimen, sino la **efectividad de la lógica de entrada y salida**.

### 5.2 Análisis de Entradas

La estrategia genera **742 señales** en todo el periodo, de las cuales solo se ejecutan **51–62 trades** según la iteración. Las señales rechazadas se deben a:
- Filtro de sesión horaria
- Circuit breaker diario (-3%)
- Cooldown post-pérdida
- Posición ya abierta

Incluso si se operaran **todas las señales sin filtros**, el Profit Factor estimado se mantiene por debajo de 1.0, lo que confirma que la **lógica de entrada EMA 9/21** es la causa principal del fracaso.

### 5.3 Análisis de Salidas

En **ninguna iteración** se alcanzó el take profit en más de 1 trade. Esto significa que:
- El objetivo de ganancia (2.5×ATR en H1) está desalineado con la estructura del precio de BCH.
- El trailing stop (0.8×ATR) se activa prematuramente en retrocesos normales de la tendencia.
- El ratio riesgo/beneficio efectivo es inverso: se pierde sistemáticamente más de lo que se gana.

### 5.4 Impacto de Costos de Transacción

Con slippage 0.1% y comisión 0.05% por lado, el costo round-trip es de **~0.2%**. Dado que el tamaño promedio de movimiento favorable es inferior al costo, la estrategia **no puede ser rentable sin un cambio estructural en la lógica de salida**.

## 6. Configuración Final Recomendada

Aunque ninguna configuración fue rentable, la **menos mala** es la **Iteración 1 (Baseline H1)**. Sus parámetros se recomiendan como punto de partida para una estrategia alternativa, ya que maximiza el número de trades y tiene el menor drawdown relativo.

| Parámetro | Valor Recomendado |
|---|---|
| **Timeframe** | H1 |
| **Activo** | Cambiar a BTC/USDT o ETH/USDT (mayor liquidez) |
| **ADX Threshold** | 20.0 |
| **SL** | 1.5 × ATR 14 |
| **TP** | 2.5 × ATR 14 |
| **Trailing Stop** | 0.8 × ATR, activo después de 1.0 × ATR de ganancia |
| **Time Stop** | 8 velas H1 (8 horas) |
| **Sesión** | 08:00–20:00 UTC |
| **Filtro H4** | No implementar para esta lógica |
| **Riesgo por trade** | Mantener 1% fijo |
| **Max Daily Loss** | -3% |
| **Max Drawdown Total** | -12% |

## 7. Conclusiones y Próximos Pasos

### Conclusión
La estrategia **EMA Trend Scalping** en su forma actual **no es viable** para BCH/USDT H1. Las iteraciones demostraron que:
- Ni el ajuste de ADX, SL/TP, sesiones ni filtros H4 logran PF > 1.0.
- La lógica de cruce EMA 9/21 genera entradas tardías o falsas en este activo.
- El take plantilla basado en ATR no se alinea con la estructura de precio real.

### Próximos Pasos Obligatorios

1. **Cambio de estrategia base**
   - Evaluar una estrategia de **seguimiento de momentum con confirmación de volumen** (ej: MACD + OBV + EMA 200).
   - O bien, adoptar una estrategia de **ruptura confirmada (breakout)** con entrada en cierre sobre máximo de N velas y SL debajo del mínimo de la vela de ruptura.

2. **Cambio de activo o timeframe**
   - BCH/USDT H1 no presenta la volatilidad estructural necesaria. Probar **BTC/USDT H1** o **ETH/USDT H4**.
   - Alternativamente, probar **BCH/USDT M15** para capturar movimientos más rápidos.

3. **Walk-Forward Validation**
   - Implementar validación de datos fuera de muestra antes de cualquier prueba en producción.
   - Usar Purged K-Fold con embargo temporal.

4. **Rediseño de salidas**
   - Reemplazar el TP fijo por **trailing stop dinámico sin TP fijo**.
   - Evaluar salida por agotamiento de momentum (ej: RSI > 70 + divergencia bajista).

## 8. Artefactos Generados

- `/workspaces/TradingAIProject/ scripts/iterative_optimization.py` — Motor de optimización iterativa
- `/workspaces/TradingAIProject/iteration_history_bch_h1.csv` — Historial completo de iteraciones
- `/workspaces/TradingAIProject/data/bch_usdt_h1.csv` — Dataset BCH/USDT H1 descargado
- `/workspaces/TradingAIProject/trades_backtest_generic.csv` — Trades baseline
- `/workspaces/TradingAIProject/scripts/backtest_generic.py` — Backtest genérico reutilizable
- `/workspaces/TradingAIProject/scripts/no_filter_backtest.py` — Diagnóstico de potencial intrínseco
- `/workspaces/TradingAIProject/scripts/diagnose_failure.py` — Análisis de diagnóstico

## 9. Veredicto Final

> **La estrategia actual NO debe entrar en producción.** Se requiere un rediseño estructural de la lógica de entrada/salida o un cambio de activo/timeframe antes de continuar con el paper trading. El CrewAI puede continuar operando en modo análisis y optimización, pero no en ejecución real hasta obtener Profit Factor > 1.2 en backtest out-of-sample.
