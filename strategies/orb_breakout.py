"""
ORB — Opening Range Breakout para SPY 15min.
Estrategia de ruptura del rango de apertura en la sesión americana.

Genera ~2-3 trades/semana complementando la estrategia principal de 1H.
Combinadas: SPY (1H) + IWM (1H) + ORB (15min) = 3-5 trades/semana
"""

import pandas as pd
import numpy as np
from indicators import atr


def generate_orb_signals(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Genera señales ORB (Opening Range Breakout) en timeframe 15min.
    
    Lógica:
      1. Identificar la primera vela de cada día (9:30 ET)
      2. Rango de apertura = [low de primera vela, high de primera vela]
      3. Si precio rompe el high del rango → LONG
      4. Si precio rompe el low del rango → SHORT
      5. SL = lado opuesto del rango | TP = rango * 1.5 o 2.0
    
    Args:
        df: DataFrame OHLCV con timestamp en ET (America/New_York)
        cfg: StrategyConfig con parámetros
    
    Returns:
        DataFrame con columna 'signal'
    """
    out = df.copy()
    out['signal'] = 0
    
    # Yahoo Finance devuelve timestamps en America/New_York
    # Si ya tienen timezone, usarlos; si no, asumir ET
    if out['timestamp'].dt.tz is not None:
        out['timestamp_et'] = out['timestamp']
    else:
        # Asumir que datos sin tz están en ET (Yahoo)
        out['timestamp_et'] = out['timestamp'].dt.tz_localize('America/New_York', ambiguous='NaT')
        # Si falló, intentar UTC
        if out['timestamp_et'].isna().all():
            out['timestamp_et'] = out['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
    
    out['date'] = out['timestamp_et'].dt.date
    out['time_str'] = out['timestamp_et'].dt.strftime('%H:%M')
    
    # Calcular ATR para SL/TP
    atr_vals = atr(out, 14)
    out['atr'] = atr_vals
    
    # Identificar apertura de cada día (primeras N velas = rango de apertura)
    orb_minutes = getattr(cfg, 'orb_minutes', 30)  # 30 min por defecto
    orb_bars = orb_minutes // 15  # velas de 15min que forman el rango
    
    orb_highs = {}
    orb_lows = {}
    orb_triggered = {}  # evita re-entrar el mismo día
    
    for i, row in out.iterrows():
        date = row['date']
        time_str = row['time_str']
        
        # Solo en sesión regular (9:30-16:00 ET)
        hour_min = int(time_str.split(':')[0]) * 60 + int(time_str.split(':')[1])
        if hour_min < 570 or hour_min > 960:  # 9:30 = 570min, 16:00 = 960min
            continue
        
        # Inicializar rango de apertura al empezar el día
        if date not in orb_highs:
            orb_highs[date] = None
            orb_lows[date] = None
            orb_triggered[date] = False
        
        # Determinar rango de apertura (primeras N velas del día)
        bar_of_day = out[out['date'] == date].index.get_loc(i) if i in out[out['date'] == date].index else -1
        if isinstance(bar_of_day, (int, np.integer)) and 0 <= bar_of_day < orb_bars:
            # Acumular rango en las primeras velas
            if orb_highs[date] is None or row['high'] > orb_highs[date]:
                orb_highs[date] = row['high']
            if orb_lows[date] is None or row['low'] < orb_lows[date]:
                orb_lows[date] = row['low']
            continue  # No operar durante la formación del rango
        
        # Si el rango ya está definido y no se ha disparado aún
        if (orb_highs[date] is not None and orb_lows[date] is not None 
            and not orb_triggered[date]):
            
            range_width = orb_highs[date] - orb_lows[date]
            tp_mult = getattr(cfg, 'orb_tp_mult', 1.5)
            
            # Breakout LONG
            if row['close'] > orb_highs[date]:
                out.at[i, 'signal'] = 1
                out.at[i, 'orb_entry'] = 'LONG'
                out.at[i, 'orb_range_high'] = orb_highs[date]
                out.at[i, 'orb_range_low'] = orb_lows[date]
                out.at[i, 'orb_sl'] = orb_lows[date]
                out.at[i, 'orb_tp'] = row['close'] + range_width * tp_mult
                orb_triggered[date] = True
                
            # Breakout SHORT
            elif row['close'] < orb_lows[date]:
                out.at[i, 'signal'] = -1
                out.at[i, 'orb_entry'] = 'SHORT'
                out.at[i, 'orb_range_high'] = orb_highs[date]
                out.at[i, 'orb_range_low'] = orb_lows[date]
                out.at[i, 'orb_sl'] = orb_highs[date]
                out.at[i, 'orb_tp'] = row['close'] - range_width * tp_mult
                orb_triggered[date] = True
    
    return out
