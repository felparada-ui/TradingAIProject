"""
Conector universal de trading — MT5 (Windows) o Binance (Linux/macOS).
Auto-detecta la plataforma disponible y elige el broker adecuado.

Modos:
  - MT5_DEMO : Cuenta demo MetaTrader 5 (Windows)
  - MT5_REAL : Cuenta real MetaTrader 5 (Windows)
  - BINANCE_PAPER : Binance simulado (Linux/macOS) ← funciona ahora
  - BINANCE_LIVE : Binance real
"""

import os
import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class MT5Connector:
    """
    Conector para MetaTrader 5 (solo Windows).
    Requiere tener MT5 instalado y una cuenta demo/real configurada.
    """

    def __init__(self, login: int = 0, password: str = "", server: str = "", demo: bool = True):
        self.login = login or int(os.getenv("MT5_LOGIN", "0"))
        self.password = password or os.getenv("MT5_PASSWORD", "")
        self.server = server or os.getenv("MT5_SERVER", "")
        self.demo = demo
        self.connected = False
        self.mt5 = None
        self.account_info = None

    def connect(self) -> bool:
        """Conecta a MetaTrader 5."""
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5

            if not mt5.initialize():
                logger.error(f"MT5 initialize failed: {mt5.last_error()}")
                return False

            if self.login > 0 and self.password:
                authorized = mt5.login(self.login, password=self.password, server=self.server)
                if not authorized:
                    logger.error(f"MT5 login failed: {mt5.last_error()}")
                    return False

            self.account_info = mt5.account_info()
            if self.account_info:
                account_type = "DEMO" if self.account_info.trade_mode == 0 else "REAL"
                logger.info(f"✅ MT5 conectado: {self.account_info.name} | "
                           f"Balance: ${self.account_info.balance:.2f} | {account_type}")
                self.connected = True
                
                # Notificar por Telegram
                try:
                    from notifications import _send_message
                    _send_message(
                        f"<b>✅ MT5 CONECTADO — {account_type}</b>\n\n"
                        f"<b>Cuenta:</b> {self.account_info.name}\n"
                        f"<b>Balance:</b> <code>${self.account_info.balance:.2f}</code>\n"
                        f"<b>Apalancamiento:</b> 1:{self.account_info.leverage}\n"
                        f"<b>Servidor:</b> {self.account_info.server}\n"
                        f"<b>Plataforma:</b> MetaTrader 5\n\n"
                        f"<i>Listo para operar</i>"
                    )
                except:
                    pass
                
                return True

            return False

        except ImportError:
            logger.error("MetaTrader5 no instalado (solo Windows). Usa: pip install MetaTrader5")
            return False
        except Exception as e:
            logger.error(f"Error conectando MT5: {e}")
            return False

    def get_balance(self) -> float:
        """Obtiene el balance de la cuenta."""
        if not self.connected or not self.mt5:
            return 0.0
        info = self.mt5.account_info()
        return info.balance if info else 0.0

    def get_positions(self) -> list:
        """Obtiene posiciones abiertas."""
        if not self.connected or not self.mt5:
            return []
        positions = self.mt5.positions_get()
        if not positions:
            return []
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
            }
            for p in positions
        ]

    def place_order(self, symbol: str, order_type: str, volume: float,
                    price: float = 0.0, sl: float = 0.0, tp: float = 0.0,
                    comment: str = "TradingBot") -> dict:
        """
        Envía una orden a MT5.
        
        Args:
            symbol: Par (ej: 'BCHUSD')
            order_type: 'buy' o 'sell'
            volume: Tamaño en lotes
            price: Precio (0 = market)
            sl: Stop loss
            tp: Take profit
            comment: Comentario de la orden
        
        Returns:
            Dict con resultado
        """
        if not self.connected or not self.mt5:
            return {"error": "No conectado a MT5"}

        mt5 = self.mt5
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            return {"error": f"Símbolo {symbol} no encontrado en MT5"}

        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return {"error": f"No se pudo activar {symbol}"}

        order_type_mt5 = mt5.ORDER_TYPE_BUY if order_type.lower() == "buy" else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type_mt5,
            "price": price if price > 0 else (mt5.symbol_info_tick(symbol).ask if order_type.lower() == "buy" else mt5.symbol_info_tick(symbol).bid),
            "sl": sl if sl > 0 else 0.0,
            "tp": tp if tp > 0 else 0.0,
            "deviation": 10,
            "magic": 123456,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✅ Orden ejecutada: {order_type} {volume} {symbol} @ {request['price']}")
            return {
                "success": True,
                "ticket": result.order,
                "price": request["price"],
                "volume": volume,
                "comment": comment,
            }
        else:
            error_code = result.retcode if result else "UNKNOWN"
            logger.error(f"❌ Orden fallida: {error_code}")
            return {"error": f"Orden fallida: {error_code}"}

    def close_position(self, ticket: int) -> dict:
        """Cierra una posición por ticket."""
        if not self.connected or not self.mt5:
            return {"error": "No conectado"}

        mt5 = self.mt5
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return {"error": f"Posición {ticket} no encontrada"}

        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "Close by Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return {"success": True, "ticket": ticket, "price": price}
        return {"error": f"Error cerrando {ticket}: {result.retcode if result else 'UNKNOWN'}"}

    def disconnect(self):
        """Desconecta de MT5."""
        if self.mt5:
            try:
                self.mt5.shutdown()
            except:
                pass
        self.connected = False


# ── DETECCION DE PLATAFORMA DISPONIBLE ───────────────────────

def get_available_broker():
    """
    Detecta qué broker está disponible en el sistema actual.
    Retorna: 'mt5' (Windows con MT5), 'binance' (Linux/macOS)
    """
    # Intentar MT5 primero
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            mt5.shutdown()
            return "mt5"
    except:
        pass
    # Fallback a Binance
    return "binance"


def get_symbol_for_broker(symbol: str, broker: str) -> str:
    """Convierte símbolo estándar al formato del broker."""
    mapping = {
        "mt5": {
            "BCH/USDT": "BCHUSD",
            "BTC/USDT": "BTCUSD",
            "ETH/USDT": "ETHUSD",
            "SOL/USDT": "SOLUSD",
        },
        "binance": {
            "BCH/USDT": "BCH/USDT",
            "BTC/USDT": "BTC/USDT",
            "ETH/USDT": "ETH/USDT",
            "SOL/USDT": "SOL/USDT",
        },
    }
    return mapping.get(broker, {}).get(symbol, symbol.replace("/", ""))
