"""
Motor de trading en VIVO para ATFS sobre BTC/USDT H1.
Corre en un loop al cierre de cada vela (1 hora por defecto).
Envia notificaciones Telegram en tiempo real.

Modos:
  PAPER : Simula trades sin dinero real (recomendado para validar)
  LIVE  : Ejecuta ordenes reales en Binance (solo con capital validado)
"""

import time
import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import STRATEGY as CFG, EXCHANGE, TELEGRAM
from data_feed import get_latest_data, update_data_incremental, validate_data_quality
from strategies.atfs import generate_signals
from risk_manager import RiskManager, Position
from notifications import (
    notify_trade_open,
    notify_trade_close,
    notify_circuit_breaker,
    notify_regime_change,
    notify_daily_summary,
    notify_system_start,
    notify_error,
)

logger = logging.getLogger(__name__)


def _timeframe_to_seconds(tf: str) -> int:
    """Convierte un timeframe como '1h', '4h', '30m' a segundos."""
    tf = tf.lower().strip()
    if tf.endswith("h"):
        return int(tf.replace("h", "")) * 3600
    elif tf.endswith("m"):
        return int(tf.replace("m", "")) * 60
    elif tf.endswith("d"):
        return int(tf.replace("d", "")) * 86400
    return 3600  # default 1h


