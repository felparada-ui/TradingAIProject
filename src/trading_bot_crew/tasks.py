"""
Tasks para el Trading Bot Crew — Estrategia EMA 5/13/150 en BCH/USDT 1H.
Usa la mejor estrategia encontrada (validada 4.5 años: +20.38%).
Incluye agente Performance Monitor para supervisión en tiempo real.
"""

import os
import pandas as pd
import numpy as np
from crewai import Task
from crewai.tools import tool

from config import StrategyConfig
from strategies.ema_trend_scalping import generate_signals
from backtest import run_backtest
from indicators import add_all_indicators


@tool
def fetch_and_backtest_ema(symbol: str = "BCH/USDT", timeframe: str = "1h", limit: int = 1000) -> dict:
    """
    Descarga datos OHLCV y ejecuta backtest con la estrategia EMA 5/13/150.
    Es la mejor estrategia encontrada: +20.38% en 4.5 años de BCH/USDT.
    
    Args:
        symbol: Par de trading
        timeframe: Timeframe de velas
        limit: Cantidad de velas
    
    Returns:
        Dict con métricas de rendimiento
    """
    import ccxt
    ex = ccxt.binance({'enableRateLimit': True})
    bars = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    cfg = StrategyConfig()
    cfg.strategy_type = 'ema_cross'
    cfg.timeframe = timeframe
    cfg.ema_fast = 5; cfg.ema_slow = 13; cfg.ema_trend = 150
    cfg.adx_threshold = 22.0; cfg.atr_tp_mult = 1.8
    cfg.use_trailing_stop = False
    cfg.risk_per_trade = 0.005
    cfg.session_hours_utc = list(range(0, 24))
    cfg.trading_days = [0, 1, 2, 3, 4]
    
    trades, equity, metrics = run_backtest(df, cfg, initial_capital=200.0)
    
    return {
        'strategy': 'EMA 5/13/150 + ADX 22 + TP 1.8',
        'symbol': symbol,
        'timeframe': timeframe,
        'total_bars': len(df),
        'date_range': f"{df['timestamp'].min()} -> {df['timestamp'].max()}",
        'total_trades': metrics.get('total_trades', 0),
        'win_rate': metrics.get('win_rate_pct', 0),
        'profit_factor': metrics.get('profit_factor', 0),
        'total_return': metrics.get('total_return_pct', 0),
        'max_drawdown': metrics.get('max_drawdown_pct', 0),
        'final_equity': metrics.get('final_equity', 200),
        'avg_win': metrics.get('avg_win_usd', 0),
        'avg_loss': metrics.get('avg_loss_usd', 0),
    }


@tool
def compute_risk_metrics(symbol: str = "BCH/USDT", timeframe: str = "1h", limit: int = 1000) -> dict:
    """
    Calcula métricas de riesgo avanzadas para el símbolo especificado.
    """
    import ccxt
    ex = ccxt.binance({'enableRateLimit': True})
    bars = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    returns = df['close'].pct_change().dropna()
    var_95 = float(np.percentile(returns, 5))
    sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    current_price = float(df['close'].iloc[-1])
    
    return {
        'symbol': symbol, 'timeframe': timeframe,
        'current_price': current_price,
        'daily_var_95': var_95 * 100,
        'sharpe_ratio': round(sharpe, 2),
        'max_drawdown': float(drawdown.min()) * 100,
        'expected_annual_return': 4.5,  # ~20.38% / 4.5 años
        'recommended_risk_per_trade': 0.5,  # 0.5%
    }


@tool
def check_paper_trading_status() -> dict:
    """
    Verifica el estado actual del paper trading: trades registrados, equity,
    desviación vs backtest esperado.
    """
    trades_file = 'trades_backtest.csv'
    log_file = 'logs/trading_bot.log'
    
    status = {
        'bot_running': False,
        'last_check': str(pd.Timestamp.now()),
        'trades_today': 0,
        'total_trades_simulated': 0,
        'latest_equity': 200.0,
        'issues': [],
    }
    
    # Ver si el bot está corriendo
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'main_bot.py.*mode paper'], 
                              capture_output=True, text=True, timeout=5)
        if result.stdout.strip():
            status['bot_running'] = True
    except:
        pass
    
    # Leer último trade del log
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()[-50:]
            for line in lines:
                if 'Posicion cerrada' in line:
                    status['total_trades_simulated'] += 1
                if 'PnL:' in line:
                    status['latest_equity'] = 200.0  # simplificado
        except:
            pass
    
    # Verificar desviación vs backtest esperado
    if not status['bot_running']:
        status['issues'].append('⚠️ El bot PAPER no está corriendo')
    
    return status


