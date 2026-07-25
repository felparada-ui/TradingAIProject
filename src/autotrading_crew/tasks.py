"""
Definición de Tareas para la Crew de Autotrading.

Cada tarea corresponde a una fase del workflow:
  - Fase 1 (Barrido):   Quant Strategist escanea y filtra activos
  - Fase 2 (Análisis):  Technical Scout + Sentiment Tracker evalúan
  - Fase 3 (Validación): Risk Manager valida la operación
  - Fase 4 (Ejecución):  Execution Trader coloca y monitorea la orden
"""

import json
from crewai import Task, Agent


# ============================================================================
# FASE 1: BARRIDO DE MERCADO
# ============================================================================

def create_scan_task(agent_obj: Agent, assets: list[str] = None) -> Task:
    """El Quant Strategist escanea 25+ activos y selecciona los top 3."""
    assets_str = json.dumps(assets or [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
        "BTC/USD", "ETH/USD", "SOL/USD",
        "SPY", "QQQ", "IWM", "DIA",
    ])

    return Task(
        description=f"""
        **FASE 1: BARRIDO DE MERCADO**

        Tu tarea es escanear los siguientes activos y seleccionar los 3 mejores:

        Activos: {assets_str}

        Pasos:
        1. Usa `scan_market_assets` para obtener el ranking completo de activos.
        2. Para cada uno de los top 5, usa `detect_market_regime` para identificar
           el régimen de mercado actual (tendencia, rango, alta volatilidad).
        3. Selecciona los 3 activos con mejor puntuación compuesta para la siguiente fase.

        Entrega un JSON con:
          - top_3_assets: lista de los 3 mejores símbolos
          - regime_summary: régimen detectado para cada uno
          - justification: breve explicación de por qué fueron seleccionados
        """,
        expected_output="JSON con top_3_assets, regime_summary y justification",
        agent=agent_obj,
    )


# ============================================================================
# FASE 2: ANÁLISIS CRUZADO
# ============================================================================

def create_technical_analysis_task(agent_obj: Agent, symbols_json: str) -> Task:
    """El Technical Scout analiza los activos en múltiples timeframes."""
    return Task(
        description=f"""
        **FASE 2A: ANÁLISIS TÉCNICO MULTI-TIMEFRAME**

        Activos a analizar: {symbols_json}

        Para CADA activo en la lista, debes:
        1. Usar `analyze_multi_timeframe` para obtener señal consolidada (M5, M15, H1, H4).
        2. Usar `calculate_vwap_profile` para determinar posición vs VWAP.
        3. Usar `detect_harmonic_patterns` para buscar patrones armónicos.
        4. Usar `compute_order_flow_imbalance` para medir presión compradora/vendedora.
        5. Usar `generate_technical_signal` para obtener señal con SL/TP dinámicos.

        Para cada activo, entrega:
          - signal (BUY/SELL/NEUTRAL)
          - confidence (0-100)
          - entry, stop_loss, take_profit sugeridos
          - timeframes analizados y su consistencia
          - patrones armónicos encontrados (si hay)
          - desequilibrio de flujo de órdenes

        Finalmente, selecciona el mejor activo para operar basado en la
        consistencia entre timeframes y la calidad de la señal.
        """,
        expected_output="JSON con análisis detallado de cada activo y recomendación final",
        agent=agent_obj,
    )


def create_sentiment_analysis_task(agent_obj: Agent, symbols_json: str) -> Task:
    """El Sentiment Tracker analiza noticias y sentimiento social."""
    return Task(
        description=f"""
        **FASE 2B: ANÁLISIS DE SENTIMIENTO**

        Activos a analizar: {symbols_json}

        Para CADA activo en la lista:
        1. Usar `fetch_economic_calendar` para eventos económicos relevantes.
        2. Usar `analyze_news_sentiment` para sentimiento de noticias recientes.
        3. Usar `get_social_sentiment` para sentimiento de redes sociales.
        4. Usar `compute_sentiment_factor` para obtener el factor de ajuste final.

        Entrega para cada activo:
          - classification: bullish/bearish/neutral
          - adjustment_pct: factor de ajuste (±25%)
          - eventos económicos próximos de alto impacto
          - volumen de讨论 en redes sociales

        IMPORTANTE: Si encuentras eventos de alto impacto (decisión de tasas,
        IPC, nóminas) en las próximas 4h, márcalo como advertencia.
        """,
        expected_output="JSON con análisis de sentimiento y factor de ajuste para cada activo",
        agent=agent_obj,
    )