class LiveEngine:
    """
    Motor principal de trading en vivo.
    Ejecuta la estrategia MACD Cross 1H en tiempo real.
    Timeframe configurable desde STRATEGY.timeframe.
    """

    def __init__(
        self,
        initial_capital: float = 200.0,
        mode: str = "PAPER",
        csv_warmup_path: Optional[str] = None,
    ):
        self.cfg             = CFG
        self.initial_capital = initial_capital
        self.mode            = mode.upper()
        self.csv_warmup_path = csv_warmup_path
        self.candle_seconds  = _timeframe_to_seconds(self.cfg.timeframe)

        self.rm              = RiskManager(self.cfg, initial_capital)
        self.position        : Optional[Position] = None
        self.df_hist         : Optional[pd.DataFrame] = None
        self.last_regime     : str = "RANGE"
        self.bar_counter     : int = 0
        self.monthly_pnl_usd : float = 0.0
        self.current_month   : str = ""
        self.running         : bool = False

    # ── Inicializacion ────────────────────────────────────────
    def initialize(self) -> bool:
        """Carga datos iniciales (warmup con CSV o CCXT)."""
        logger.info(f"Inicializando LiveEngine en modo {self.mode}...")

        # Intentar warmup con CSV local (mas rapido que descargar 500 velas)
        if self.csv_warmup_path:
            from data_feed import load_from_csv
            df_warmup = load_from_csv(self.csv_warmup_path)
            if df_warmup is not None:
                # Usar las ultimas 500 velas del CSV + completar con CCXT
                self.df_hist = df_warmup.tail(500).reset_index(drop=True)
                logger.info(f"Warmup desde CSV: {len(self.df_hist)} velas")

        # Si no hay CSV o fallo, usar CCXT directamente
        if self.df_hist is None:
            self.df_hist = get_latest_data(self.cfg, limit=500)

        if not validate_data_quality(self.df_hist):
            logger.error("Datos de inicializacion insuficientes")
            notify_error("Fallo al cargar datos iniciales", "LiveEngine")
            return False

        logger.info(f"Datos iniciales: {len(self.df_hist)} velas | "
                    f"Ultima: {self.df_hist['timestamp'].iloc[-1]} UTC")

        notify_system_start(self.initial_capital, self.mode)
        return True

    # ── Loop principal ────────────────────────────────────────
    def run(self):
        """Ejecuta el bot indefinidamente hasta detencion manual."""
        if not self.initialize():
            return

        self.running = True
        logger.info("Bot de trading iniciado. Esperando cierre de vela M5...")

        while self.running:
            try:
                self._wait_for_candle_close()
                self._process_new_candle()

            except KeyboardInterrupt:
                logger.info("Detencion manual solicitada")
                self.running = False

            except Exception as e:
                logger.error(f"Error en loop principal: {e}")
                notify_error(str(e), "LiveEngine.run")
                time.sleep(30)  # Esperar antes de reintentar

        logger.info("Bot detenido.")

    # ── Esperar al cierre de vela ─────────────────────────────
    def _wait_for_candle_close(self):
        """Espera al proximo cierre de vela segun el timeframe configurado."""
        now     = datetime.now(timezone.utc)
        secs    = now.minute * 60 + now.second
        wait    = self.candle_seconds - (secs % self.candle_seconds)
        wait    += 3  # margen de seguridad
        tf_label = self.cfg.timeframe
        logger.info(f"Proxima vela {tf_label} en {wait}s "
                    f"({(now + timedelta(seconds=wait)).strftime('%H:%M:%S')} UTC)")
        time.sleep(wait)

    # ── Procesar nueva vela ───────────────────────────────────
    def _process_new_candle(self):
        """Procesamiento completo al cierre de cada vela M5."""
        self.bar_counter += 1

        # 1. Actualizar datos
        self.df_hist = update_data_incremental(self.df_hist, self.cfg)
        if not validate_data_quality(self.df_hist, min_rows=210):
            logger.warning("Datos insuficientes para generar señales")
            return

        # 2. Calcular indicadores y señales
        data = generate_signals(self.df_hist, self.cfg)
        data = data.dropna(subset=["ema_fast", "ema_slow", "ema_trend", "adx", "atr"])
        if data.empty:
            return

        last = data.iloc[-1]
        ts   = last["timestamp"]

        # 3. Reset diario y check de dia nuevo
        is_new_day = self.rm.reset_day_if_needed(ts)
        if is_new_day:
            self._handle_new_day(ts)

        # 4. Verificar circuit breakers
        cb_reason = self.rm.check_circuit_breakers()
        if cb_reason or self.rm.circuit_breaker_active:
            logger.warning(f"Circuit breaker activo: {cb_reason}")
            return

        # 5. Detectar cambio de regimen
        current_regime = last.get("regime", "RANGE")
        if current_regime != self.last_regime:
            score = self._calc_regime_score(last)
            notify_regime_change(self.last_regime, current_regime, score)
            self.last_regime = current_regime

        # 6. Gestionar posicion abierta
        if self.position is not None:
            self._manage_open_position(last, ts)

        # 7. Evaluar nueva entrada
        if self.position is None:
            self._evaluate_entry(last, ts)

        # Logging del estado
        self._log_status(last, ts)

    def _manage_open_position(self, last_row: pd.Series, ts):
        """Actualiza el trailing stop, time stop y verifica SL/TP."""
        # Time stop
        ts_bars = getattr(self.cfg, "time_stop_bars", None)
        if ts_bars is not None and (self.bar_counter - self.position.entry_bar) >= ts_bars:
            exit_price = last_row["close"]
            reason = "time_stop"

            if self.mode == "LIVE":
                self._execute_close_order(exit_price)

            pnl = self.rm.close_position(
                self.position, exit_price, self.bar_counter, ts,
                reason, send_notification=True
            )
            logger.info(f"Posicion cerrada por TIME STOP: {reason} | PnL: ${pnl:.4f} | Equity: ${self.rm.equity:.2f}")
            self.position = None
            return

        self.position = self.rm.update_trailing_stop(
            self.position, last_row["close"], last_row["atr"]
        )

        hit_stop = (last_row["low"]  <= self.position.stop_price) if self.position.side == 1 \
                   else (last_row["high"] >= self.position.stop_price)
        hit_tp   = (last_row["high"] >= self.position.take_profit) if self.position.side == 1 \
                   else (last_row["low"] <= self.position.take_profit)

        if hit_stop or hit_tp:
            exit_price = self.position.stop_price if hit_stop else self.position.take_profit
            reason     = "stop" if hit_stop else "take_profit"

            if self.mode == "LIVE":
                self._execute_close_order(exit_price)

            pnl = self.rm.close_position(
                self.position, exit_price, self.bar_counter, ts,
                reason, send_notification=True
            )

            logger.info(f"Posicion cerrada: {reason} | PnL: ${pnl:.4f} | Equity: ${self.rm.equity:.2f}")
            self.position = None

    # ── Evaluar entrada ───────────────────────────────────────
    def _evaluate_entry(self, last_row: pd.Series, ts):
        """Evalua si se cumplen las condiciones para abrir posicion."""
        # Verificar todos los filtros
        if self.rm.daily_loss_hit():
            return
        if self.rm.cooldown_active(self.bar_counter):
            return
        if not last_row.get("in_session", False):
            return

        signal = last_row.get("signal_atfs", 0)
        if signal == 0:
            return

        side = 1 if signal == 1 else -1

        # Abrir posicion
        new_position = self.rm.open_position(
            side          = side,
            entry_price   = last_row["close"],
            atr_value     = last_row["atr"],
            entry_bar     = self.bar_counter,
            entry_time    = ts,
            regime        = last_row.get("regime", "UNKNOWN"),
            signal_quality= int(last_row.get("signal_quality", 0)),
        )

        if new_position is None:
            return

        if self.mode == "LIVE":
            success = self._execute_open_order(new_position)
            if not success:
                return

        self.position = new_position
        risk_usd = abs(new_position.entry_price - new_position.stop_price) * new_position.size

        # Notificar apertura
        notify_trade_open(
            side        = "long" if side == 1 else "short",
            entry_price = new_position.entry_price,
            stop_loss   = new_position.stop_price,
            take_profit = new_position.take_profit,
            size        = new_position.size,
            capital     = self.rm.equity,
            risk_usd    = risk_usd,
            regime      = new_position.regime,
            atr_pct     = float(last_row.get("atr_pct", 0)) * 100,
            timestamp   = ts,
        )

        logger.info(
            f"ENTRADA {'LONG' if side==1 else 'SHORT'} | "
            f"BTC/USDT: ${new_position.entry_price:,.2f} | "
            f"SL: ${new_position.stop_price:,.2f} | "
            f"TP: ${new_position.take_profit:,.2f} | "
            f"Size: {new_position.size:.6f} BTC | "
            f"Riesgo: ${risk_usd:.2f}"
        )

    # ── Ejecucion real (LIVE mode) ────────────────────────────
    def _execute_open_order(self, position: Position) -> bool:
        """Ejecuta orden de apertura en el exchange real."""
        try:
            import ccxt
            exchange = ccxt.binance({
                "apiKey": EXCHANGE.api_key,
                "secret": EXCHANGE.api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            })
            if EXCHANGE.sandbox:
                exchange.set_sandbox_mode(True)

            side_str = "buy" if position.side == 1 else "sell"
            order    = exchange.create_market_order(
                symbol = EXCHANGE.symbol,
                side   = side_str,
                amount = position.size,
            )
            logger.info(f"Orden ejecutada: {order.get('id')} | {side_str.upper()} {position.size} BTC")
            return True
        except Exception as e:
            notify_error(f"Error ejecutando orden: {e}", "LiveEngine.execute_open")
            logger.error(f"Error ejecutando orden: {e}")
            return False

    def _execute_close_order(self, exit_price: float) -> bool:
        """Ejecuta orden de cierre en el exchange real."""
        if self.position is None:
            return False
        try:
            import ccxt
            exchange = ccxt.binance({
                "apiKey": EXCHANGE.api_key,
                "secret": EXCHANGE.api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            })
            if EXCHANGE.sandbox:
                exchange.set_sandbox_mode(True)

            # Cierre es la operacion inversa
            side_str = "sell" if self.position.side == 1 else "buy"
            order    = exchange.create_market_order(
                symbol   = EXCHANGE.symbol,
                side     = side_str,
                amount   = self.position.size,
                params   = {"reduceOnly": True},
            )
            logger.info(f"Cierre ejecutado: {order.get('id')}")
            return True
        except Exception as e:
            notify_error(f"Error cerrando posicion: {e}", "LiveEngine.execute_close")
            logger.error(f"Error cerrando posicion: {e}")
            return False

    # ── Resumen diario ────────────────────────────────────────
    def _handle_new_day(self, ts):
        """Procesa el cambio de dia: envia resumen del dia anterior."""
        stats = self.rm.get_daily_stats()

        if stats["trades_total"] == 0:
            return

        # Acumular PnL mensual
        month_key = str(ts)[:7]
        if month_key != self.current_month:
            self.current_month   = month_key
            self.monthly_pnl_usd = 0.0
        self.monthly_pnl_usd += stats["pnl_usd"]

        monthly_pct = (self.monthly_pnl_usd / self.initial_capital) * 100

        notify_daily_summary(
            date_str       = str(self.rm.current_day),
            trades_total   = stats["trades_total"],
            trades_win     = stats["trades_win"],
            trades_loss    = stats["trades_loss"],
            pnl_usd        = stats["pnl_usd"],
            pnl_pct        = stats["pnl_pct"],
            capital_start  = self.rm.daily_start_equity,
            capital_end    = self.rm.equity,
            best_trade     = stats["best_trade"],
            worst_trade    = stats["worst_trade"],
            monthly_pnl_pct= monthly_pct,
            dd_max_day     = stats["dd_max_day"],
            session_stats  = {},
        )

        logger.info(
            f"Resumen dia anterior: "
            f"Trades={stats['trades_total']} | "
            f"WR={stats['trades_win']}/{stats['trades_total']} | "
            f"PnL=${stats['pnl_usd']:.2f}"
        )

    # ── Helpers ───────────────────────────────────────────────
    def _calc_regime_score(self, row: pd.Series) -> int:
        """Calcula el score de condiciones para el log."""
        score = 0
        regime = row.get("regime", "RANGE")
        if regime == "TREND_BULL":
            score += 4
        elif regime == "TREND_BEAR":
            score += 3
        elif regime == "HIGH_VOL":
            score += 2
        else:
            score += 1
        if row.get("in_session", False):
            score += 3
        adx_val = row.get("adx", 0)
        if adx_val > 25:
            score += 2
        elif adx_val > 20:
            score += 1
        return min(score, 10)

    def _log_status(self, last_row: pd.Series, ts):
        """Logging periodico del estado del sistema."""
        pos_str = "NINGUNA"
        if self.position:
            side_str = "LONG" if self.position.side == 1 else "SHORT"
            fl_pnl   = (last_row["close"] - self.position.entry_price) * self.position.size * self.position.side
            pos_str  = f"{side_str} @ ${self.position.entry_price:,.2f} | PnL flotante: ${fl_pnl:.4f}"

        logger.info(
            f"[{ts}] "
            f"BTC/USDT=${last_row['close']:,.2f} | "
            f"Regimen={last_row.get('regime','?')} | "
            f"ADX={last_row.get('adx',0):.1f} | "
            f"Session={'SI' if last_row.get('in_session') else 'NO'} | "
            f"Equity=${self.rm.equity:.2f} | "
            f"Pos={pos_str}"
        )