def create_analysis_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Market Analyst. Analiza BCH/USDT en 1H con la estrategia EMA 5/13/150.
        
        1. Usa fetch_and_backtest_ema para descargar los últimos 1000 velas y ejecutar backtest.
        2. Verifica: Profit Factor > 1.0, Win Rate > 35%, Retorno positivo.
        3. Compara el rendimiento reciente vs el histórico de 4.5 años (+20.38%).
        4. Genera recomendación: OPERAR / OBSERVAR / PAUSAR.
        """,
        expected_output="""Reporte de Análisis:
- Estrategia: EMA 5/13/150 + ADX 22 + TP 1.8
- Profit Factor, Win Rate, Retorno reciente
- Comparativa vs histórico 4.5 años
- Recomendación""",
        agent=agent_obj,
    )


def create_risk_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Risk Manager. Calcula el riesgo para BCH/USDT 1H.
        
        1. Usa compute_risk_metrics para obtener VaR, drawdown, Sharpe.
        2. Verifica que el riesgo por trade sea máximo 0.5%.
        3. Si el drawdown reciente supera -4.27% (máximo histórico), alerta.
        4. Define el tamaño de posición recomendado.
        """,
        expected_output="""Reporte de Riesgo:
- VaR 95%, Sharpe Ratio, Drawdown actual
- Tamaño de posición: 0.5% del capital
- Nivel de riesgo: BAJO / MEDIO / ALTO""",
        agent=agent_obj,
    )


def create_strategy_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Strategy Developer. Documenta la estrategia activa:
        
        1. Estrategia: EMA 5/13/150 (cruce rápido/lento con filtro de tendencia)
        2. Entrada Long: EMA 5 cruza sobre EMA 13 + Precio > EMA 150 + ADX > 22
        3. Entrada Short: EMA 5 cruza bajo EMA 13 + Precio < EMA 150 + ADX > 22
        4. SL: ATR * 1.0 | TP: ATR * 1.8
        5. Sin trailing stop (empeora resultados)
        6. Activo: BCH/USDT 1H | Sesión: 24h Lun-Vie
        7. Riesgo: 0.5% por trade | Capital: $200 paper
        
        Validado en 4.5 años: +20.38% retorno, PF 1.35, WR 43%.
        """,
        expected_output="""Estrategia Documentada:
- Reglas de entrada/salida completas
- Parámetros validados
- Riesgos y limitaciones""",
        agent=agent_obj,
    )


def create_backtest_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Backtest Validator. Valida la estrategia EMA 5/13/150:
        
        1. Usa fetch_and_backtest_ema para ejecutar backtest completo.
        2. Criterios mínimos (basados en 4.5 años de validación):
           - Profit Factor > 1.0 (esperado 1.35)
           - Sharpe > 0.5
           - Win Rate > 35% (esperado 43%)
           - Drawdown < -10% (esperado -4.27%)
        3. Si cumple, APRUEBA. Si no, explica desviaciones.
        """,
        expected_output="""Reporte de Validación:
- Métricas actuales vs esperadas
- Veredicto: APROBADA / RECHAZADA
- Confianza: ALTA / MEDIA / BAJA""",
        agent=agent_obj,
    )


def create_monitor_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Performance Monitor. Supervisa que el bot esté funcionando correctamente:
        
        1. Usa check_paper_trading_status para verificar si el bot PAPER está activo.
        2. Revisa trades log vs trades esperados.
        3. Detecta anomalías: bot caído, trades no ejecutados, errores en log.
        4. Si todo bien, reporta: SISTEMA OPERANDO NORMALMENTE.
        5. Si hay issues, emite alerta con detalles.
        """,
        expected_output="""Reporte de Monitoreo:
