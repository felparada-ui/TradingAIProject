"""
Tracker de Sentimiento y Fundamentales

Procesa:
  - Calendario económico (eventos programados)
  - Sentimiento de noticias
  - Sentimiento de redes sociales/foros

Genera un factor de ponderación (±25%) que modifica la confianza
de las señales técnicas.
"""

import json
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SentimentTracker:
    """
    Analiza el sentimiento del mercado a partir de múltiples fuentes.
    NOTA: Las conexiones reales a APIs (ForexFactory, Twitter, Reddit)
    requieren API keys. Esta implementación usa datos simulados que
    deben ser reemplazados con integraciones reales en producción.
    """

    def __init__(self, config: dict):
        sent_cfg = config.get("sentimiento", {})
        self.sources = sent_cfg.get("fuentes", ["ForexFactory", "Twitter", "Reddit"])
        self.window_hours = sent_cfg.get("ventana_horas", 4)
        self.min_impact = sent_cfg.get("impacto_minimo", 2)
        self.attention_window = sent_cfg.get("ventana_atencion", 24)

    # ------------------------------------------------------------------
    # API pública (herramientas para CrewAI)
    # ------------------------------------------------------------------

    def fetch_economic_calendar(self, symbols: list[str]) -> dict:
        """
        Obtiene eventos económicos relevantes para los símbolos dados.
        Retorna eventos con impacto, descripción y sentimiento esperado.

        TODO: Integrar con API real (ForexFactory, Investing.com, etc.)
        """
        events = []
        now = datetime.now()

        # Simulación de eventos — reemplazar con API real
        mock_events = [
            {
                "symbol": "EUR/USD",
                "event": "Decisión de tipos BCE",
                "datetime": now + timedelta(hours=2),
                "impact": 3,
                "expected": "halcón (hawkish)",
                "sentiment": "bearish",
            },
            {
                "symbol": "BTC/USD",
                "event": "Decisión FOMC",
                "datetime": now + timedelta(hours=5),
                "impact": 3,
                "expected": "pausa en subidas",
                "sentiment": "bullish",
            },
            {
                "symbol": "SPY",
                "event": "IPC Estados Unidos",
                "datetime": now + timedelta(hours=8),
                "impact": 3,
                "expected": "0.2% mensual",
                "sentiment": "neutral",
            },
        ]

        for event in mock_events:
            if any(s.upper() in event["symbol"] for s in symbols):
                if event["impact"] >= self.min_impact:
                    events.append(event)

        return {
            "events": events,
            "total_events": len(events),
            "high_impact": sum(1 for e in events if e["impact"] == 3),
        }

    def analyze_news_sentiment(self, symbol: str, hours_back: int = 4) -> dict:
        """
        Analiza titulares de noticias recientes para un símbolo.

        TODO: Integrar con API de noticias financieras (Alpha Vantage, NewsAPI, etc.)
        """
        # Simulación — reemplazar con NLP real
        mock_headlines = {
            "EUR/USD": [
                ("BCE mantiene tasas, euro estable", 0.1),
                ("Preocupación por recesión en Alemania", -0.4),
            ],
            "BTC/USD": [
                ("Bitcoin supera resistencia de 30K", 0.6),
                ("ETF de Bitcoin atrae inflows récord", 0.7),
            ],
            "SPY": [
                ("Wall Street opera mixto antes de datos de inflación", 0.0),
                ("Sectores tecnológicos lideran ganancias", 0.3),
            ],
        }

        headlines = mock_headlines.get(symbol.upper(), [("Sin noticias recientes", 0.0)])
        scores = [s for _, s in headlines]
        avg_sentiment = sum(scores) / len(scores) if scores else 0.0

        # Clasificación
        if avg_sentiment > 0.2:
            classification = "bullish"
        elif avg_sentiment < -0.2:
            classification = "bearish"
        else:
            classification = "neutral"

        return {
            "symbol": symbol,
            "headlines": [{"title": h, "score": s} for h, s in headlines],
            "avg_sentiment": round(avg_sentiment, 3),
            "classification": classification,
            "coverage": len(headlines),
        }

    def get_social_sentiment(self, symbol: str) -> dict:
        """
        Obtiene sentimiento de redes sociales/foros.

        TODO: Integrar con APIs de Reddit, Twitter, StockTwits, etc.
        """
        # Simulación — reemplazar con APIs reales
        mock_social = {
            "EUR/USD": {"bullish": 42, "bearish": 38, "neutral": 20, "volume": 1200},
            "BTC/USD": {"bullish": 65, "bearish": 20, "neutral": 15, "volume": 8500},
            "SPY": {"bullish": 48, "bearish": 30, "neutral": 22, "volume": 3400},
        }

        data = mock_social.get(symbol.upper(), {"bullish": 33, "bearish": 33, "neutral": 34, "volume": 100})
        total = data["bullish"] + data["bearish"] + data["neutral"]
        net_sentiment = (data["bullish"] - data["bearish"]) / total if total > 0 else 0

        return {
            "symbol": symbol,
            "bullish_pct": round(data["bullish"] / total * 100, 1),
            "bearish_pct": round(data["bearish"] / total * 100, 1),
            "neutral_pct": round(data["neutral"] / total * 100, 1),
            "net_sentiment": round(net_sentiment, 3),
            "volume": data["volume"],
        }

    def compute_sentiment_factor(self, symbol: str, symbols: list[str]) -> dict:
        """
        Combina todas las fuentes de sentimiento en un factor único
        que modifica la confianza de la señal técnica en ±25%.
        """
        news = self.analyze_news_sentiment(symbol)
        social = self.get_social_sentiment(symbol)
        calendar = self.fetch_economic_calendar(symbols)

        # Pesos ponderados de cada fuente
        w_news = 0.40
        w_social = 0.25
        w_calendar = 0.35

        # Factor de noticias ([-1, 1])
        news_factor = news["avg_sentiment"]

        # Factor de redes ([bearish=-1, neutral=0, bullish=1])
        social_factor = social["net_sentiment"]

        # Factor de calendario
        calendar_factor = 0.0
        if calendar["events"]:
            for event in calendar["events"]:
                if event["symbol"] == symbol.upper():
                    if event["sentiment"] == "bullish":
                        calendar_factor = 0.5
                    elif event["sentiment"] == "bearish":
                        calendar_factor = -0.5
                    break

        # Factor compuesto (rango: -1 a 1)
        composite = (w_news * news_factor + w_social * social_factor + w_calendar * calendar_factor)

        # Escalar a ±25%
        adjustment = composite * 0.25 * 100  # en puntos porcentuales

        # Clasificación
        if composite > 0.1:
            classification = "bullish"
        elif composite < -0.1:
            classification = "bearish"
        else:
            classification = "neutral"

        return {
            "symbol": symbol,
            "composite_factor": round(composite, 3),
            "adjustment_pct": round(adjustment, 1),
            "classification": classification,
            "details": {
                "news": {"factor": news_factor, "coverage": news["coverage"]},
                "social": {"factor": social_factor, "volume": social["volume"]},
                "calendar": {"factor": calendar_factor, "events": calendar["total_events"]},
            },
        }
