"""
Sistema de notificaciones Telegram para el bot de trading.
Envia alertas en tiempo real: entradas, salidas, SL, TP y resumen diario.
"""

import requests
import logging
from datetime import datetime, timezone
from typing import Optional
from config import TELEGRAM

logger = logging.getLogger(__name__)


def _send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Envia un mensaje al chat de Telegram configurado."""
    if not TELEGRAM.bot_token or not TELEGRAM.chat_id:
        logger.warning("Telegram no configurado. Revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM.bot_token}/sendMessage"
        payload = {
            "chat_id": TELEGRAM.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Telegram error {resp.status_code}: {resp.text}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error enviando mensaje Telegram: {e}")
        return False


def notify_trade_open(
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    size: float,
    capital: float,
    risk_usd: float,
    regime: str = "N/A",
    atr_pct: float = 0.0,
    timestamp: Optional[datetime] = None,
):
    """Notifica apertura de posicion."""
    if not TELEGRAM.notify_on_entry:
        return
    ts = timestamp or datetime.now(timezone.utc)
    direction = "🟢 LONG" if side.upper() == "LONG" else "🔴 SHORT"
    sl_dist_pct = abs(entry_price - stop_loss) / entry_price * 100
    tp_dist_pct = abs(take_profit - entry_price) / entry_price * 100
    rr = tp_dist_pct / sl_dist_pct if sl_dist_pct > 0 else 0

    msg = (
        f"<b>{'='*30}</b>\n"
        f"<b>🚀 NUEVA OPERACION ABIERTA</b>\n"
        f"<b>{'='*30}</b>\n"
        f"\n"
        f"<b>Direccion :</b> {direction}\n"
        f"<b>Activo    :</b> BCH/USDT 1H\n"
        f"<b>Estrategia:</b> MACD Cross\n"
        f"<b>Precio    :</b> <code>${entry_price:,.2f}</code>\n"
        f"<b>Stop Loss :</b> <code>${stop_loss:,.2f}</code>  (-{sl_dist_pct:.3f}%)\n"
        f"<b>Take Profit:</b> <code>${take_profit:,.2f}</code>  (+{tp_dist_pct:.3f}%)\n"
        f"<b>R:R       :</b> 1:{rr:.2f}\n"
        f"\n"
        f"<b>Tamano    :</b> {size:.6f} BTC\n"
        f"<b>Riesgo    :</b> ${risk_usd:.2f} ({risk_usd/capital*100:.1f}% del capital)\n"
        f"<b>Capital   :</b> ${capital:.2f}\n"
        f"\n"
        f"<b>Regimen   :</b> {regime}\n"
        f"<b>ATR%      :</b> {atr_pct:.4f}%\n"
        f"<b>Hora UTC  :</b> {ts.strftime('%H:%M:%S')}\n"
        f"<b>{'='*30}</b>"
    )
    _send_message(msg)


def notify_trade_close(
    side: str,
    entry_price: float,
    exit_price: float,
    size: float,
    pnl_usd: float,
    pnl_pct: float,
    reason: str,
    capital: float,
    duration_min: float = 0,
    timestamp: Optional[datetime] = None,
):
    """Notifica cierre de posicion con resultado."""
    if not TELEGRAM.notify_on_exit:
        return
    ts = timestamp or datetime.now(timezone.utc)
    direction = "🟢 LONG" if side.upper() == "LONG" else "🔴 SHORT"

    if pnl_usd > 0:
        result_icon = "✅ GANANCIA"
        pnl_str = f"+${pnl_usd:.2f} (+{pnl_pct:.3f}%)"
    elif reason == "stop":
        result_icon = "❌ STOP LOSS"
        pnl_str = f"-${abs(pnl_usd):.2f} (-{abs(pnl_pct):.3f}%)"
    else:
        result_icon = "⚠️ PERDIDA"
        pnl_str = f"-${abs(pnl_usd):.2f} (-{abs(pnl_pct):.3f}%)"

    reason_map = {
        "stop": "Stop Loss tocado",
        "take_profit": "Take Profit alcanzado ✨",
        "trailing_stop": "Trailing Stop activado",
        "end_of_session": "Cierre de sesion",
        "circuit_breaker": "Circuit Breaker activado",
        "manual": "Cierre manual",
    }

    msg = (
        f"<b>{'='*30}</b>\n"
        f"<b>{result_icon}</b>\n"
        f"<b>{'='*30}</b>\n"
        f"\n"
        f"<b>Direccion :</b> {direction}\n"
        f"<b>Entrada   :</b> <code>${entry_price:,.2f}</code>\n"
        f"<b>Salida    :</b> <code>${exit_price:,.2f}</code>\n"
        f"<b>Resultado :</b> <b>{pnl_str}</b>\n"
        f"<b>Razon     :</b> {reason_map.get(reason, reason)}\n"
        f"<b>Duracion  :</b> {duration_min:.0f} minutos\n"
        f"\n"
        f"<b>Capital   :</b> ${capital:.2f}\n"
        f"<b>Hora UTC  :</b> {ts.strftime('%H:%M:%S')}\n"
        f"<b>{'='*30}</b>"
    )
    _send_message(msg)


def notify_circuit_breaker(reason: str, drawdown_pct: float, capital: float):
    """Notifica activacion del circuit breaker — CRITICO."""
    if not TELEGRAM.notify_circuit_breaker:
        return
    msg = (
        f"<b>🚨🚨🚨 CIRCUIT BREAKER ACTIVADO 🚨🚨🚨</b>\n"
        f"\n"
        f"<b>Razon     :</b> {reason}\n"
        f"<b>Drawdown  :</b> -{abs(drawdown_pct):.2f}%\n"
        f"<b>Capital   :</b> ${capital:.2f}\n"
        f"\n"
        f"<b>ACCION    :</b> Trading DETENIDO automaticamente.\n"
        f"Se requiere revision manual para reanudar.\n"
        f"<b>Hora UTC  :</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    _send_message(msg)


def notify_regime_change(old_regime: str, new_regime: str, score: int):
    """Notifica cambio de regimen de mercado."""
    if not TELEGRAM.notify_regime_change:
        return
    regime_icons = {
        "TREND_BULL": "📈",
        "TREND_BEAR": "📉",
        "RANGE": "↔️",
        "HIGH_VOL": "⚡",
    }
    icon = regime_icons.get(new_regime, "🔄")
    msg = (
        f"<b>{icon} CAMBIO DE REGIMEN DE MERCADO</b>\n"
        f"\n"
        f"<b>Anterior  :</b> {old_regime}\n"
        f"<b>Actual    :</b> {new_regime}\n"
        f"<b>Score     :</b> {score}/10\n"
        f"<b>Hora UTC  :</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
    )
    _send_message(msg)


def notify_daily_summary(
    date_str: str,
    trades_total: int,
    trades_win: int,
    trades_loss: int,
    pnl_usd: float,
    pnl_pct: float,
    capital_start: float,
    capital_end: float,
    best_trade: float,
    worst_trade: float,
    monthly_pnl_pct: float,
    dd_max_day: float,
    session_stats: dict,
):
    """
    Envia el resumen completo del dia al cierre.
    Incluye todas las operaciones, estadisticas y progreso mensual.
    """
    if not TELEGRAM.notify_daily_summary:
        return

    win_rate = (trades_win / trades_total * 100) if trades_total > 0 else 0
    month_target = 1.5
    month_progress = (monthly_pnl_pct / month_target * 100) if month_target > 0 else 0

    if pnl_usd >= 0:
        day_icon = "✅"
        pnl_display = f"+${pnl_usd:.2f} (+{pnl_pct:.2f}%)"
    else:
        day_icon = "❌"
        pnl_display = f"-${abs(pnl_usd):.2f} (-{abs(pnl_pct):.2f}%)"

    progress_bar = "█" * int(min(month_progress, 100) / 10) + "░" * (10 - int(min(month_progress, 100) / 10))

    # Sesion con mejor performance
    best_session = max(session_stats, key=lambda k: session_stats[k].get("pnl", 0)) if session_stats else "N/A"

    msg = (
        f"<b>{'═'*32}</b>\n"
        f"<b>📊 RESUMEN DIARIO — {date_str}</b>\n"
        f"<b>{'═'*32}</b>\n"
        f"\n"
        f"<b>{day_icon} Resultado del dia:</b>\n"
        f"   PnL: <b>{pnl_display}</b>\n"
        f"\n"
        f"<b>📈 Operaciones:</b>\n"
        f"   Total : {trades_total}\n"
        f"   Ganad.: {trades_win} ✅\n"
        f"   Perd. : {trades_loss} ❌\n"
        f"   WR    : {win_rate:.1f}%\n"
        f"\n"
        f"<b>💰 Capital:</b>\n"
        f"   Inicio: ${capital_start:.2f}\n"
        f"   Fin   : ${capital_end:.2f}\n"
        f"   DD max: -{abs(dd_max_day):.2f}%\n"
        f"\n"
        f"<b>🏆 Mejor trade  :</b> +${best_trade:.2f}\n"
        f"<b>💔 Peor trade   :</b> -${abs(worst_trade):.2f}\n"
        f"\n"
        f"<b>🎯 Progreso mensual:</b>\n"
        f"   {monthly_pnl_pct:+.2f}% de objetivo 1.5%\n"
        f"   [{progress_bar}] {month_progress:.0f}%\n"
        f"\n"
        f"<b>⏰ Mejor sesion hoy:</b> {best_session} UTC\n"
        f"\n"
        f"<b>{'═'*32}</b>\n"
        f"<i>Bot activo 24/7 — Proxima sesion: 14:00 UTC</i>"
    )
    _send_message(msg)


def notify_system_start(capital: float, mode: str = "PAPER"):
    """Notifica que el bot ha iniciado."""
    mode_icon = "🟡" if mode == "PAPER" else "🔴"
    msg = (
        f"<b>{'='*30}</b>\n"
        f"<b>{mode_icon} BOT DE TRADING INICIADO</b>\n"
        f"<b>{'='*30}</b>\n"
        f"\n"
        f"<b>Modo      :</b> {mode}\n"
        f"<b>Activo    :</b> BCH/USDT 1H\n"
        f"<b>Capital   :</b> ${capital:.2f}\n"
        f"<b>Estrategia:</b> MACD Cross 1H\n"
        f"<b>Riesgo/op :</b> 0.5% (${capital*0.005:.2f})\n"
        f"<b>Sesion    :</b> 24h Lun-Vie\n"
        f"\n"
        f"<b>Hora UTC  :</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>{'='*30}</b>"
    )
    _send_message(msg)


def notify_error(error_msg: str, context: str = "Sistema"):
    """Notifica errores criticos del sistema."""
    msg = (
        f"<b>⚠️ ERROR EN {context.upper()}</b>\n"
        f"\n"
        f"<code>{error_msg[:500]}</code>\n"
        f"\n"
        f"<b>Hora UTC:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
    )
    _send_message(msg)
