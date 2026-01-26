"""
Data Pipeline Agent

Handles data fetching and caching.
Clearance: Pipeline
"""

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType
from data.providers.yahoo import YahooFinanceProvider
from data.storage.parquet import ParquetStorage

logger = logging.getLogger(__name__)


class DataPipelineAgent(Agent):
    """
    Data Pipeline Agent fetches and caches data.
    
    Responsibilities:
    - Fetch data from providers (Yahoo, StockTwits, etc.)
    - Cache to Parquet storage
    - Emit data.available when ready
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
        cache_path: Path | None = None,
    ) -> None:
        super().__init__(event_bus, config)
        
        if cache_path is None:
            from config import STORAGE_PATH
            cache_path = STORAGE_PATH
        self.cache_path = Path(cache_path)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize providers
        self.yahoo = YahooFinanceProvider()
        self.storage = ParquetStorage(self.cache_path)
    
    @property
    def name(self) -> str:
        return "DataPipeline"
    
    @property
    def clearance(self) -> Clearance:
        return Clearance.PIPELINE
    
    def _subscribe_events(self) -> None:
        """Subscribe to approved data requests."""
        self.event_bus.subscribe(EventType.PM_APPROVED, self._on_request_approved)
    
    def _on_request_approved(self, event: Event) -> None:
        """Fetch data for an approved request."""
        request = event.payload.get("original_request", {})
        source = event.payload.get("source", "yahoo_finance")
        
        self.log(f"Fetching data: {request} from {source}")
        
        try:
            result = self._fetch_data(request, source)
            
            if result["success"]:
                self.emit(EventType.DATA_AVAILABLE, {
                    "type": request.get("type"),
                    "symbols": request.get("symbols", []),
                    "rows": result.get("rows", 0),
                })
            else:
                self.emit(EventType.SYSTEM_ERROR, {
                    "error": result.get("error", "Unknown fetch error"),
                    "request": request,
                })
        except Exception as e:
            self.log(f"Fetch error: {e}", level="error")
            self.emit(EventType.SYSTEM_ERROR, {
                "error": str(e),
                "request": request,
            })
    
    def _fetch_data(self, request: dict, source: str) -> dict:
        """Fetch and cache data."""
        data_type = request.get("type", "prices")
        symbols = request.get("symbols", [])
        years = request.get("years", 5)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)
        
        total_rows = 0
        failed = []
        
        for symbol in symbols:
            try:
                if data_type in ["prices", "ohlcv"]:
                    df = self.yahoo.get_historical_prices(symbol, start_date, end_date)
                    if df is not None and len(df) > 0:
                        self.storage.save_prices(symbol, df)
                        total_rows += len(df)
                elif data_type == "fundamentals":
                    data = self.yahoo.get_fundamentals(symbol)
                    if data:
                        # Save as single-row parquet
                        df = pd.DataFrame([data])
                        self.storage.save_fundamentals(symbol, df)
                        total_rows += 1
            except Exception as e:
                self.log(f"Failed to fetch {symbol}: {e}", level="warning")
                failed.append(symbol)
        
        return {
            "success": len(failed) < len(symbols),
            "rows": total_rows,
            "failed": failed,
        }
    
    def fetch_universe(
        self,
        symbols: list[str],
        years: int = 5,
    ) -> dict:
        """
        Fetch price data for a universe of symbols.
        
        Returns status dict with success rate.
        """
        self.log(f"Fetching universe: {len(symbols)} symbols, {years} years")
        
        result = self._fetch_data(
            request={"type": "prices", "symbols": symbols, "years": years},
            source="yahoo_finance",
        )
        
        return result
    
    def check_cache_status(self, symbols: list[str]) -> dict:
        """Check which symbols are already cached."""
        cached = []
        missing = []
        
        for symbol in symbols:
            if self.storage.has_prices(symbol):
                cached.append(symbol)
            else:
                missing.append(symbol)
        
        return {
            "cached": cached,
            "missing": missing,
            "cache_rate": len(cached) / len(symbols) if symbols else 0,
        }
