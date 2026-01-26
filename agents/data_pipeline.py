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
from data.providers.house_clerk import HouseClerkProvider
from data.providers.yahoo import YahooFinanceProvider
from data.storage.parquet import ParquetStorage
from data.storage.politician_trades import PoliticianTradeStorage

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
        self.house_clerk = HouseClerkProvider()  # Free, no API key needed
        self.storage = ParquetStorage(self.cache_path)
        self.politician_storage = PoliticianTradeStorage(self.cache_path)
    
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
            prices = self.storage.load_prices(symbol)
            if prices is not None and not prices.empty:
                cached.append(symbol)
            else:
                missing.append(symbol)
        
        return {
            "cached": cached,
            "missing": missing,
            "cache_rate": len(cached) / len(symbols) if symbols else 0,
        }
    
    def fetch_politician_trades(
        self,
        politician_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        """Fetch politician trades from free House Stock Watcher data.
        
        Args:
            politician_name: Optional specific politician name, or None for all in watchlist
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Status dict with success, rows, and failed politicians
        """
        
        import yaml
        from config import POLITICIAN_WATCHLIST_PATH
        
        # Load politician watchlist
        if not POLITICIAN_WATCHLIST_PATH.exists():
            return {
                "success": False,
                "error": f"Politician watchlist not found: {POLITICIAN_WATCHLIST_PATH}",
                "rows": 0,
                "failed": [],
            }
        
        with open(POLITICIAN_WATCHLIST_PATH) as f:
            watchlist = yaml.safe_load(f)
        
        politicians = watchlist.get("politicians", [])
        
        # Filter to specific politician if requested
        if politician_name:
            politicians = [p for p in politicians if p.get("name") == politician_name]
        
        if not politicians:
            return {
                "success": False,
                "error": "No politicians found matching criteria",
                "rows": 0,
                "failed": [],
            }
        
        total_rows = 0
        failed = []
        
        for politician in politicians:
            pol_name = politician.get("name", "Unknown")
            
            try:
                self.log(f"Fetching trades for {pol_name} from House Stock Watcher")
                
                # Fetch congressional trades (free, no API key needed)
                trades_df = self.house_clerk.get_congressional_trades(
                    politician_name=pol_name,
                    start_date=start_date,
                    end_date=end_date,
                )
                
                if not trades_df.empty:
                    # Add politician name if not in dataframe
                    if "politician_name" not in trades_df.columns:
                        trades_df["politician_name"] = pol_name
                    
                    # Save to storage
                    self.politician_storage.save_trades(pol_name, trades_df)
                    total_rows += len(trades_df)
                    self.log(f"Saved {len(trades_df)} trades for {pol_name}")
                else:
                    self.log(f"No trades found for {pol_name}", level="warning")
                    
            except Exception as e:
                self.log(f"Failed to fetch trades for {pol_name}: {e}", level="error")
                failed.append(pol_name)
        
        return {
            "success": len(failed) < len(politicians),
            "rows": total_rows,
            "failed": failed,
        }