# ============================================================================
# FASE 3: VALIDACIÓN DE RIESGO
# ============================================================================

def create_risk_validation_task(agent_obj: Agent, proposal_json: str) -> Task:
    """El Risk Manager valida la propuesta de operación."""
    return Task(
        description=f"""
        **FASE 3: VALIDACIÓN DE RIESGO**

        Propuesta de operación a validar: {proposal_json}

        Debes realizar las siguientes validaciones:

        1. **Validar límites de riesgo**: Usa `validate_risk_limits` para verificar
           que la operación cumpla con riesgo máximo del 1.5%, RR mínimo de 1.8,
           y no exceda el límite de operaciones simultáneas.

        2. **Calcular tamaño de posición**: Usa `calculate_position_size` para
           determinar el número exacto de unidades basado en ATR, Kelly fraccional
           y riesgo máximo.

        3. **Correlación de cartera**: Usa `compute_portfolio_correlation` para
           verificar que el nuevo activo no tenga correlación > 70% con posiciones abiertas.

        4. **Circuit breaker**: Usa `check_circuit_breaker` para verificar que el
           drawdown diario no exceda el 5% y el drawdown total no exceda el 15%.

        Si ALGUNA validación falla, explica claramente por qué y sugiere ajustes.

        Si TODO está OK, entrega el plan de operación completo con:
          - side, symbol, entry, sl, tp
          - units (tamaño de posición)
          - risk_pct, rr_ratio
          - trailing_stop_config
        """,
        expected_output="JSON con resultado de validación y plan de operación aprobado/rechazado",
        agent=agent_obj,
    )


# ============================================================================
# FASE 4: EJECUCIÓN Y MONITOREO
# ============================================================================

def create_execution_task(agent_obj: Agent, trade_plan_json: str) -> Task:
    """El Execution Trader ejecuta la orden y monitorea."""
    return Task(
        description=f"""
        **FASE 4: EJECUCIÓN DE ORDEN**

        Plan de operación a ejecutar: {trade_plan_json}

        Pasos:
        1. **Conectar con MT5**: Usa `connect_mt5` para verificar conexión.
        2. **Verificar salud**: Usa `check_mt5_health` para asegurar que el terminal
           está operativo y el spread es aceptable.
        3. **Ejecutar orden**: Usa `place_market_order` para enviar la orden con
           los parámetros especificados (symbol, side, volume, sl, tp).
        4. **Monitorear**: Después de ejecutar, usa `monitor_open_positions` para
           confirmar que la orden fue colocada correctamente.

        Si el spread es mayor a 20 puntos (verificar con check_mt5_health),
        CANCELA la operación y reporta la razón.

        Entrega un reporte completo de ejecución con:
          - order_id
          - execution_price
          - spread_at_execution
          - status (FILLED / REJECTED / CANCELLED)
          - latency_ms (si está disponible)
          - slippage (diferencia entre precio solicitado y ejecutado)
        """,
        expected_output="JSON con reporte de ejecución de la orden",
        agent=agent_obj,
    )


def create_monitoring_task(agent_obj: Agent) -> Task:
    """El Execution Trader monitorea posiciones abiertas y trailing stops."""
    return Task(
        description="""
        **MONITOREO DE POSICIONES ABIERTAS**

        Debes monitorear todas las posiciones abiertas actualmente:

        1. Usa `monitor_open_positions` para obtener el estado actual.
        2. Para cada posición abierta con ganancia no realizada, verifica si
           se debe activar el trailing stop.
        3. Si una posición ha alcanzado el take profit o stop loss, regístralo.

        Reporte esperado:
          - Número de posiciones abiertas
          - PnL no realizado total
          - Posiciones cerca de SL/TP
          - Sugerencias de trailing stop
        """,
        expected_output="JSON con estado de monitoreo",
        agent=agent_obj,
    )
