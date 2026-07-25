# Propuesta de estrategia inicial para la crew

## 1. Estado actual del proyecto

El proyecto ya tiene una base sólida:

- Estrategia principal en [strategies/ema_trend_scalping.py](strategies/ema_trend_scalping.py)
- Indicadores en [indicators.py](indicators.py)
- Gestión de riesgo en [risk_manager.py](risk_manager.py)
- Configuración en [config.py](config.py)

---

## 2. Hallazgos de la Búsqueda Masiva de Estrategias

Se probaron **4,977 combinaciones** de 8 tipos de estrategia en 3 timeframes (1h, 4h, 1d).

### Mejor Estrategia Encontrada: MACD Cross 1H

**Configuración default actual** en `config.py`:

| Parámetro | Valor |
|---|---|
| strategy_type | `macd_cross` |
| timeframe | `1h` |
| adx_threshold | 10.0 |
| atr_sl_mult | 1.0 |
| atr_tp_mult | 3.0 |
| use_trailing_stop | False |
| risk_per_trade | 0.5% ($1 por $200) |

**Resultados validados (BCH/USDT, 1000 velas 1H):**
- Retorno total: **+6.09%**
- Profit Factor: **2.34**
- Win Rate: **43.75%**
- Drawdown máximo: **-1.51%**
- Equity final: **$212.18** (de $200)
- Sharpe: **12.06**
- Operaciones: 16 (7 ganadoras, 9 perdedoras)

### Segunda Mejor: Donchian Breakout 4H

**Configuración:**
- strategy_type: `donchian_breakout`, timeframe: `4h`
- donchian_period: 30, adx_threshold: 15.0, TP: 2.0-3.0

**Resultados:** Retorno +1.27%, Win Rate 61.5%, PF 1.81, 13 trades.

### Notas importantes
1. La estrategia MACD Cross funciona mejor en **BCH/USDT** que en BTC/USDT
2. El trailing stop empeoró el rendimiento en esta configuración
3. ADX bajo (10) funciona mejor que ADX alto
4. TP=3.0 da el mejor balance entre frecuencia y rentabilidad
5. La ventana de sesión completa (0-24h) rinde mejor que ventanas restringidas

### Archivos modificados en esta iteración
- `config.py` — Nueva configuración default (MACD Cross 1H)
- `indicators.py` — MACD, BB, DI+ con parámetros configurables
- `strategies/ema_trend_scalping.py` — Generador universal de 8 tipos de señal
- `strategy_search.py` — Módulo de búsqueda masiva
- `strategy_optimizer.py` — Optimizador de parámetros

La estrategia actual ya está orientada a un enfoque de tendencia en BTC/USDT M5 con:

- EMA 9 / 21 / 200
- ADX
- ATR
- filtro de sesión
- riesgo fijo y stop/target dinámicos

Eso es una buena base, pero para volverse realmente rentable hay que mejorar cuatro cosas:

1. Reducir señales falsas
2. Operar solo en regímenes de mercado favorables
3. Usar multi-timeframe
4. Hacer que la crew aprenda y no solo siga una regla fija

---

## 2. Mejoras recomendadas para la estrategia

### A. Estrategia principal: tendencia con pullback

La estrategia inicial debe ser una estrategia de tendencia, no una estrategia agresiva de cruce puro.

Regla base:

- Operar solo cuando el mercado está en tendencia clara
- Entrar en pullback o retroceso técnico, no en el movimiento inicial
- Salir con stop dinámico y objetivo de RR 1:2 o mejor

### B. Mejorar los filtros de entrada

Actualmente la señal se activa por cruce de EMAs y ADX. Eso es útil, pero conviene añadir:

- Confirmación de precio respecto a EMA 200
- Confirmación de momentum corto
- Confirmación de volatilidad suficiente
- Filtro de sesión premium

### C. Evitar operar en rango o en horas muertas

El algoritmo debe evitar:

- rangos laterales
- volatilidad muy baja
- horas de baja liquidez
- mercados con señal débil o ruido alto

### D. Hacerlo más robusto con riesgo realista

La gestión de riesgo ya es buena, pero debe mantenerse estricta:

- 0.5% a 1% riesgo por trade
- máximo 1 posición abierta
- cooldown tras pérdida
- circuit breaker diario y total

---

## 3. Formas de entrada recomendadas

### Forma 1: pullback de tendencia

Entrada ideal para el inicio:

