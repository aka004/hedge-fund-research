#!/usr/bin/env python3
"""
Source Fetcher - Pre-fetch real sources for research agents
============================================================

Fetches actual news, filings, and company info before agents run.
Prevents source hallucination by providing real data to cite.

Usage:
    from source_fetcher import SourceFetcher
    
    fetcher = SourceFetcher()
    sources = fetcher.fetch_all("MU", "Micron Technology")
    context = sources.to_context()
"""

import os
import re
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus

# Try to import requests for HTTP calls
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class NewsItem:
    title: str
    source: str
    date: str
    url: str
    snippet: str = ""


@dataclass
class FilingInfo:
    filing_type: str
    filing_date: str
    description: str
    url: str


@dataclass
class CompanyInfo:
    name: str
    ticker: str
    sector: str = ""
    industry: str = ""
    description: str = ""
    website: str = ""
    employees: int = 0


@dataclass
class FetchedSources:
    """All pre-fetched sources for a ticker."""
    ticker: str
    company_name: str
    fetched_at: str
    company_info: Optional[CompanyInfo] = None
    recent_news: List[NewsItem] = field(default_factory=list)
    sec_filings: List[FilingInfo] = field(default_factory=list)
    earnings_dates: List[str] = field(default_factory=list)
    analyst_summary: str = ""
    
    def to_context(self) -> str:
        """Format all sources as context for agent injection."""
        parts = [
            "\n# PRE-FETCHED SOURCES (VERIFIED - CITE THESE)",
            f"**Fetched at:** {self.fetched_at}",
            "\n⚠️ **Use these real sources instead of inventing URLs.**\n",
        ]
        
        # Company Info
        if self.company_info:
            parts.append(f"""
## Company Overview
- **Name:** {self.company_info.name}
- **Ticker:** {self.company_info.ticker}
- **Sector:** {self.company_info.sector or 'N/A'}
- **Industry:** {self.company_info.industry or 'N/A'}
- **Employees:** {self.company_info.employees:,} if self.company_info.employees else 'N/A'
- **Website:** {self.company_info.website or 'N/A'}

{self.company_info.description[:500] if self.company_info.description else ''}
""")
        
        # Recent News
        if self.recent_news:
            parts.append("\n## Recent News (Real Headlines - OK to cite)")
            for i, news in enumerate(self.recent_news[:10], 1):
                parts.append(f"{i}. **{news.title}** - {news.source} ({news.date})")
                if news.snippet:
                    parts.append(f"   > {news.snippet[:200]}...")
        else:
            parts.append("\n## Recent News\nNo recent news fetched. Cite sources generically (e.g., 'Recent news reports indicate...')")
        
        # SEC Filings
        if self.sec_filings:
            parts.append("\n## SEC Filings (Real - OK to cite)")
            for filing in self.sec_filings[:5]:
                parts.append(f"- **{filing.filing_type}** ({filing.filing_date}): {filing.description}")
                parts.append(f"  URL: {filing.url}")
        else:
            parts.append("\n## SEC Filings\nNo filings fetched. Cite generically (e.g., 'According to the company's most recent 10-K...')")
        
        # Earnings
        if self.earnings_dates:
            parts.append(f"\n## Upcoming Earnings\n- {', '.join(self.earnings_dates)}")
        
        # Analyst Summary
        if self.analyst_summary:
            parts.append(f"\n## Analyst Consensus\n{self.analyst_summary}")
        
        return "\n".join(parts)


