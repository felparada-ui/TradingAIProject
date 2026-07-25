"""
Ejecutor de Órdenes MT5 — Conexión y ejecución asíncrona.

Responsabilidades:
  - Conectar con MetaTrader 5
  - Enviar órdenes Market, Limit y Stop
  - Monitorear slippage y spread
  - Cancelar órdenes pendientes
  - Monitorear salud de la conexión
  - Reportar estado de posiciones abiertas

NOTA: MetaTrader5 solo funciona en Windows. En Linux/Docker, las
funciones de MT5 se simulan para permitir desarrollo y backtesting.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Flag para detectar si MT5 está disponible
_MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except (ImportError, OSError):
    logger.warning("MetaTrader5 no disponible. Usando simulador de MT5.")


class MT5Executor:
    """
    Ejecutor de órdenes para MetaTrader 5 con soporte asíncrono.
    En entornos sin MT5 (Linux), opera en modo simulado para backtesting.
    """

    def __init__(self, config: dict):
        self.config = config
        mt5_cfg = config.get("mt5", {})
        general_cfg = config.get("general", {})

        self.server = mt5_cfg.get("server", "ICMarketsSC-Demo")
        self.login = mt5_cfg.get("login", 0)
        self.password = mt5_cfg.get("password", "")
        self.timeout_ms = mt5_cfg.get("timeout_ms", 5000)
        self.max_slippage = mt5_cfg.get("max_slippage", 10)
        self.max_spread = mt5_cfg.get("max_spread", 20)
        self.magic_number = mt5_cfg.get("magic_number", 202401)
        self.mode = general_cfg.get("modo_operacion", "demo")
        self._reconnect_attempts = 0
        self._max_reconnects = 3

        self._connected = False
        self._last_tick: dict = {}
        self._open_positions_cache: list[dict] = []

        # Mapeo de símbolos (formato amigable → formato MT5)
        self._symbol_map = {
            # Forex
            "EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "USD/JPY": "USDJPY",
            "AUD/USD": "AUDUSD", "USD/CAD": "USDCAD", "NZD/USD": "NZDUSD",
            # Crypto
            "BTC/USD": "BTCUSD", "ETH/USD": "ETHUSD", "SOL/USD": "SOLUSD",
            "BCH/USD": "BCHUSD", "LTC/USD": "LTCUSD", "XRP/USD": "XRPUSD",
            # Indices
            "SPY": "SP500", "QQQ": "NAS100", "IWM": "US2000", "DIA": "US30",
            # Commodities
            "XAU/USD": "XAUUSD", "XAG/USD": "XAGUSD",
        }

    # ------------------------------------------------------------------
    # API pública (herramientas para CrewAI)
    # ------------------------------------------------------------------

    def connect_mt5(self) -> dict:
        """Conecta con MetaTrader 5 con autoreconexión."""
        if not _MT5_AVAILABLE:
            logger.info("MT5 no disponible — modo simulación activo")
            self._connected = True
            simulated_balance = self.config.get("general", {}).get("capital_inicial", 500.0)
            return {
                "connected": True,
                "mode": "simulated",
                "server": self.server,
                "account": "SIMULATED",
                "balance": simulated_balance,
                "equity": simulated_balance,
            }

        logger.info(f"Conectando a MT5 — Servidor: {self.server}, Cuenta: {self.login}")

        # Inicializar terminal si no está inicializado
        if not mt5.initialize():
            error = mt5.last_error()
            logger.error(f"Error inicializando MT5: {error}")
            # Intentar con path por defecto
            if not mt5.initialize(path=self._detect_terminal_path()):
                error = mt5.last_error()
                self._connected = False
                return {"connected": False, "error": str(error)}

        # Login
        if self.login and self.password:
            authorized = mt5.login(
                self.login,
                password=self.password,
                server=self.server,
                timeout=self.timeout_ms,
            )
            if not authorized:
                error = mt5.last_error()
                logger.error(f"Error de autenticación MT5: {error}")
                self._connected = False
                self._reconnect_attempts += 1
                return {"connected": False, "error": str(error)}

        account_info = mt5.account_info()
        if account_info is None:
            self._connected = False
            return {"connected": False, "error": "No se pudo obtener info de cuenta"}

        self._connected = True
        self._reconnect_attempts = 0
        logger.info(f"[MT5] Conectado a {account_info.server} | Balance: ${account_info.balance:.2f}")

        return {
            "connected": True,
            "mode": self.mode,
            "server": account_info.server,
            "account": account_info.login,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "margin_free": account_info.margin_free,
            "leverage": account_info.leverage,
            "currency": account_info.currency,
        }

    def place_market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "AutoTrade",
    ) -> dict:
        """
        Envía una orden Market. Verifica spread y slippage antes de ejecutar.
        """
        error = self._ensure_connected()
        if error:
            return error

        # Normalizar símbolo para MT5
        mt5_symbol = self._normalize_symbol(symbol)

        # Verificar spread
        spread_check = self._check_spread(mt5_symbol)
        if not spread_check["ok"]:
            return {"error": f"Spread demasiado alto: {spread_check['spread']}", "order_sent": False}

        if not _MT5_AVAILABLE:
            return self._simulate_order(symbol, side, volume, stop_loss, take_profit, "ORDER_TYPE_BUY" if side.upper() == "BUY" else "ORDER_TYPE_SELL")

        order_type = mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL

        # Asegurar que el símbolo está activo y obtener precio actual
        mt5.symbol_select(mt5_symbol, True)
        tick = mt5.symbol_info_tick(mt5_symbol)
        if tick is None:
            return {"error": f"No se pudo obtener precio para {mt5_symbol}", "order_sent": False}

        current_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        if current_price is None or current_price <= 0:
            return {"error": f"Precio inválido para {mt5_symbol}: {current_price}", "order_sent": False}

        # El volumen ya viene en lotes MT5 (0.01, 0.10, 1.0, etc.)
        mt5_volume = max(0.01, round(volume, 2))

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": mt5_volume,
            "type": order_type,
            "price": current_price,
            "sl": stop_loss if stop_loss > 0 else 0.0,
            "tp": take_profit if take_profit > 0 else 0.0,
            "deviation": self.max_slippage,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Orden fallida: {result.comment} (código {result.retcode})")
            return {
                "order_sent": False,
                "error": f"MT5 error: {result.comment}",
                "retcode": result.retcode,
            }

        return {
            "order_sent": True,
            "order_id": result.order,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": result.price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "comment": comment,
        }

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ) -> dict:
        """Coloca una orden Limit (pendiente)."""
        error = self._ensure_connected()
        if error:
            return error

        mt5_symbol = self._normalize_symbol(symbol)

        if not _MT5_AVAILABLE:
            return self._simulate_order(symbol, side, volume, stop_loss, take_profit, "ORDER_TYPE_BUY_LIMIT" if side.upper() == "BUY" else "ORDER_TYPE_SELL_LIMIT", price)

        order_type = mt5.ORDER_TYPE_BUY_LIMIT if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": mt5_symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": self.max_slippage,
            "magic": self.magic_number,
            "comment": "AutoTrade Limit",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        if _MT5_AVAILABLE:
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"order_sent": False, "error": f"MT5 error: {result.comment}"}
            return {"order_sent": True, "order_id": result.order, "price": price}

        return self._simulate_order(symbol, side, volume, stop_loss, take_profit, str(order_type), price)

    def place_stop_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ) -> dict:
        """Coloca una orden Stop (pendiente)."""
        error = self._ensure_connected()
        if error:
            return error

        mt5_symbol = self._normalize_symbol(symbol)

        if not _MT5_AVAILABLE:
            return self._simulate_order(symbol, side, volume, stop_loss, take_profit, "ORDER_TYPE_BUY_STOP" if side.upper() == "BUY" else "ORDER_TYPE_SELL_STOP", price)

        order_type = mt5.ORDER_TYPE_BUY_STOP if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL_STOP

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": mt5_symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": self.max_slippage,
            "magic": self.magic_number,
            "comment": "AutoTrade Stop",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        if _MT5_AVAILABLE:
            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"order_sent": False, "error": f"MT5 error: {result.comment}"}
            return {"order_sent": True, "order_id": result.order, "price": price}

        return self._simulate_order(symbol, side, volume, stop_loss, take_profit, str(order_type), price)

    def monitor_open_positions(self) -> list[dict]:
        """Obtiene todas las posiciones abiertas."""
        if not _MT5_AVAILABLE:
            return self._open_positions_cache

        if not self._connected:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "side": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": pos.volume,
                "entry_price": pos.price_open,
                "current_price": pos.price_current,
                "stop_loss": pos.sl,
                "take_profit": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "comment": pos.comment,
                "magic": pos.magic,
            })
        return result

    def cancel_pending_orders(self, symbol: str = "") -> dict:
        """Cancela todas las órdenes pendientes, opcionalmente filtradas por símbolo."""
        if not _MT5_AVAILABLE:
            count = len([o for o in self._open_positions_cache if not symbol or o.get("symbol") == symbol])
            self._open_positions_cache.clear()
            return {"cancelled": count, "mode": "simulated"}

        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if orders is None:
            return {"cancelled": 0}

        cancelled = 0
        for order in orders:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order.ticket,
            }
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                cancelled += 1

        return {"cancelled": cancelled}

    def check_mt5_health(self) -> dict:
        """Verifica la salud de la conexión MT5 y las condiciones del terminal."""
        if not _MT5_AVAILABLE:
            return {
                "connected": self._connected,
                "mode": "simulated",
                "status": "OK" if self._connected else "DISCONNECTED",
                "latency_ms": 0,
            }

        if not self._connected:
            return {"connected": False, "status": "DISCONNECTED"}

        start = time.time()
        info = mt5.terminal_info()
        latency = int((time.time() - start) * 1000)

        if info is None:
            return {"connected": False, "status": "TERMINAL_INFO_ERROR"}

        return {
            "connected": True,
            "status": "OK",
            "latency_ms": latency,
            "trade_allowed": getattr(info, "trade_allowed", True),
            "margin_mode": getattr(info, "margin_so_mode", 0),
            "path": getattr(info, "path", ""),
        }

    def disconnect(self):
        """Desconecta de MT5."""
        if _MT5_AVAILABLE and self._connected:
            try:
                mt5.shutdown()
            except Exception:
                pass
        self._connected = False
        self._reconnect_attempts = 0
        logger.info("Desconectado de MT5")

    @staticmethod
    def _detect_terminal_path() -> str:
        """Detecta la ruta del terminal MT5 en el sistema."""
        import platform
        if platform.system() == "Windows":
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\MetaQuotes\MetaTrader 5")
                path, _ = winreg.QueryValueEx(key, "Path")
                return path
            except Exception:
                return "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
        return ""
    def _normalize_symbol(self, symbol: str) -> str:
        """Convierte símbolo formato amigable a formato MT5."""
        return self._symbol_map.get(symbol.upper(), symbol.upper().replace("/", ""))
    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> Optional[dict]:
        """Verifica la conexión, reconecta si es necesario (hasta 3 intentos)."""
        if self._connected:
            # Verificar que la conexión sigue activa (heartbeat)
            if _MT5_AVAILABLE:
                try:
                    info = mt5.account_info()
                    if info is None:
                        self._connected = False
                        logger.warning("Heartbeat MT5 falló — reconectando...")
                    else:
                        return None
                except Exception:
                    self._connected = False
            else:
                return None

        if self._reconnect_attempts >= self._max_reconnects:
            logger.error(f"Máximos reintentos ({self._max_reconnects}) alcanzados — abortando")
            return {"error": f"No conectado tras {self._max_reconnects} intentos", "order_sent": False}

        self._reconnect_attempts += 1
        logger.info(f"Intento de reconexión #{self._reconnect_attempts}...")
        result = self.connect_mt5()
        if not result.get("connected"):
            return {"error": f"Reconexión #{self._reconnect_attempts} fallida", "order_sent": False}
        return None

    def _check_spread(self, symbol: str) -> dict:
        """Verifica que el spread esté dentro del límite según tipo de activo."""
        if not _MT5_AVAILABLE:
            return {"ok": True, "spread": 5, "symbol": symbol}

        mt5_symbol = self._normalize_symbol(symbol)

        # Spread máximo según tipo de activo
        crypto_symbols = ["BTCUSD", "ETHUSD", "SOLUSD", "BCHUSD", "LTCUSD", "XRPUSD"]
        if mt5_symbol in crypto_symbols:
            max_allowed = 2000  # Crypto tiene spreads altos
        elif mt5_symbol in ["XAUUSD", "XAGUSD"]:
            max_allowed = 100   # Commodities
        else:
            max_allowed = self.max_spread  # Forex: 20

        # Verificar que el símbolo existe
        info = mt5.symbol_info(mt5_symbol)
        if info is None:
            logger.warning(f"Simbolo {mt5_symbol} no disponible en MT5")
            return {"ok": False, "spread": 999, "error": f"Simbolo {mt5_symbol} no disponible"}

        if not info.visible:
            mt5.symbol_select(mt5_symbol, True)

        tick = mt5.symbol_info_tick(mt5_symbol)
        if tick is None:
            logger.warning(f"No se pudo obtener tick para {mt5_symbol}")
            return {"ok": False, "spread": 999, "error": f"Sin datos de mercado para {mt5_symbol}"}

        spread = (tick.ask - tick.bid) / info.point if info.point > 0 else (tick.ask - tick.bid) * 10000
        self._last_tick = {"ask": tick.ask, "bid": tick.bid, "spread": spread, "symbol": mt5_symbol}

        if spread > max_allowed:
            logger.info(f"Spread {spread:.0f} para {mt5_symbol} > maximo {max_allowed}")
            return {"ok": False, "spread": round(spread, 1), "symbol": mt5_symbol}

        return {"ok": True, "spread": round(spread, 1), "symbol": mt5_symbol}
        self._last_tick = {"ask": tick.ask, "bid": tick.bid, "spread": spread}

        if spread > self.max_spread:
            return {"ok": False, "spread": round(spread, 1), "symbol": symbol}

        return {"ok": True, "spread": round(spread, 1), "symbol": symbol}

    def _simulate_order(self, symbol, side, volume, sl, tp, order_type, price=None):
        """Simula una orden para backtesting o entornos sin MT5."""
        tick = self._last_tick or {"ask": 50000.0, "bid": 49990.0}
        exec_price = price or (tick["ask"] if "BUY" in order_type else tick["bid"])
        order_id = int(time.time() * 1000) % 1000000

        position = {
            "ticket": order_id,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "entry_price": round(exec_price, 2),
            "current_price": round(exec_price, 2),
            "stop_loss": sl,
            "take_profit": tp,
            "profit": 0.0,
            "comment": "SIMULATED",
        }
        self._open_positions_cache.append(position)

        return {
            "order_sent": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": round(exec_price, 2),
            "stop_loss": sl,
            "take_profit": tp,
            "mode": "simulated",
        }
