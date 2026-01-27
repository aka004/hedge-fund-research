"""Universe management for stock selection."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# S&P 500 symbols as of January 2026 (503 symbols - some companies have dual share classes)
# fmt: off
SP500_SYMBOLS = [
    # A
    "A", "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACN", "ADBE", "ADI", "ADM",
    "ADP", "ADSK", "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM",
    "ALB", "ALGN", "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP",
    "AMT", "AMZN", "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH", "APTV",
    "ARE", "ATO", "AVB", "AVGO", "AVY", "AWK", "AXON", "AXP", "AZO",
    # B
    "BA", "BAC", "BALL", "BAX", "BBWI", "BBY", "BDX", "BEN", "BF.B", "BG",
    "BIIB", "BIO", "BK", "BKNG", "BLK", "BMY", "BR", "BRK.B", "BRO", "BSX",
    "BWA", "BX", "BXP",
    # C
    "C", "CAG", "CAH", "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL",
    "CDNS", "CDW", "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI",
    "CINF", "CL", "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC",
    "CNP", "COF", "COO", "COP", "COR", "COST", "CPAY", "CPB", "CPRT", "CPT",
    "CRL", "CRM", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTLT", "CTRA", "CTSH",
    "CTVA", "CVS", "CVX",
    # D
    "D", "DAL", "DAY", "DD", "DE", "DECK", "DFS", "DG", "DGX", "DHI",
    "DHR", "DIS", "DLR", "DLTR", "DOC", "DOV", "DOW", "DPZ", "DRI", "DTE",
    "DUK", "DVA", "DVN",
    # E
    "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EG", "EIX", "EL", "ELV",
    "EMN", "EMR", "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ES", "ESS",
    "ETN", "ETR", "ETSY", "EVRG", "EW", "EXC", "EXPD", "EXPE", "EXR",
    # F
    "F", "FANG", "FAST", "FCX", "FDS", "FDX", "FE", "FFIV", "FI", "FICO",
    "FIS", "FITB", "FLT", "FMC", "FOX", "FOXA", "FRT", "FSLR", "FTNT", "FTV",
    # G
    "GD", "GDDY", "GE", "GEHC", "GEN", "GEV", "GILD", "GIS", "GL", "GLW",
    "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW",
    # H
    "HAL", "HAS", "HBAN", "HCA", "HD", "HES", "HIG", "HII", "HLT", "HOLX",
    "HON", "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUBB", "HUM", "HWM",
    # I
    "IBM", "ICE", "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC", "INTU", "INVH",
    "IP", "IPG", "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ",
    # J
    "J", "JBHT", "JBL", "JCI", "JKHY", "JNJ", "JNPR", "JPM",
    # K
    "K", "KDP", "KEY", "KEYS", "KHC", "KIM", "KKR", "KLAC", "KMB", "KMI",
    "KMX", "KO", "KR",
    # L
    "KVUE", "L", "LDOS", "LEN", "LH", "LHX", "LIN", "LKQ", "LLY", "LMT",
    "LNT", "LOW", "LRCX", "LULU", "LUV", "LVS", "LW", "LYB", "LYV",
    # M
    "MA", "MAA", "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT",
    "MET", "META", "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST",
    "MO", "MOH", "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRO", "MS", "MSCI",
    "MSFT", "MSI", "MTB", "MTCH", "MTD", "MU",
    # N
    "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE", "NOC", "NOW",
    "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWS", "NWSA",
    # O
    "O", "ODFL", "OKE", "OMC", "ON", "ORCL", "ORLY", "OTIS", "OXY",
    # P
    "PANW", "PARA", "PAYC", "PAYX", "PCAR", "PCG", "PEG", "PEP", "PFE", "PFG",
    "PG", "PGR", "PH", "PHM", "PKG", "PLD", "PLTR", "PM", "PNC", "PNR",
    "PNW", "PODD", "POOL", "PPG", "PPL", "PRU", "PSA", "PSX", "PTC", "PWR",
    "PYPL",
    # Q
    "QCOM", "QRVO",
    # R
    "RCL", "REG", "REGN", "RF", "RJF", "RL", "RMD", "ROK", "ROL", "ROP",
    "ROST", "RSG", "RTX",
    # S
    "SBAC", "SBUX", "SCHW", "SHW", "SJM", "SLB", "SMCI", "SNA", "SNPS", "SO",
    "SOLV", "SPG", "SPGI", "SRE", "STE", "STLD", "STT", "STX", "STZ", "SWK",
    "SWKS", "SYF", "SYK", "SYY",
    # T
    "T", "TAP", "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TFX", "TGT",
    "TJX", "TMO", "TMUS", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA",
    "TSN", "TT", "TTWO", "TXN", "TXT", "TYL",
    # U
    "UAL", "UBER", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS", "URI", "USB",
    # V
    "V", "VICI", "VLO", "VLTO", "VMC", "VRSK", "VRSN", "VRTX", "VST", "VTR",
    "VTRS", "VZ",
    # W
    "WAB", "WAT", "WBA", "WBD", "WDC", "WEC", "WELL", "WFC", "WM", "WMB",
    "WMT", "WRB", "WST", "WTW", "WY", "WYNN",
    # X-Z
    "XEL", "XOM", "XYL", "YUM", "ZBH", "ZBRA", "ZTS",
]
# fmt: on

# Major ETFs - Index, Sector, Factor, and Bond ETFs
# fmt: off
ETF_SYMBOLS = [
    # Broad Market Index ETFs
    "SPY", "IVV", "VOO",      # S&P 500
    "QQQ", "QQQM",            # Nasdaq 100
    "DIA",                    # Dow Jones
    "IWM", "IWN", "IWO",      # Russell 2000 (total, value, growth)
    "VTI", "ITOT",            # Total US Market
    "VTV", "VUG",             # Value / Growth
    "VB", "VBR", "VBK",       # Small Cap (total, value, growth)
    # International
    "EFA", "VEA", "IEFA",     # Developed Markets ex-US
    "EEM", "VWO", "IEMG",     # Emerging Markets
    "VXUS",                   # Total International
    "FXI",                    # China Large-Cap
    "EWJ",                    # Japan
    "EWG",                    # Germany
    "EWU",                    # UK
    # Sector ETFs (SPDR Select Sector)
    "XLK",                    # Technology
    "XLF",                    # Financials
    "XLV",                    # Health Care
    "XLE",                    # Energy
    "XLI",                    # Industrials
    "XLY",                    # Consumer Discretionary
    "XLP",                    # Consumer Staples
    "XLU",                    # Utilities
    "XLB",                    # Materials
    "XLRE",                   # Real Estate
    "XLC",                    # Communication Services
    # Thematic / Industry
    "ARKK", "ARKW", "ARKF",   # ARK Innovation, Internet, Fintech
    "SMH", "SOXX",            # Semiconductors
    "XBI", "IBB",             # Biotech
    "XHB",                    # Homebuilders
    "XRT",                    # Retail
    "KRE",                    # Regional Banks
    "XOP",                    # Oil & Gas Exploration
    "TAN",                    # Solar
    "ICLN",                   # Clean Energy
    # Factor ETFs
    "MTUM",                   # Momentum
    "VLUE",                   # Value
    "QUAL",                   # Quality
    "SIZE",                   # Size
    "USMV", "SPLV",           # Low Volatility
    # Fixed Income
    "AGG", "BND",             # Total Bond Market
    "TLT", "IEF", "SHY",      # Treasuries (Long, Intermediate, Short)
    "LQD",                    # Investment Grade Corporate
    "HYG", "JNK",             # High Yield Corporate
    "TIP",                    # TIPS (Inflation Protected)
    "MUB",                    # Municipal Bonds
    "EMB",                    # Emerging Market Bonds
    # Leveraged / Inverse (use with caution)
    "TQQQ", "SQQQ",           # 3x / -3x Nasdaq
    "SPXL", "SPXS",           # 3x / -3x S&P 500
    "UVXY", "SVXY",           # VIX related
    # Volatility
    "VXX",                    # VIX Short-Term Futures
]
# fmt: on

# Commodity ETFs and Futures-based ETFs
# fmt: off
COMMODITY_SYMBOLS = [
    # Precious Metals
    "GLD", "IAU",             # Gold
    "SLV",                    # Silver
    "PPLT",                   # Platinum
    "PALL",                   # Palladium
    # Energy
    "USO", "BNO",             # Crude Oil (WTI, Brent)
    "UNG",                    # Natural Gas
    "UGA",                    # Gasoline
    # Agriculture
    "DBA",                    # Agriculture Basket
    "CORN",                   # Corn
    "WEAT",                   # Wheat
    "SOYB",                   # Soybeans
    "CANE",                   # Sugar
    "JO",                     # Coffee
    "NIB",                    # Cocoa
    # Industrial Metals
    "DBB",                    # Base Metals Basket
    "CPER",                   # Copper
    # Broad Commodity
    "DJP",                    # Bloomberg Commodity Index
    "GSG",                    # S&P GSCI Commodity
    "PDBC",                   # Diversified Commodity
    "COM",                    # Direxion Auspice Broad Commodity
]
# fmt: on


class UniverseManager:
    """Manages stock universes for backtesting."""

    def __init__(self, storage_path: Path) -> None:
        """Initialize universe manager.

        Args:
            storage_path: Path to store universe data
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def get_sp500_symbols(self) -> list[str]:
        """Get current S&P 500 symbols.

        Returns:
            List of S&P 500 ticker symbols
        """
        return SP500_SYMBOLS.copy()

    def get_etf_symbols(self) -> list[str]:
        """Get major ETF symbols.

        Returns:
            List of ETF ticker symbols
        """
        return ETF_SYMBOLS.copy()

    def get_commodity_symbols(self) -> list[str]:
        """Get commodity ETF symbols.

        Returns:
            List of commodity ETF ticker symbols
        """
        return COMMODITY_SYMBOLS.copy()

    def get_expanded_universe(self) -> list[str]:
        """Get expanded universe: S&P 500 + ETFs + Commodities.

        Returns:
            List of all ticker symbols (deduplicated)
        """
        all_symbols = SP500_SYMBOLS + ETF_SYMBOLS + COMMODITY_SYMBOLS
        # Deduplicate while preserving order
        seen = set()
        result = []
        for s in all_symbols:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def save_custom_universe(self, name: str, symbols: list[str]) -> None:
        """Save a custom universe.

        Args:
            name: Universe name
            symbols: List of ticker symbols
        """
        file_path = self.storage_path / f"{name}.csv"
        df = pd.DataFrame({"symbol": symbols})
        df.to_csv(file_path, index=False)
        logger.info(f"Saved universe '{name}' with {len(symbols)} symbols")

    def load_universe(self, name: str) -> list[str]:
        """Load a universe by name.

        Args:
            name: Universe name. Built-in options:
                - 'sp500': S&P 500 stocks
                - 'etfs': Major ETFs
                - 'commodities': Commodity ETFs
                - 'expanded': S&P 500 + ETFs + Commodities

        Returns:
            List of ticker symbols
        """
        name_lower = name.lower()

        # Built-in universes
        if name_lower == "sp500":
            return self.get_sp500_symbols()
        if name_lower in ("etfs", "etf"):
            return self.get_etf_symbols()
        if name_lower in ("commodities", "commodity"):
            return self.get_commodity_symbols()
        if name_lower == "expanded":
            return self.get_expanded_universe()

        # Custom universe from file
        file_path = self.storage_path / f"{name}.csv"
        if not file_path.exists():
            raise ValueError(f"Universe '{name}' not found")

        df = pd.read_csv(file_path)
        return df["symbol"].tolist()

    def list_universes(self) -> list[str]:
        """List all available universes.

        Returns:
            List of universe names
        """
        # Built-in universes
        universes = ["sp500", "etfs", "commodities", "expanded"]
        # Custom universes from files
        universes.extend(f.stem for f in self.storage_path.glob("*.csv"))
        return universes

    def filter_universe(
        self,
        symbols: list[str],
        min_market_cap: float | None = None,
        sectors: list[str] | None = None,
        exclude_symbols: list[str] | None = None,
    ) -> list[str]:
        """Filter a universe based on criteria.

        Args:
            symbols: Input symbol list
            min_market_cap: Minimum market cap filter
            sectors: List of sectors to include
            exclude_symbols: Symbols to exclude

        Returns:
            Filtered list of symbols
        """
        result = symbols.copy()

        if exclude_symbols:
            result = [s for s in result if s not in exclude_symbols]

        # Note: market_cap and sector filtering would require fundamental data
        # This is a placeholder for the interface
        if min_market_cap or sectors:
            logger.warning(
                "Market cap and sector filtering requires fundamental data to be loaded"
            )

        return result