class SourceFetcher:
    """
    Fetches real sources for research agents.
    
    Uses free APIs where possible:
    - Yahoo Finance for company info
    - SEC EDGAR for filings
    - News via various free sources
    """
    
    def __init__(self):
        self.session = requests.Session() if REQUESTS_AVAILABLE else None
        if self.session:
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (research-bot; contact@example.com)'
            })
    
    def fetch_all(self, ticker: str, company_name: str) -> FetchedSources:
        """Fetch all available sources for a ticker."""
        sources = FetchedSources(
            ticker=ticker,
            company_name=company_name,
            fetched_at=datetime.now().isoformat()
        )
        
        if not REQUESTS_AVAILABLE:
            print("Warning: requests not available, skipping source fetch")
            return sources
        
        # Fetch company info from yfinance (already have this data)
        sources.company_info = self._fetch_company_info(ticker)
        
        # Fetch SEC filings
        sources.sec_filings = self._fetch_sec_filings(ticker)
        
        # Fetch news (try multiple sources)
        sources.recent_news = self._fetch_news(ticker, company_name)
        
        return sources
    
    def _fetch_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Fetch company info from yfinance."""
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            
            return CompanyInfo(
                name=info.get('longName', ticker),
                ticker=ticker,
                sector=info.get('sector', ''),
                industry=info.get('industry', ''),
                description=info.get('longBusinessSummary', ''),
                website=info.get('website', ''),
                employees=info.get('fullTimeEmployees', 0)
            )
        except Exception as e:
            print(f"Company info fetch error: {e}")
            return None
    
    def _fetch_sec_filings(self, ticker: str) -> List[FilingInfo]:
        """Fetch recent SEC filings from EDGAR."""
        filings = []
        
        try:
            # Get CIK from ticker
            cik_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=&dateb=&owner=include&count=10&output=atom"
            
            response = self.session.get(cik_url, timeout=10)
            if response.status_code != 200:
                return filings
            
            # Parse the atom feed for filing info
            # Simple regex parsing (not full XML parsing to avoid dependencies)
            entries = re.findall(r'<entry>(.*?)</entry>', response.text, re.DOTALL)
            
            for entry in entries[:5]:
                title_match = re.search(r'<title>(.*?)</title>', entry)
                link_match = re.search(r'<link href="(.*?)"', entry)
                date_match = re.search(r'<updated>(.*?)</updated>', entry)
                
                if title_match and link_match:
                    title = title_match.group(1)
                    # Extract filing type from title
                    filing_type = title.split(' - ')[0] if ' - ' in title else title[:20]
                    
                    filings.append(FilingInfo(
                        filing_type=filing_type.strip(),
                        filing_date=date_match.group(1)[:10] if date_match else "Unknown",
                        description=title,
                        url=link_match.group(1)
                    ))
            
        except Exception as e:
            print(f"SEC filings fetch error: {e}")
        
        return filings
    
    def _fetch_news(self, ticker: str, company_name: str) -> List[NewsItem]:
        """Fetch recent news from free sources."""
        news = []
        
        # Try Google News RSS (free, no API key)
        try:
            query = quote_plus(f"{company_name} {ticker} stock")
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            
            response = self.session.get(rss_url, timeout=10)
            if response.status_code == 200:
                # Parse RSS items
                items = re.findall(r'<item>(.*?)</item>', response.text, re.DOTALL)
                
                for item in items[:10]:
                    title_match = re.search(r'<title>(.*?)</title>', item)
                    link_match = re.search(r'<link>(.*?)</link>', item)
                    date_match = re.search(r'<pubDate>(.*?)</pubDate>', item)
                    source_match = re.search(r'<source.*?>(.*?)</source>', item)
                    
                    if title_match:
                        # Clean up title (remove CDATA)
                        title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title_match.group(1))
                        title = title.replace('&amp;', '&').replace('&quot;', '"')
                        
                        news.append(NewsItem(
                            title=title,
                            source=source_match.group(1) if source_match else "Google News",
                            date=date_match.group(1)[:16] if date_match else "Recent",
                            url=link_match.group(1) if link_match else "",
                            snippet=""
                        ))
        
        except Exception as e:
            print(f"News fetch error: {e}")
        
        return news


# CLI for testing
if __name__ == "__main__":
    import sys
    
    ticker = sys.argv[1] if len(sys.argv) > 1 else "MU"
    company = sys.argv[2] if len(sys.argv) > 2 else "Micron Technology"
    
    print(f"\n=== Fetching sources for {ticker} ({company}) ===\n")
    
    fetcher = SourceFetcher()
    sources = fetcher.fetch_all(ticker, company)
    
    print(sources.to_context())
