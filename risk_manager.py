"""
Gestor de riesgo para cuenta de $200 USD.
Logica de sizing conservadora orientada a crecimiento constante.

Principios:
  - Nunca arriesgar mas del 1% por trade ($2 sobre $200)
  - Circuit breaker diario: -3% del capital ($6)
  - Circuit breaker total : -10% del capital ($20)
  - Cooldown de 15 min (3 velas M5) tras cada perdida
  - Trailing stop activado para proteger ganancias flotantes
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional
from notifications import notify_circuit_breaker, notify_trade_close


@dataclass
class Position:
    side: int            # 1=long, -1=short
    entry_price: float
    stop_price: float
    take_profit: float
    size: float          # en unidades del activo (BTC)
    entry_bar: int
    entry_time: object   # timestamp de apertura
    regime: str = "UNKNOWN"
    signal_quality: int = 0
    strategy: str = "unknown"


class RiskManager:
    def __init__(self, cfg, initial_capital: float = 200.0):
        self.cfg              = cfg
        self.capital          = initial_capital
        self.equity           = initial_capital
        self.initial_capital  = initial_capital
        self.daily_start_equity = initial_capital
        self.current_day      : Optional[date] = None
        self.trades_today     : list = []
        self.last_loss_bar    : int  = -999
        self.circuit_breaker_active: bool = False
        self.all_trades       : list = []    # historial completo para reporte

    # ── Reset diario ──────────────────────────────────────────
    def reset_day_if_needed(self, timestamp) -> bool:
        """Resetea contadores diarios. Retorna True si es dia nuevo."""
        day = timestamp.date() if hasattr(timestamp, "date") else timestamp
        if self.current_day != day:
            self.current_day        = day
            self.daily_start_equity = self.equity
            self.trades_today       = []
            return True
        return False

    # ── Circuit Breakers ──────────────────────────────────────
    def daily_loss_hit(self) -> bool:
        """Retorna True si se alcanzo la perdida maxima diaria."""
        drawdown = (self.daily_start_equity - self.equity) / self.daily_start_equity
        return drawdown >= self.cfg.max_daily_loss

    def total_drawdown_hit(self) -> bool:
        """Retorna True si el drawdown total supero el limite."""
        drawdown = (self.initial_capital - self.equity) / self.initial_capital
        return drawdown >= self.cfg.max_drawdown_total

    def check_circuit_breakers(self) -> Optional[str]:
        """
        Verifica todos los circuit breakers.
        Retorna el motivo del breaker o None si todo esta bien.
        """
        if self.total_drawdown_hit():
            reason = f"Drawdown total supero {self.cfg.max_drawdown_total*100:.0f}%"
            if not self.circuit_breaker_active:
                self.circuit_breaker_active = True
                dd_pct = (self.initial_capital - self.equity) / self.initial_capital * 100
                notify_circuit_breaker(reason, dd_pct, self.equity)
            return reason

        if self.daily_loss_hit():
            dd_pct = (self.daily_start_equity - self.equity) / self.daily_start_equity * 100
            reason = f"Perdida diaria supero {self.cfg.max_daily_loss*100:.0f}% (${self.daily_start_equity - self.equity:.2f})"
            notify_circuit_breaker(reason, dd_pct, self.equity)
            return reason

        return None

    def cooldown_active(self, current_bar: int) -> bool:
        """Retorna True si estamos en periodo de cooldown tras una perdida."""
        return (current_bar - self.last_loss_bar) < self.cfg.cooldown_bars_after_loss

    # ── Calculos de SL/TP ────────────────────────────────────
    def calc_stop_and_tp(self, side: int, entry_price: float, atr_value: float):
        """Calcula stop loss y take profit basados en ATR."""
        if side == 1:   # Long
            stop = entry_price - atr_value * self.cfg.atr_sl_mult
            tp   = entry_price + atr_value * self.cfg.atr_tp_mult
        else:           # Short
            stop = entry_price + atr_value * self.cfg.atr_sl_mult
            tp   = entry_price - atr_value * self.cfg.atr_tp_mult
        return stop, tp

    def calc_position_size(self, entry_price: float, stop_price: float) -> float:
        """
        Sizing basado en riesgo fijo por operacion.
        Con $200 y 1% de riesgo → $2 por trade.
        size = riesgo_usd / distancia_al_stop_en_usd
        """
        risk_amount = self.equity * self.cfg.risk_per_trade
        price_risk  = abs(entry_price - stop_price)
        if price_risk <= 0:
            return 0.0
        size = risk_amount / price_risk
        return round(size, 6)

    # ── Apertura de posicion ──────────────────────────────────
    def open_position(
        self,
        side: int,
        entry_price: float,
        atr_value: float,
        entry_bar: int,
        entry_time,
        regime: str = "UNKNOWN",
        signal_quality: int = 0,
        strategy: str = "unknown",
    ) -> Optional[Position]:
        """Abre una nueva posicion si pasa todas las validaciones."""
        if self.circuit_breaker_active:
            return None

        cb = self.check_circuit_breakers()
        if cb:
            return None

        stop, tp = self.calc_stop_and_tp(side, entry_price, atr_value)
        size      = self.calc_position_size(entry_price, stop)

        if size <= 0:
            return None

        return Position(
            side          = side,
            entry_price   = entry_price,
            stop_price    = stop,
            take_profit   = tp,
            size          = size,
            entry_bar     = entry_bar,
            entry_time    = entry_time,
            regime        = regime,
            signal_quality= signal_quality,
            strategy      = strategy,
        )

    # ── Trailing Stop ─────────────────────────────────────────
    def update_trailing_stop(self, pos: Position, current_price: float, atr_value: float) -> Position:
        """Ajusta el stop loss en la direccion del trade."""
        if not self.cfg.use_trailing_stop:
            return pos
        trail_dist = atr_value * self.cfg.trailing_atr_mult
        if pos.side == 1:
            new_stop = current_price - trail_dist
            if new_stop > pos.stop_price:
                pos.stop_price = new_stop
        else:
            new_stop = current_price + trail_dist
            if new_stop < pos.stop_price:
                pos.stop_price = new_stop
        return pos

    # ── Cierre de posicion ────────────────────────────────────
    def close_position(
        self,
        pos: Position,
        exit_price: float,
        exit_bar: int,
        exit_time,
        reason: str = "unknown",
        send_notification: bool = False,
    ) -> float:
        """Cierra la posicion, actualiza equity y registra el trade."""
        pnl_usd = (exit_price - pos.entry_price) * pos.size * pos.side
        self.equity             += pnl_usd
        if self.equity > self.capital:
            self.capital = self.equity  # Actualiza el high water mark

        if pnl_usd < 0:
            self.last_loss_bar = exit_bar

        # Calcular duracion
        duration_min = 0
        try:
            duration_min = (exit_time - pos.entry_time).total_seconds() / 60
        except Exception:
            pass

        pnl_pct = pnl_usd / (pos.entry_price * pos.size) * 100 if pos.size > 0 else 0

        trade_record = {
            "entry_time"    : pos.entry_time,
            "exit_time"     : exit_time,
            "side"          : "long" if pos.side == 1 else "short",
            "entry_price"   : pos.entry_price,
            "exit_price"    : exit_price,
            "size"          : pos.size,
            "pnl_usd"       : round(pnl_usd, 4),
            "pnl_pct"       : round(pnl_pct, 4),
            "reason"        : reason,
            "duration_min"  : round(duration_min, 1),
            "regime"        : pos.regime,
            "signal_quality": pos.signal_quality,
            "equity_after"  : round(self.equity, 4),
        }
        self.trades_today.append(trade_record)
        self.all_trades.append(trade_record)

        if send_notification:
            notify_trade_close(
                side        = "long" if pos.side == 1 else "short",
                entry_price = pos.entry_price,
                exit_price  = exit_price,
                size        = pos.size,
                pnl_usd     = pnl_usd,
                pnl_pct     = pnl_pct,
                reason      = reason,
                capital     = self.equity,
                duration_min= duration_min,
                timestamp   = exit_time,
            )

        return pnl_usd

    # ── Metricas del dia ──────────────────────────────────────
    def get_daily_stats(self) -> dict:
        """Retorna estadisticas del dia actual."""
        if not self.trades_today:
            return {
                "trades_total": 0,
                "trades_win": 0,
                "trades_loss": 0,
                "pnl_usd": 0.0,
                "pnl_pct": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "dd_max_day": 0.0,
            }

        pnls        = [t["pnl_usd"] for t in self.trades_today]
        wins        = [p for p in pnls if p > 0]
        losses      = [p for p in pnls if p <= 0]
        total_pnl   = sum(pnls)
        pnl_pct     = (total_pnl / self.daily_start_equity) * 100

        # Drawdown maximo intradía
        equities = []
        eq = self.daily_start_equity
        for t in self.trades_today:
            eq += t["pnl_usd"]
            equities.append(eq)
        peak   = self.daily_start_equity
        dd_max = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > dd_max:
                dd_max = dd

        return {
            "trades_total" : len(pnls),
            "trades_win"   : len(wins),
            "trades_loss"  : len(losses),
            "pnl_usd"      : round(total_pnl, 4),
            "pnl_pct"      : round(pnl_pct, 4),
            "best_trade"   : round(max(pnls), 4) if pnls else 0,
            "worst_trade"  : round(min(pnls), 4) if pnls else 0,
            "dd_max_day"   : round(dd_max, 4),
        }

    # ── Metricas globales ─────────────────────────────────────
    def get_global_stats(self) -> dict:
        """Retorna estadisticas de todo el periodo."""
        if not self.all_trades:
            return {"total_trades": 0, "equity": self.equity}

        pnls  = [t["pnl_usd"] for t in self.all_trades]
        wins  = [p for p in pnls if p > 0]
        losses= [p for p in pnls if p <= 0]

        total_return_pct = (self.equity - self.initial_capital) / self.initial_capital * 100
        profit_factor    = sum(wins) / abs(sum(losses)) if losses else float("inf")
        win_rate         = len(wins) / len(pnls) * 100 if pnls else 0

        return {
            "total_trades"     : len(pnls),
            "win_rate_pct"     : round(win_rate, 2),
            "profit_factor"    : round(profit_factor, 2),
            "total_return_pct" : round(total_return_pct, 2),
            "equity"           : round(self.equity, 2),
            "initial_capital"  : self.initial_capital,
            "avg_win_usd"      : round(sum(wins)/len(wins), 4) if wins else 0,
            "avg_loss_usd"     : round(sum(losses)/len(losses), 4) if losses else 0,
        }