- El precio está por encima de EMA 200 y la EMA 9 está por encima de la EMA 21
- Se produce un retroceso hacia EMA 21 o EMA 9
- Hay rebotada y cierre de vela favorable
- Se entra en dirección de la tendencia

Esta forma es más limpia y evita entradas tempranas.

### Forma 2: breakout con retest

Otra forma válida:

- Se rompe un máximo/mínimo reciente
- El precio hace retest al nivel roto
- Se entra con confirmación de impulso

### Forma 3: cruce de EMA con confirmación de ADX

La forma actual es buena como base, pero debe usarse solo si:

- ADX está fuerte
- el precio está alineado con la tendencia macro
- la vela de entrada tiene fuerza

---

## 4. Indicadores recomendados

### Indicadores base obligatorios

- EMA 9: señal rápida
- EMA 21: señal intermedia
- EMA 200: filtro macro
- ATR 14: stop y sizing
- ADX 14: fuerza de tendencia
- RSI 14: filtro de sobrecompra/sobreventa
- Donchian 20: breakout y retest

### Indicadores secundarios recomendados

- VWAP: confirmar si el precio opera por encima o por debajo del valor medio de la sesión
- Volume profile o volumen relativo: útil para confirmar interés real
- MACD histogram: ayuda a detectar impulso

### Qué conviene evitar al inicio

- Demasiados indicadores al mismo tiempo
- Indicadores complejos sin validación real
- Overfitting con demasiados parámetros

La regla práctica es:

- 3 indicadores de tendencia
- 2 de volatilidad
- 1 de impulso

---

## 5. Timeframe recomendado

### Timeframe inicial

- M5 como timeframe principal para entradas
- H1 como filtro de tendencia
- H4 como contexto macro

Esto es mejor que usar solo M5 porque evita señales falsas en mercados laterales.

### Recomendación práctica

- Entradas en M5
- Confirmación en H1
- Revisión diaria en H4

Esto convierte la estrategia en un sistema más rentable y menos nervioso.

---

## 6. Estrategia inicial de la crew

La crew inicial debe ser simple, conservadora y escalable.

### Objetivo inicial

Operar solo cuando haya:

1. Tendencia clara en H1
2. Entrada limpia en M5
3. Volatilidad suficiente
4. Riesgo controlado

### Regla inicial propuesta

Entrar largo si:

- el precio está por encima de EMA 200 en H1
- la EMA 9 cruza por encima de EMA 21 en M5
- ADX > 20
- el precio está en pullback o retest de EMA 21
- la vela tiene fuerza y el riesgo es controlado

Entrar corto si:

- el precio está por debajo de EMA 200 en H1
- la EMA 9 cruza por debajo de EMA 21 en M5
- ADX > 20
- el precio está en pullback o retest de EMA 21
- la vela tiene fuerza

### Gestión de riesgo inicial

- riesgo por trade: 0.5% a 1%
- SL con ATR 1.0 a 1.2
- TP con RR 1:2
- stop trail tras moverse favorablemente

---

## 7. Cómo debe evolucionar la crew con el tiempo

### Fase 1: base estable

Agentes clave:

- Market Analyst
- Risk Manager
- Strategy Optimizer
- Orchestrator

Objetivo:

- validar la estrategia inicial
- medir win rate, PF y drawdown
- evitar sobreajuste

### Fase 2: mejora incremental

Agregar:

- ML Engineer
- Execution Monitor

Objetivo:

- filtrar señales de baja calidad
- mejorar timing de entrada/salida
- analizar slippage y ejecución

### Fase 3: optimización continua

Objetivo:

- ajustar parámetros con walk-forward
- reentrenar filtros
- evaluar desempeño por régimen de mercado

---

## 8. Recomendación final

La estrategia inicial más sensata para este proyecto es:

- Tendencia clásica en M5
- Confirmación en H1
- Filtro de tendencia macro con EMA 200
- Cruce EMA 9/21 como señal de entrada
- ADX y ATR como confirmación
- Riesgo fijo y gestión conservadora

Eso es simple, testeable y mucho más rentable que una estrategia demasiado agresiva o demasiado compleja.

En resumen:

- Mejor estrategia: trend-following con pullback
- Mejor forma: pullback/retest + confirmación de impulso
- Mejores indicadores: EMA 9/21/200, ADX, ATR, RSI, Donchian
- Mejor timeframe: M5 para entrada, H1 para filtro, H4 para contexto
- Mejor enfoque de crew: simple al inicio, luego ir añadiendo filtros y aprendizaje automático