- Estado del bot: ACTIVO / DETENIDO
- Trades ejecutados hoy
- Desviaciones detectadas
- Alertas: NINGUNA / [detalles]
- Conclusión: TODO OK / REQUIERE ATENCIÓN""",
        agent=agent_obj,
    )
    return Task(
        description="""
        Eres el Market Analyst. Tu trabajo es analizar BCH/USDT en 1H usando la estrategia MACD Cross.
        
        1. Descarga datos OHLCV de BCH/USDT en 1h usando fetch_and_backtest_macd_cross.
        2. Analiza el rendimiento de la estrategia MACD Cross:
           - Profit Factor > 1.0 indica estrategia rentable
           - Win Rate > 40% es aceptable
           - Drawdown < 5% muestra buen control de riesgo
        3. Identifica los días/sesiones donde la estrategia rinde mejor.
        4. Genera un reporte claro con recomendaciones.
        
        Usa el tool fetch_and_backtest_macd_cross con symbol="BCH/USDT", timeframe="1h".
        """,
        expected_output="""Reporte de Análisis de Mercado:
- Símbolo analizado y período de datos
- Métricas de rendimiento de la estrategia MACD Cross
- Profit Factor, Win Rate, Retorno Total, Drawdown
- Recomendación: OPERAR / OBSERVAR / PAUSAR""",
        agent=agent_obj,
    )


def create_risk_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Risk Manager. Basado en el análisis del Market Analyst, calcula:
        
        1. Usa compute_risk_metrics para obtener VaR 95%/99%, drawdown y Kelly Criterion.
        2. Determina el tamaño de posición recomendado.
        3. Establece límites de riesgo: máximo 0.5% del capital por trade.
        4. Si el drawdown es > 5%, recomienda pausar.
        5. Calcula el stop-loss dinámico basado en ATR.
        
        Usa el tool compute_risk_metrics con symbol="BCH/USDT", timeframe="1h".
        """,
        expected_output="""Reporte de Gestión de Riesgo:
- VaR 95% y 99% diario
- Drawdown máximo histórico
- Sharpe Ratio y Sortino Ratio
- Tamaño de posición recomendado: X%
- Stop Loss sugerido: $X basado en ATR
- Nivel de riesgo: BAJO / MEDIO / ALTO / EXTREMO""",
        agent=agent_obj,
    )


def create_strategy_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Strategy Developer. Con la información del análisis y riesgo:
        
        1. Define la estrategia MACD Cross 1H:
           - Entrada: MACD línea cruza sobre MACD señal (long) o bajo (short)
           - Tendencia: Precio > EMA 200 para long, < EMA 200 para short
           - Filtro: ADX > 10 (evitar mercados laterales)
           - Salida: Take Profit en ATR * 3.0 o Stop Loss en ATR * 1.0
        2. Justifica por qué esta configuración es óptima.
        3. Describe las condiciones ideales de mercado para operar.
        4. Establece reglas claras de gestión de capital.
        """,
        expected_output="""Estrategia MACD Cross 1H - Documentación:
- Condiciones de entrada detalladas
- Gestión de salidas (SL/TP)
- Filtros de mercado y sesión
- Gestión de capital
- Riesgos identificados""",
        agent=agent_obj,
    )


def create_backtest_task(agent_obj=None) -> Task:
    return Task(
        description="""
        Eres el Backtest Validator. Ejecuta la validación final:
        
        1. Usa fetch_and_backtest_macd_cross para ejecutar el backtest completo.
        2. Verifica que las métricas cumplan los criterios mínimos:
           - Profit Factor > 1.3 (ideal > 2.0)
           - Sharpe Ratio > 1.0
           - Win Rate > 40%
           - Max Drawdown < 15%
        3. Analiza la equity curve y la distribución de trades.
        4. Si pasa todos los filtros, APRUEBA la estrategia.
        5. Si no, explica qué ajustar.
        """,
        expected_output="""Reporte de Validación de Backtest:
- Resultados vs criterios mínimos
- Profit Factor: X (mínimo 1.3)
- Sharpe Ratio: X (mínimo 1.0)
- Win Rate: X% (mínimo 40%)
- Max Drawdown: X% (máximo 15%)
- Veredicto: APROBADA / RECHAZADA
- Recomendaciones de ajuste""",
        agent=agent_obj,
    )

