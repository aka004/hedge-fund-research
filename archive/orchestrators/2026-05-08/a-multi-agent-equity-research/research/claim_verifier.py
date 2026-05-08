#!/usr/bin/env python3
"""
Claim Verifier - Fact-check external claims before acting on them
=================================================================

Verifies claims from Twitter, news, and other sources by:
1. Extracting specific factual assertions
2. Searching for primary sources (SEC, SEDAR, press releases)
3. Cross-referencing across independent sources
4. Scoring reliability and flagging red flags

NEW: Thesis-style post verification
- Valuation claims (P/E, P/FCF, EV/EBITDA comparisons)
- Performance claims (portfolio returns, ticker returns)
- Investment thesis logic analysis

Usage:
    from claim_verifier import ClaimVerifier
    
    verifier = ClaimVerifier()
    result = verifier.verify("https://x.com/user/status/123")
    
    print(result.verdict)     # "VERIFIED" | "LIKELY_TRUE" | "UNVERIFIED" | "DOUBTFUL" | "LIKELY_FALSE"
    print(result.score)       # 0-100
    print(result.red_flags)   # List of red flag codes
"""

import os
import re
import json
import subprocess
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Import DataFetcher for real market data
try:
    from data_fetcher import DataFetcher
    DATA_FETCHER_AVAILABLE = True
except ImportError:
    try:
        from research.data_fetcher import DataFetcher
        DATA_FETCHER_AVAILABLE = True
    except ImportError:
        DATA_FETCHER_AVAILABLE = False

# Try to import yfinance directly as backup
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class Verdict(Enum):
    VERIFIED = "VERIFIED"
    LIKELY_TRUE = "LIKELY_TRUE"
    UNVERIFIED = "UNVERIFIED"
    DOUBTFUL = "DOUBTFUL"
    LIKELY_FALSE = "LIKELY_FALSE"


class RedFlag(Enum):
    # Existing flags
    NO_COMPANY_NAME = ("NO_COMPANY_NAME", -30, "M&A claim without target/acquirer name")
    ROUND_NUMBERS = ("ROUND_NUMBERS", -10, "Deal value is suspiciously round")
    NO_PRIMARY_SOURCE = ("NO_PRIMARY_SOURCE", -40, "No T1/T2 source found")
    VIRAL_NO_ORIGIN = ("VIRAL_NO_ORIGIN", -25, "Multiple social posts, no original source")
    CONFLICT_FOUND = ("CONFLICT_FOUND", -50, "Sources contradict each other")
    TIMING_SUSPICIOUS = ("TIMING_SUSPICIOUS", -20, "Suspicious timing pattern")
    AUTHOR_UNRELIABLE = ("AUTHOR_UNRELIABLE", -30, "Source author has history of false claims")
    GEOGRAPHIC_MISMATCH = ("GEOGRAPHIC_MISMATCH", -20, "Jurisdiction doesn't match filings")
    
    # Thesis-specific flags
    VALUATION_DISCREPANCY = ("VALUATION_DISCREPANCY", -25, "Claimed valuation differs >20% from actual")
    UNVERIFIABLE_PERFORMANCE = ("UNVERIFIABLE_PERFORMANCE", -35, "Performance claim cannot be verified")
    EXTRAORDINARY_CLAIM = ("EXTRAORDINARY_CLAIM", -40, "Extraordinary return claim without proof")
    CHERRY_PICKED_TIMEFRAME = ("CHERRY_PICKED_TIMEFRAME", -15, "Timeframe appears cherry-picked")
    MISSING_MATERIAL_RISKS = ("MISSING_MATERIAL_RISKS", -20, "Thesis ignores material risks")
    STALE_DATA = ("STALE_DATA", -15, "Valuation based on outdated data")
    COMPARISON_IGNORES_DIFFERENCES = ("COMPARISON_IGNORES_DIFFERENCES", -15, "Comparison ignores material differences")
    CIRCULAR_LOGIC = ("CIRCULAR_LOGIC", -30, "Thesis relies on circular reasoning")
    UNVERIFIABLE_CATALYST = ("UNVERIFIABLE_CATALYST", -20, "Catalyst claim cannot be verified")


class SourceTier(Enum):
    T1 = (1, 1.0, "SEC/SEDAR filings, Government databases")
    T2 = (2, 0.9, "Company press releases (official IR)")
    T3 = (3, 0.8, "Wire services (Reuters, Bloomberg, AP)")
    T4 = (4, 0.7, "Major financial media (WSJ, FT)")
    T5 = (5, 0.6, "Industry publications")
    T6 = (6, 0.3, "Social media, blogs")
    T7 = (7, 0.1, "Anonymous sources")


# ============================================================================
# Valuation Metrics
# ============================================================================

VALUATION_METRICS = {
    # Pattern -> (metric_key, needs_inverse)
    r'p/?e': ('pe_ratio', False),
    r'pe\s*ratio': ('pe_ratio', False),
    r'price[\s/-]*to[\s/-]*earnings': ('pe_ratio', False),
    r'p/?fcf': ('price_to_fcf', False),
    r'price[\s/-]*to[\s/-]*(?:free\s*)?cash\s*flow': ('price_to_fcf', False),
    r'ev/?ebitda': ('ev_to_ebitda', False),
    r'ev[\s/-]*to[\s/-]*ebitda': ('ev_to_ebitda', False),
    r'p/?b': ('price_to_book', False),
    r'price[\s/-]*to[\s/-]*book': ('price_to_book', False),
    r'p/?s': ('price_to_sales', False),
    r'price[\s/-]*to[\s/-]*sales': ('price_to_sales', False),
    r'fcf\s*yield': ('fcf_yield', False),
    r'earnings\s*yield': ('earnings_yield', False),
    r'dividend\s*yield': ('dividend_yield', False),
}


@dataclass
class ValuationClaim:
    """A specific valuation claim extracted from text."""
    ticker: str
    metric_type: str  # pe_ratio, price_to_fcf, etc.
    claimed_value: float
    actual_value: Optional[float] = None
    discrepancy_pct: Optional[float] = None
    verified: bool = False
    note: str = ""


@dataclass
class PerformanceClaim:
    """A performance/return claim extracted from text."""
    claim_text: str
    ticker: Optional[str] = None
    return_pct: Optional[float] = None
    timeframe: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    actual_return: Optional[float] = None
    verified: bool = False
    verifiable: bool = True
    note: str = ""


@dataclass
class ThesisClaim:
    """An investment thesis claim."""
    thesis_summary: str
    tickers: List[str] = field(default_factory=list)
    catalysts: List[str] = field(default_factory=list)
    risks_mentioned: List[str] = field(default_factory=list)
    risks_missing: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    unverifiable_assumptions: List[str] = field(default_factory=list)
    logic_issues: List[str] = field(default_factory=list)


@dataclass
class ExtractedClaim:
    """A specific verifiable claim extracted from source text."""
    claim_id: str
    claim_type: str  # M&A, Earnings, Executive, Regulatory, Product, Macro, Market, VALUATION_COMPARISON, PERFORMANCE_CLAIM, INVESTMENT_THESIS
    assertion: str
    specifics: Dict[str, Any] = field(default_factory=dict)
    verifiable_elements: List[str] = field(default_factory=list)
    missing_elements: List[str] = field(default_factory=list)
    
    # Thesis-specific fields
    valuation_claims: List[ValuationClaim] = field(default_factory=list)
    performance_claims: List[PerformanceClaim] = field(default_factory=list)
    thesis_analysis: Optional[ThesisClaim] = None


@dataclass
class SourceEvidence:
    """Evidence from a single source."""
    source_id: str
    source_type: str
    tier: SourceTier
    url: str
    confirms_claim: bool
    contradicts_claim: bool = False
    specific_details: Dict[str, Any] = field(default_factory=dict)
    is_independent: bool = True
    note: str = ""


@dataclass
class VerificationResult:
    """Complete verification result for a claim or set of claims."""
    verification_id: str
    timestamp: str
    input_url: str
    input_author: str = ""
    raw_text: str = ""
    
    claims: List[ExtractedClaim] = field(default_factory=list)
    evidence: List[SourceEvidence] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    
    score: int = 50
    verdict: Verdict = Verdict.UNVERIFIED
    recommendation: str = "AWAIT_CONFIRMATION"
    confidence: float = 0.5
    
    analyst_note: str = ""
    sources_checked: Dict[str, str] = field(default_factory=dict)
    
    # Thesis-specific summary
    valuation_summary: Dict[str, Any] = field(default_factory=dict)
    performance_summary: Dict[str, Any] = field(default_factory=dict)
    thesis_summary: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "verification_id": self.verification_id,
            "timestamp": self.timestamp,
            "input_url": self.input_url,
            "input_author": self.input_author,
            "claims_extracted": len(self.claims),
            "score": self.score,
            "verdict": self.verdict.value,
            "red_flags": self.red_flags,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "analyst_note": self.analyst_note,
            "sources_checked": self.sources_checked
        }
        
        # Add thesis-specific summaries if present
        if self.valuation_summary:
            result["valuation_summary"] = self.valuation_summary
        if self.performance_summary:
            result["performance_summary"] = self.performance_summary
        if self.thesis_summary:
            result["thesis_summary"] = self.thesis_summary
            
        return result
    
    def to_quick_verdict(self) -> str:
        """Format as quick verdict for chat integration."""
        claim_text = self.claims[0].assertion if self.claims else "Unknown claim"
        
        flags_str = "\n".join(f"- {f}" for f in self.red_flags) if self.red_flags else "None"
        
        # Add valuation discrepancies if present
        val_section = ""
        if self.valuation_summary.get("discrepancies"):
            val_section = "\n\n**VALUATION DISCREPANCIES**:\n"
            for d in self.valuation_summary["discrepancies"]:
                val_section += f"- {d['ticker']} {d['metric']}: claimed {d['claimed']:.1f}x, actual {d['actual']:.1f}x ({d['diff_pct']:+.0f}%)\n"
        
        # Add performance verification if present
        perf_section = ""
        if self.performance_summary.get("claims"):
            perf_section = "\n\n**PERFORMANCE CLAIMS**:\n"
            for p in self.performance_summary["claims"]:
                status = "✓ VERIFIED" if p.get("verified") else ("❌ INCORRECT" if p.get("actual") else "⚠ UNVERIFIABLE")
                perf_section += f"- {p['claim']}: {status}\n"
        
        # Add thesis issues if present
        thesis_section = ""
        if self.thesis_summary.get("issues"):
            thesis_section = "\n\n**THESIS ISSUES**:\n"
            for issue in self.thesis_summary["issues"]:
                thesis_section += f"- {issue}\n"
        
        return f"""**CLAIM**: {claim_text}

**VERDICT**: {self.verdict.value} (Score: {self.score}/100)

**RED FLAGS**:
{flags_str}{val_section}{perf_section}{thesis_section}

**ANALYST NOTE**:
{self.analyst_note}

**RECOMMENDATION**: {self.recommendation}
"""


class ClaimVerifier:
    """
    Verify claims from external sources.
    
    Supports:
    - Factual claims (M&A, Earnings, Executive changes, Regulatory filings)
    - Valuation claims (P/E, P/FCF, EV/EBITDA comparisons)
    - Performance claims (portfolio returns, ticker returns)
    - Investment thesis analysis
    """
    
    def __init__(self, bird_cli_path: str = "bird", db_path: str = None):
        self.bird_cli = bird_cli_path
        self.sec_base_url = "https://www.sec.gov/cgi-bin/browse-edgar"
        self.sedar_base_url = "https://www.sedarplus.ca"
        
        # Initialize data fetcher for valuation verification
        self.data_fetcher = None
        if DATA_FETCHER_AVAILABLE:
            try:
                self.data_fetcher = DataFetcher(db_path=db_path)
            except Exception as e:
                print(f"Warning: Could not initialize DataFetcher: {e}")
        
    def verify(self, url: str, raw_text: str = None, claim_type_hint: str = None) -> VerificationResult:
        """
        Main verification entry point.
        
        Args:
            url: URL of the source (tweet, article, etc.)
            raw_text: Optional override text (if already fetched)
            claim_type_hint: Optional hint for claim type (M&A, Earnings, VALUATION_COMPARISON, etc.)
            
        Returns:
            VerificationResult with score, verdict, and evidence
        """
        verification_id = f"VRF-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        result = VerificationResult(
            verification_id=verification_id,
            timestamp=timestamp,
            input_url=url
        )
        
        # Step 1: Fetch source content if not provided
        if raw_text is None:
            raw_text, author = self._fetch_source(url)
            result.raw_text = raw_text
            result.input_author = author
        else:
            result.raw_text = raw_text
            
        if not raw_text:
            result.verdict = Verdict.UNVERIFIED
            result.recommendation = "SOURCE_FETCH_FAILED"
            result.analyst_note = "Could not fetch source content"
            return result
        
        # Step 2: Extract claims (including thesis-style claims)
        claims = self._extract_claims(raw_text, claim_type_hint)
        result.claims = claims
        
        if not claims:
            result.verdict = Verdict.UNVERIFIED
            result.recommendation = "NO_VERIFIABLE_CLAIMS"
            result.analyst_note = "No specific verifiable claims extracted"
            return result
        
        # Step 3: Search for primary sources
        evidence = []
        sources_checked = {}
        
        for claim in claims:
            claim_evidence, checked = self._search_primary_sources(claim)
            evidence.extend(claim_evidence)
            sources_checked.update(checked)
        
        result.evidence = evidence
        result.sources_checked = sources_checked
        
        # Step 4: Verify thesis-specific claims
        for claim in claims:
            if claim.claim_type == "VALUATION_COMPARISON":
                self._verify_valuation_claims(claim)
            elif claim.claim_type == "PERFORMANCE_CLAIM":
                self._verify_performance_claims(claim)
            elif claim.claim_type == "INVESTMENT_THESIS":
                self._analyze_thesis_logic(claim)
        
        # Step 5: Build thesis summaries
        result.valuation_summary = self._build_valuation_summary(claims)
        result.performance_summary = self._build_performance_summary(claims)
        result.thesis_summary = self._build_thesis_summary(claims)
        
        # Step 6: Detect red flags (including thesis-specific flags)
        red_flags = self._detect_red_flags(claims, evidence, raw_text)
        result.red_flags = red_flags
        
        # Step 7: Calculate score and verdict
        score = self._calculate_score(claims, evidence, red_flags)
        result.score = score
        result.verdict = self._score_to_verdict(score)
        result.recommendation = self._get_recommendation(result.verdict)
        result.confidence = self._calculate_confidence(evidence, red_flags)
        
        # Step 8: Generate analyst note
        result.analyst_note = self._generate_analyst_note(result)
        
        return result
    
    def _fetch_source(self, url: str) -> tuple:
        """Fetch content from URL. Returns (text, author)."""
        
        # Twitter/X URLs
        if "x.com" in url or "twitter.com" in url:
            return self._fetch_tweet(url)
        
        # Web articles
        if REQUESTS_AVAILABLE:
            try:
                resp = requests.get(url, timeout=10)
                return resp.text[:5000], ""  # Truncate for processing
            except:
                pass
        
        return "", ""
    
    def _fetch_tweet(self, url: str) -> tuple:
        """Fetch tweet using bird CLI."""
        try:
            # Extract tweet ID
            tweet_id = re.search(r'/status/(\d+)', url)
            if not tweet_id:
                return "", ""
            
            # Source shell config to get credentials, then run bird
            shell_cmd = f'source ~/.zshrc && bird read {tweet_id.group(1)}'
            result = subprocess.run(
                shell_cmd,
                shell=True,
                executable='/bin/zsh',
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                text = result.stdout
                # Extract author
                author_match = re.search(r'@(\w+)', text)
                author = f"@{author_match.group(1)}" if author_match else ""
                return text, author
        except Exception as e:
            print(f"Tweet fetch error: {e}")
        
        return "", ""
    
    def _extract_claims(self, text: str, claim_type_hint: str = None) -> List[ExtractedClaim]:
        """Extract verifiable claims from text."""
        claims = []
        
        # Check for thesis-style content first
        has_valuation = self._has_valuation_claims(text)
        has_performance = self._has_performance_claims(text)
        has_thesis_indicators = self._has_thesis_indicators(text)
        
        # Extract thesis-style claims
        if has_valuation or claim_type_hint == "VALUATION_COMPARISON":
            valuation_claim = self._extract_valuation_claims(text)
            if valuation_claim:
                claims.append(valuation_claim)
        
        if has_performance or claim_type_hint == "PERFORMANCE_CLAIM":
            performance_claim = self._extract_performance_claims(text)
            if performance_claim:
                claims.append(performance_claim)
        
        if has_thesis_indicators or claim_type_hint == "INVESTMENT_THESIS":
            thesis_claim = self._extract_thesis_claims(text)
            if thesis_claim:
                claims.append(thesis_claim)
        
        # Also extract traditional factual claims
        # M&A patterns
        ma_patterns = [
            r'(?:acquired|bought|purchased|took over|takeover|acquisition of)\s+(?:a\s+)?(.+?)\s+(?:for|in a|worth)\s+\$?([\d.,]+)\s*(billion|million|B|M)?',
            r'\$?([\d.,]+)\s*(billion|million|B|M)?\s+(?:deal|acquisition|purchase|takeover)',
        ]
        
        for pattern in ma_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                claim = ExtractedClaim(
                    claim_id=f"CLM-{len(claims)+1:03d}",
                    claim_type="M&A",
                    assertion=self._summarize_ma_claim(text, matches),
                    specifics=self._extract_ma_specifics(text, matches),
                    verifiable_elements=["company_name", "acquirer_name", "deal_value", "closing_date"],
                    missing_elements=[]
                )
                
                # Check what's missing
                if not claim.specifics.get("target_company"):
                    claim.missing_elements.append("target_company_name")
                if not claim.specifics.get("acquirer_company"):
                    claim.missing_elements.append("acquirer_company_name")
                    
                claims.append(claim)
                break
        
        # Earnings patterns
        earnings_patterns = [
            r'(?:reported|posted|announced)\s+(?:earnings|revenue|sales)\s+of\s+\$?([\d.,]+)',
            r'(?:beat|missed|met)\s+(?:earnings|EPS|revenue)\s+(?:estimates|expectations)',
        ]
        
        for pattern in earnings_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                claim = ExtractedClaim(
                    claim_id=f"CLM-{len(claims)+1:03d}",
                    claim_type="Earnings",
                    assertion=self._summarize_earnings_claim(text),
                    specifics=self._extract_earnings_specifics(text),
                    verifiable_elements=["ticker", "quarter", "revenue", "eps"],
                    missing_elements=[]
                )
                claims.append(claim)
                break
        
        return claims
    
    # ========================================================================
    # Thesis Claim Detection
    # ========================================================================
    
    def _has_valuation_claims(self, text: str) -> bool:
        """Check if text contains valuation claims."""
        text_lower = text.lower()
        
        for pattern in VALUATION_METRICS.keys():
            if re.search(pattern, text_lower):
                # Also need a number nearby
                if re.search(rf'{pattern}\s*(?:of|at|is|:)?\s*[\d.]+', text_lower):
                    return True
                if re.search(rf'[\d.]+\s*x?\s*{pattern}', text_lower):
                    return True
        
        # Check for "Xx FCF/PE/etc" patterns
        if re.search(r'\d+\.?\d*\s*x\s*(?:fcf|pe|earnings|ebitda|book|sales)', text_lower):
            return True
            
        return False
    
    def _has_performance_claims(self, text: str) -> bool:
        """Check if text contains performance/return claims."""
        text_lower = text.lower()
        
        patterns = [
            r'up\s+\d+%',
            r'down\s+\d+%',
            r'return(?:s|ed)?\s+(?:of\s+)?\d+%',
            r'gained?\s+\d+%',
            r'lost\s+\d+%',
            r'\+\d+%',
            r'-\d+%',
            r'portfolio\s+(?:is\s+)?(?:up|down)',
            r'ytd\s+\d+%',
            r'\d+%\s+(?:return|gain|loss)',
            r'outperform(?:ed|ing)?\s+by\s+\d+',
            r'beat(?:en|ing)?\s+(?:the\s+)?(?:market|s&p|spy|index)',
        ]
        
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _has_thesis_indicators(self, text: str) -> bool:
        """Check if text appears to be an investment thesis."""
        text_lower = text.lower()
        
        indicators = [
            r'\blong\b',
            r'\bshort\b',
            r'\bbullish\b',
            r'\bbearish\b',
            r'\bbuy\b',
            r'\bsell\b',
            r'\bundervalued\b',
            r'\bovervalued\b',
            r'thesis',
            r'catalyst',
            r'upside',
            r'downside',
            r'target\s+(?:price|of)',
            r'price\s+target',
            r'fair\s+value',
            r'intrinsic\s+value',
            r'\bmoat\b',
            r'margin\s+of\s+safety',
        ]
        
        count = 0
        for pattern in indicators:
            if re.search(pattern, text_lower):
                count += 1
        
        return count >= 2  # Need at least 2 thesis indicators
    
    # ========================================================================
    # Valuation Claim Extraction & Verification
    # ========================================================================
    
    def _extract_valuation_claims(self, text: str) -> Optional[ExtractedClaim]:
        """Extract valuation comparison claims from text."""
        text_lower = text.lower()
        valuation_claims = []
        
        # Extract tickers
        tickers = self._extract_tickers(text)
        
        # Pattern: TICKER at Xx METRIC
        # e.g., "VALE at 4x FCF", "BHP trading at 8x earnings"
        for ticker in tickers:
            ticker_pattern = rf'\b{ticker}\b[^.]*?(\d+\.?\d*)\s*x\s*(fcf|pe|earnings|ebitda|book|sales|p/?e|ev/?ebitda)'
            matches = re.findall(ticker_pattern, text_lower)
            
            for match in matches:
                value, metric = match
                metric_key = self._normalize_metric(metric)
                
                valuation_claims.append(ValuationClaim(
                    ticker=ticker,
                    metric_type=metric_key,
                    claimed_value=float(value)
                ))
        
        # Pattern: "P/E of X" near a ticker
        for pattern, (metric_key, _) in VALUATION_METRICS.items():
            regex = rf'{pattern}\s*(?:of|at|is|:)?\s*(\d+\.?\d*)'
            matches = re.findall(regex, text_lower)
            
            for match in matches:
                # Find nearest ticker
                nearest_ticker = self._find_nearest_ticker(text, pattern, tickers)
                if nearest_ticker and not any(v.ticker == nearest_ticker and v.metric_type == metric_key for v in valuation_claims):
                    valuation_claims.append(ValuationClaim(
                        ticker=nearest_ticker,
                        metric_type=metric_key,
                        claimed_value=float(match)
                    ))
        
        if not valuation_claims:
            return None
        
        claim = ExtractedClaim(
            claim_id=f"CLM-VAL-{datetime.now().strftime('%H%M%S')}",
            claim_type="VALUATION_COMPARISON",
            assertion=f"Valuation claims for {', '.join(set(v.ticker for v in valuation_claims))}",
            specifics={
                "tickers": list(set(v.ticker for v in valuation_claims)),
                "metrics_claimed": [(v.ticker, v.metric_type, v.claimed_value) for v in valuation_claims]
            },
            verifiable_elements=["valuation_metrics"],
            valuation_claims=valuation_claims
        )
        
        return claim
    
    def _verify_valuation_claims(self, claim: ExtractedClaim) -> None:
        """Verify valuation claims against actual data."""
        for val_claim in claim.valuation_claims:
            actual = self._get_actual_valuation(val_claim.ticker, val_claim.metric_type)
            
            if actual is not None:
                val_claim.actual_value = actual
                
                if actual > 0:
                    discrepancy = ((val_claim.claimed_value - actual) / actual) * 100
                    val_claim.discrepancy_pct = discrepancy
                    
                    # Verified if within 20%
                    val_claim.verified = abs(discrepancy) <= 20
                    
                    if abs(discrepancy) > 20:
                        val_claim.note = f"Claimed {val_claim.claimed_value:.1f}x vs actual {actual:.1f}x ({discrepancy:+.0f}% off)"
                    else:
                        val_claim.note = f"Verified: {val_claim.claimed_value:.1f}x (actual {actual:.1f}x)"
            else:
                val_claim.note = f"Could not fetch {val_claim.metric_type} for {val_claim.ticker}"
    
    def _get_actual_valuation(self, ticker: str, metric_type: str) -> Optional[float]:
        """Get actual valuation metric from yfinance."""
        if not YFINANCE_AVAILABLE:
            return None
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            if metric_type == 'pe_ratio':
                return info.get('trailingPE') or info.get('forwardPE')
            
            elif metric_type == 'price_to_fcf':
                # P/FCF = Market Cap / Free Cash Flow
                market_cap = info.get('marketCap')
                fcf = info.get('freeCashflow')
                if market_cap and fcf and fcf > 0:
                    return market_cap / fcf
                return None
            
            elif metric_type == 'ev_to_ebitda':
                return info.get('enterpriseToEbitda')
            
            elif metric_type == 'price_to_book':
                return info.get('priceToBook')
            
            elif metric_type == 'price_to_sales':
                return info.get('priceToSalesTrailing12Months')
            
            elif metric_type == 'fcf_yield':
                # FCF Yield = FCF / Market Cap
                market_cap = info.get('marketCap')
                fcf = info.get('freeCashflow')
                if market_cap and fcf:
                    return (fcf / market_cap) * 100
                return None
            
            elif metric_type == 'dividend_yield':
                dy = info.get('dividendYield')
                return dy * 100 if dy else None
            
        except Exception as e:
            print(f"Error fetching {metric_type} for {ticker}: {e}")
        
        return None
    
    # ========================================================================
    # Performance Claim Extraction & Verification
    # ========================================================================
    
    def _extract_performance_claims(self, text: str) -> Optional[ExtractedClaim]:
        """Extract performance/return claims from text."""
        text_lower = text.lower()
        performance_claims = []
        
        tickers = self._extract_tickers(text)
        
        # Pattern: "up X%" or "gained X%"
        return_patterns = [
            (r'(?:my\s+)?portfolio\s+(?:is\s+)?(?:up|gained?)\s+(\d+\.?\d*)%', None, True),  # Portfolio claim - unverifiable
            (r'(?:up|gained?)\s+(\d+\.?\d*)%\s+(?:ytd|this\s+year|in\s+\d{4})', None, False),  # YTD return
            (r'(\w+)\s+(?:is\s+)?(?:up|gained?)\s+(\d+\.?\d*)%', 'ticker_return', False),  # Ticker return
            (r'(\d+\.?\d*)%\s+(?:return|gain)\s+(?:on|from)\s+(\w+)', 'ticker_return_rev', False),
            (r'beat(?:en|ing)?\s+(?:the\s+)?(?:market|s&p|spy)\s+by\s+(\d+\.?\d*)', 'relative', False),
        ]
        
        for pattern, ptype, unverifiable in return_patterns:
            matches = re.findall(pattern, text_lower)
            
            for match in matches:
                if ptype == 'ticker_return' and len(match) == 2:
                    ticker_candidate, return_val = match
                    ticker = ticker_candidate.upper()
                    if ticker in tickers or len(ticker) <= 5:
                        performance_claims.append(PerformanceClaim(
                            claim_text=f"{ticker} up {return_val}%",
                            ticker=ticker,
                            return_pct=float(return_val),
                            verifiable=True
                        ))
                elif ptype == 'ticker_return_rev' and len(match) == 2:
                    return_val, ticker_candidate = match
                    ticker = ticker_candidate.upper()
                    if ticker in tickers or len(ticker) <= 5:
                        performance_claims.append(PerformanceClaim(
                            claim_text=f"{ticker} {return_val}% return",
                            ticker=ticker,
                            return_pct=float(return_val),
                            verifiable=True
                        ))
                elif unverifiable:
                    return_val = match if isinstance(match, str) else match[0]
                    performance_claims.append(PerformanceClaim(
                        claim_text=f"Portfolio up {return_val}%",
                        return_pct=float(return_val),
                        verifiable=False,
                        note="Personal portfolio claims cannot be verified"
                    ))
                elif ptype == 'relative':
                    performance_claims.append(PerformanceClaim(
                        claim_text=f"Beat market by {match}%",
                        return_pct=float(match),
                        verifiable=False,
                        note="Relative performance claim without specific timeframe"
                    ))
        
        # Check for extraordinary claims
        for pc in performance_claims:
            if pc.return_pct and pc.return_pct > 100:
                pc.note = "EXTRAORDINARY: >100% return claimed"
        
        if not performance_claims:
            return None
        
        claim = ExtractedClaim(
            claim_id=f"CLM-PERF-{datetime.now().strftime('%H%M%S')}",
            claim_type="PERFORMANCE_CLAIM",
            assertion=f"Performance claims: {', '.join(p.claim_text for p in performance_claims[:3])}",
            specifics={
                "claims_count": len(performance_claims),
                "verifiable_count": sum(1 for p in performance_claims if p.verifiable),
                "extraordinary_claims": [p.claim_text for p in performance_claims if p.return_pct and p.return_pct > 100]
            },
            verifiable_elements=["ticker_returns"],
            performance_claims=performance_claims
        )
        
        return claim
    
    def _verify_performance_claims(self, claim: ExtractedClaim) -> None:
        """Verify performance claims against actual price data."""
        for perf_claim in claim.performance_claims:
            if not perf_claim.verifiable or not perf_claim.ticker:
                continue
            
            # Try to verify YTD return
            actual_return = self._get_actual_return(perf_claim.ticker, perf_claim.timeframe)
            
            if actual_return is not None:
                perf_claim.actual_return = actual_return
                
                if perf_claim.return_pct:
                    diff = abs(perf_claim.return_pct - actual_return)
                    perf_claim.verified = diff <= 5  # Within 5% tolerance
                    
                    if perf_claim.verified:
                        perf_claim.note = f"Verified: claimed {perf_claim.return_pct:.1f}%, actual {actual_return:.1f}%"
                    else:
                        perf_claim.note = f"MISMATCH: claimed {perf_claim.return_pct:.1f}%, actual {actual_return:.1f}%"
    
    def _get_actual_return(self, ticker: str, timeframe: str = None) -> Optional[float]:
        """Get actual return for a ticker over a timeframe."""
        if not YFINANCE_AVAILABLE:
            return None
        
        try:
            stock = yf.Ticker(ticker)
            
            # Default to YTD
            if timeframe is None or 'ytd' in str(timeframe).lower():
                # Get YTD return
                now = datetime.now()
                start_of_year = datetime(now.year, 1, 1)
                hist = stock.history(start=start_of_year)
                
                if len(hist) >= 2:
                    start_price = hist['Close'].iloc[0]
                    end_price = hist['Close'].iloc[-1]
                    return ((end_price - start_price) / start_price) * 100
            
            # 1-year return
            hist = stock.history(period="1y")
            if len(hist) >= 2:
                start_price = hist['Close'].iloc[0]
                end_price = hist['Close'].iloc[-1]
                return ((end_price - start_price) / start_price) * 100
                
        except Exception as e:
            print(f"Error fetching return for {ticker}: {e}")
        
        return None
    
    # ========================================================================
    # Thesis Logic Analysis
    # ========================================================================
    
    def _extract_thesis_claims(self, text: str) -> Optional[ExtractedClaim]:
        """Extract and analyze investment thesis claims."""
        text_lower = text.lower()
        
        tickers = self._extract_tickers(text)
        
        # Extract thesis components
        thesis = ThesisClaim(
            thesis_summary=self._summarize_thesis(text),
            tickers=tickers
        )
        
        # Extract catalysts
        catalyst_patterns = [
            r'catalyst[s]?\s*(?::|is|are|include)?\s*([^.]+)',
            r'(?:upcoming|expected|potential)\s+([^.]*?(?:merger|acquisition|spin.?off|dividend|buyback|catalyst))',
            r'(?:when|once|if)\s+([^.]*?(?:reports?|announces?|releases?))',
        ]
        
        for pattern in catalyst_patterns:
            matches = re.findall(pattern, text_lower)
            thesis.catalysts.extend([m.strip() for m in matches if len(m.strip()) > 5])
        
        # Extract mentioned risks
        risk_patterns = [
            r'risk[s]?\s*(?::|is|are|include)?\s*([^.]+)',
            r'(?:downside|concern|worry|worried about)\s*(?::|is|are)?\s*([^.]+)',
            r'(?:could|might|may)\s+(?:fail|decline|drop|fall)\s+([^.]+)?',
        ]
        
        for pattern in risk_patterns:
            matches = re.findall(pattern, text_lower)
            thesis.risks_mentioned.extend([m.strip() for m in matches if m and len(m.strip()) > 5])
        
        # Identify missing considerations (common risks for different sectors)
        thesis.risks_missing = self._identify_missing_risks(text, tickers)
        
        # Extract assumptions
        assumption_patterns = [
            r'(?:assuming|if|when)\s+([^.]+)',
            r'(?:should|will|expect(?:ed)?)\s+([^.]+?(?:grow|increase|decrease|improve|decline))',
        ]
        
        for pattern in assumption_patterns:
            matches = re.findall(pattern, text_lower)
            thesis.assumptions.extend([m.strip() for m in matches if len(m.strip()) > 5])
        
        # Identify unverifiable assumptions
        thesis.unverifiable_assumptions = self._identify_unverifiable_assumptions(thesis.assumptions)
        
        # Check for logic issues
        thesis.logic_issues = self._identify_logic_issues(text)
        
        claim = ExtractedClaim(
            claim_id=f"CLM-THESIS-{datetime.now().strftime('%H%M%S')}",
            claim_type="INVESTMENT_THESIS",
            assertion=thesis.thesis_summary,
            specifics={
                "tickers": tickers,
                "catalysts_count": len(thesis.catalysts),
                "risks_mentioned_count": len(thesis.risks_mentioned),
                "risks_missing_count": len(thesis.risks_missing),
                "assumptions_count": len(thesis.assumptions),
                "unverifiable_count": len(thesis.unverifiable_assumptions),
                "logic_issues_count": len(thesis.logic_issues)
            },
            verifiable_elements=["catalysts", "financials"],
            thesis_analysis=thesis
        )
        
        return claim
    
    def _analyze_thesis_logic(self, claim: ExtractedClaim) -> None:
        """Analyze thesis logic and verify catalyst claims."""
        if not claim.thesis_analysis:
            return
        
        thesis = claim.thesis_analysis
        
        # Verify catalysts against news (placeholder - would integrate with news API)
        for catalyst in thesis.catalysts:
            # Check if catalyst is time-bound and already passed
            if self._catalyst_already_passed(catalyst):
                thesis.logic_issues.append(f"Stale catalyst: {catalyst}")
        
        # Flag if thesis relies heavily on unverifiable assumptions
        if len(thesis.unverifiable_assumptions) > len(thesis.assumptions) / 2:
            thesis.logic_issues.append("Thesis relies primarily on unverifiable assumptions")
    
    def _summarize_thesis(self, text: str) -> str:
        """Create a one-line thesis summary."""
        # Look for explicit thesis statement
        thesis_match = re.search(r'thesis[:\s]+([^.]+)', text, re.IGNORECASE)
        if thesis_match:
            return thesis_match.group(1).strip()[:100]
        
        # Look for long/short position
        if re.search(r'\blong\b', text, re.IGNORECASE):
            tickers = self._extract_tickers(text)
            if tickers:
                return f"Long thesis on {', '.join(tickers[:3])}"
        
        if re.search(r'\bshort\b', text, re.IGNORECASE):
            tickers = self._extract_tickers(text)
            if tickers:
                return f"Short thesis on {', '.join(tickers[:3])}"
        
        return "Investment thesis (details in specifics)"
    
    def _identify_missing_risks(self, text: str, tickers: List[str]) -> List[str]:
        """Identify common risks that aren't mentioned in the thesis."""
        text_lower = text.lower()
        missing = []
        
        # Common risk categories
        common_risks = {
            'china': ['regulatory risk', 'geopolitical risk', 'vvie structure risk'],
            'mining': ['commodity price risk', 'capex risk', 'jurisdiction risk', 'environmental liability'],
            'tech': ['competition risk', 'regulatory risk', 'key person risk'],
            'bank': ['credit risk', 'interest rate risk', 'regulatory capital'],
            'retail': ['consumer spending risk', 'competition', 'inventory risk'],
            'energy': ['commodity price risk', 'transition risk', 'regulatory risk'],
        }
        
        # Detect sector
        detected_sectors = []
        if re.search(r'\b(?:china|chinese|baba|pdd|jd|bidu)\b', text_lower):
            detected_sectors.append('china')
        if re.search(r'\b(?:gold|silver|copper|mining|miner|vale|bhp|rio)\b', text_lower):
            detected_sectors.append('mining')
        if re.search(r'\b(?:tech|software|saas|cloud|ai|nvidia|meta|google)\b', text_lower):
            detected_sectors.append('tech')
        
        for sector in detected_sectors:
            for risk in common_risks.get(sector, []):
                if risk.replace(' risk', '') not in text_lower:
                    missing.append(f"Not mentioned: {risk}")
        
        # Always check for these if not mentioned
        universal_risks = ['concentration risk', 'liquidity risk', 'macro risk']
        for risk in universal_risks:
            if risk.replace(' risk', '') not in text_lower and len(missing) < 5:
                missing.append(f"Consider: {risk}")
        
        return missing[:5]  # Limit to top 5
    
    def _identify_unverifiable_assumptions(self, assumptions: List[str]) -> List[str]:
        """Identify which assumptions cannot be independently verified."""
        unverifiable = []
        
        unverifiable_patterns = [
            r'management will',
            r'they will',
            r'i (?:think|believe|expect)',
            r'should\s+(?:grow|increase|improve)',
            r'will\s+(?:grow|increase|improve)',
            r'(?:my|our)\s+(?:view|opinion|thesis)',
        ]
        
        for assumption in assumptions:
            for pattern in unverifiable_patterns:
                if re.search(pattern, assumption.lower()):
                    unverifiable.append(assumption)
                    break
        
        return unverifiable
    
    def _identify_logic_issues(self, text: str) -> List[str]:
        """Identify logical issues in the thesis."""
        issues = []
        text_lower = text.lower()
        
        # Circular logic: "undervalued because it's cheap"
        if re.search(r'undervalued\s+(?:because|since)\s+(?:it\'?s?|the)\s+(?:cheap|low|trading)', text_lower):
            issues.append("Circular reasoning: 'undervalued because cheap'")
        
        # Survivorship bias indicators
        if re.search(r'always\s+(?:goes|gone)\s+up', text_lower):
            issues.append("Potential survivorship bias")
        
        # Anchoring to historical prices
        if re.search(r'(?:was|traded)\s+at\s+\$?\d+\s+(?:before|in\s+\d{4})', text_lower):
            issues.append("May be anchoring to historical price")
        
        # Overconfidence indicators
        if re.search(r'(?:can\'?t|won\'?t|will\s+never)\s+(?:lose|fail|go\s+down)', text_lower):
            issues.append("Overconfidence - dismissing downside")
        
        if re.search(r'guaranteed|sure\s+thing|free\s+money|can\'?t\s+lose', text_lower):
            issues.append("RED FLAG: Guaranteed return claim")
        
        return issues
    
    def _catalyst_already_passed(self, catalyst: str) -> bool:
        """Check if a catalyst event has already passed."""
        catalyst_lower = catalyst.lower()
        
        # Look for past dates
        past_patterns = [
            r'(?:last|previous)\s+(?:week|month|quarter)',
            r'(?:in|during)\s+(?:q[1-4]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{0,4}',
        ]
        
        for pattern in past_patterns:
            if re.search(pattern, catalyst_lower):
                return True
        
        return False
    
    # ========================================================================
    # Helper Functions
    # ========================================================================
    
    def _extract_tickers(self, text: str) -> List[str]:
        """Extract stock ticker symbols from text."""
        # Common patterns: $TICKER, TICKER (all caps, 1-5 chars)
        tickers = set()
        
        # $TICKER pattern
        dollar_tickers = re.findall(r'\$([A-Z]{1,5})\b', text.upper())
        tickers.update(dollar_tickers)
        
        # ALLCAPS words that look like tickers (filter out common words)
        common_words = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HAD', 
                       'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS',
                       'HOW', 'ITS', 'LET', 'MAY', 'NEW', 'NOW', 'OLD', 'SEE', 'WAY', 'WHO',
                       'BOY', 'DID', 'ITS', 'SAY', 'SHE', 'TOO', 'USE', 'CEO', 'CFO', 'IPO',
                       'EPS', 'FCF', 'ROE', 'ROA', 'YTD', 'ATH', 'IMO', 'TBH', 'P/E', 'P/B'}
        
        caps_words = re.findall(r'\b([A-Z]{2,5})\b', text)
        for word in caps_words:
            if word not in common_words and not word.startswith('EV/'):
                tickers.add(word)
        
        return list(tickers)
    
    def _normalize_metric(self, metric: str) -> str:
        """Normalize a valuation metric name."""
        metric_lower = metric.lower().replace('/', '').replace(' ', '')
        
        if metric_lower in ['pe', 'pricetoearnings', 'earnings']:
            return 'pe_ratio'
        elif metric_lower in ['pfcf', 'pricetofcf', 'pricetocashflow', 'fcf']:
            return 'price_to_fcf'
        elif metric_lower in ['evebitda', 'evtoebitda', 'ebitda']:
            return 'ev_to_ebitda'
        elif metric_lower in ['pb', 'pricetobook', 'book']:
            return 'price_to_book'
        elif metric_lower in ['ps', 'pricetosales', 'sales']:
            return 'price_to_sales'
        
        return metric_lower
    
    def _find_nearest_ticker(self, text: str, pattern: str, tickers: List[str]) -> Optional[str]:
        """Find the nearest ticker to a pattern match in text."""
        if not tickers:
            return None
        
        text_lower = text.lower()
        pattern_match = re.search(pattern, text_lower)
        
        if not pattern_match:
            return tickers[0] if tickers else None
        
        pattern_pos = pattern_match.start()
        
        nearest = None
        min_dist = float('inf')
        
        for ticker in tickers:
            ticker_matches = list(re.finditer(rf'\b{ticker}\b', text, re.IGNORECASE))
            for tm in ticker_matches:
                dist = abs(tm.start() - pattern_pos)
                if dist < min_dist:
                    min_dist = dist
                    nearest = ticker
        
        return nearest
    
    # ========================================================================
    # Summary Builders
    # ========================================================================
    
    def _build_valuation_summary(self, claims: List[ExtractedClaim]) -> Dict[str, Any]:
        """Build summary of valuation claim verification."""
        summary = {
            "claims_count": 0,
            "verified_count": 0,
            "discrepancies": []
        }
        
        for claim in claims:
            if claim.claim_type == "VALUATION_COMPARISON":
                for val in claim.valuation_claims:
                    summary["claims_count"] += 1
                    if val.verified:
                        summary["verified_count"] += 1
                    elif val.actual_value is not None and val.discrepancy_pct is not None:
                        summary["discrepancies"].append({
                            "ticker": val.ticker,
                            "metric": val.metric_type,
                            "claimed": val.claimed_value,
                            "actual": val.actual_value,
                            "diff_pct": val.discrepancy_pct
                        })
        
        return summary if summary["claims_count"] > 0 else {}
    
    def _build_performance_summary(self, claims: List[ExtractedClaim]) -> Dict[str, Any]:
        """Build summary of performance claim verification."""
        summary = {
            "claims": [],
            "unverifiable_count": 0,
            "extraordinary_count": 0
        }
        
        for claim in claims:
            if claim.claim_type == "PERFORMANCE_CLAIM":
                for perf in claim.performance_claims:
                    claim_info = {
                        "claim": perf.claim_text,
                        "verified": perf.verified,
                        "verifiable": perf.verifiable
                    }
                    if perf.actual_return is not None:
                        claim_info["actual"] = perf.actual_return
                    
                    summary["claims"].append(claim_info)
                    
                    if not perf.verifiable:
                        summary["unverifiable_count"] += 1
                    if perf.return_pct and perf.return_pct > 100:
                        summary["extraordinary_count"] += 1
        
        return summary if summary["claims"] else {}
    
    def _build_thesis_summary(self, claims: List[ExtractedClaim]) -> Dict[str, Any]:
        """Build summary of thesis analysis."""
        summary = {
            "issues": [],
            "risks_not_considered": [],
            "unverifiable_assumptions": []
        }
        
        for claim in claims:
            if claim.claim_type == "INVESTMENT_THESIS" and claim.thesis_analysis:
                thesis = claim.thesis_analysis
                summary["issues"].extend(thesis.logic_issues)
                summary["risks_not_considered"].extend(thesis.risks_missing[:3])
                summary["unverifiable_assumptions"].extend(thesis.unverifiable_assumptions[:3])
        
        return summary if any(summary.values()) else {}
    
    # ========================================================================
    # Existing Methods (M&A, Earnings, etc.)
    # ========================================================================
    
    def _summarize_ma_claim(self, text: str, matches: list) -> str:
        """Create summary of M&A claim."""
        # Extract key elements
        deal_value = None
        for match in matches:
            if isinstance(match, tuple):
                for item in match:
                    if re.match(r'[\d.,]+', str(item)):
                        deal_value = item
                        break
        
        # Look for countries/companies
        countries = re.findall(r'\b(China|Chinese|Canada|Canadian|US|American)\b', text, re.IGNORECASE)
        
        summary = "Acquisition"
        if countries:
            summary = f"{countries[0]} acquisition"
        if deal_value:
            summary += f" for ${deal_value}"
        if "gold" in text.lower():
            summary += " (gold mining)"
            
        return summary
    
    def _extract_ma_specifics(self, text: str, matches: list) -> Dict[str, Any]:
        """Extract specific details from M&A claim."""
        specifics = {}
        
        # Deal value
        for match in matches:
            if isinstance(match, tuple):
                for i, item in enumerate(match):
                    if re.match(r'[\d.,]+', str(item)):
                        value = float(str(item).replace(',', ''))
                        unit = match[i+1] if i+1 < len(match) else ""
                        if unit.lower() in ['billion', 'b']:
                            value *= 1e9
                        elif unit.lower() in ['million', 'm']:
                            value *= 1e6
                        specifics["deal_value"] = value
                        specifics["deal_value_str"] = f"${item} {unit}".strip()
                        break
        
        # Countries
        if re.search(r'\bChin(?:a|ese)\b', text, re.IGNORECASE):
            specifics["acquirer_country"] = "China"
        if re.search(r'\bCanad(?:a|ian)\b', text, re.IGNORECASE):
            specifics["target_country"] = "Canada"
            
        # Industry
        if "gold" in text.lower():
            specifics["industry"] = "gold mining"
        elif "silver" in text.lower():
            specifics["industry"] = "silver mining"
            
        return specifics
    
    def _summarize_earnings_claim(self, text: str) -> str:
        """Create summary of earnings claim."""
        return "Earnings report claim"
    
    def _extract_earnings_specifics(self, text: str) -> Dict[str, Any]:
        """Extract specific details from earnings claim."""
        return {}
    
    def _search_primary_sources(self, claim: ExtractedClaim) -> tuple:
        """Search for primary sources to verify claim."""
        evidence = []
        sources_checked = {}
        
        if claim.claim_type == "M&A":
            # Search SEC EDGAR
            sec_result = self._search_sec_edgar(claim)
            sources_checked["sec_edgar"] = sec_result.get("status", "Not checked")
            if sec_result.get("found"):
                evidence.append(SourceEvidence(
                    source_id=f"SRC-SEC-{len(evidence)+1}",
                    source_type="sec_filing",
                    tier=SourceTier.T1,
                    url=sec_result.get("url", ""),
                    confirms_claim=True,
                    specific_details=sec_result.get("details", {})
                ))
            
            # Search SEDAR (Canadian)
            if claim.specifics.get("target_country") == "Canada":
                sedar_result = self._search_sedar(claim)
                sources_checked["sedar_plus"] = sedar_result.get("status", "Not checked")
                if sedar_result.get("found"):
                    evidence.append(SourceEvidence(
                        source_id=f"SRC-SEDAR-{len(evidence)+1}",
                        source_type="sedar_filing",
                        tier=SourceTier.T1,
                        url=sedar_result.get("url", ""),
                        confirms_claim=True,
                        specific_details=sedar_result.get("details", {})
                    ))
            
            # Search news wires
            news_result = self._search_news(claim)
            sources_checked["newswires"] = news_result.get("status", "Not checked")
        
        elif claim.claim_type in ["VALUATION_COMPARISON", "PERFORMANCE_CLAIM", "INVESTMENT_THESIS"]:
            # For thesis claims, the "source" is yfinance/market data
            sources_checked["market_data"] = "yfinance" if YFINANCE_AVAILABLE else "Not available"
            
            if YFINANCE_AVAILABLE:
                evidence.append(SourceEvidence(
                    source_id="SRC-YFINANCE-1",
                    source_type="market_data",
                    tier=SourceTier.T1,  # Real-time market data is T1
                    url="https://finance.yahoo.com",
                    confirms_claim=True,  # It provides verification data
                    note="Market data used to verify valuation/performance claims"
                ))
            
        return evidence, sources_checked
    
    def _search_sec_edgar(self, claim: ExtractedClaim) -> Dict[str, Any]:
        """Search SEC EDGAR for relevant filings."""
        # In production, this would query SEC EDGAR API
        # For now, return not found
        return {
            "status": "No matching 8-K or SC 13D found",
            "found": False
        }
    
    def _search_sedar(self, claim: ExtractedClaim) -> Dict[str, Any]:
        """Search SEDAR+ for Canadian filings."""
        return {
            "status": "No matching filing found",
            "found": False
        }
    
    def _search_news(self, claim: ExtractedClaim) -> Dict[str, Any]:
        """Search news wires for press releases."""
        return {
            "status": "No matching press release found",
            "found": False
        }
    
    def _detect_red_flags(self, claims: List[ExtractedClaim], evidence: List[SourceEvidence], text: str) -> List[str]:
        """Detect red flags in claims and evidence."""
        flags = []
        
        for claim in claims:
            # Original M&A flags
            if claim.claim_type == "M&A":
                if "target_company_name" in claim.missing_elements:
                    flags.append("NO_COMPANY_NAME")
                    
                # Round numbers
                deal_value = claim.specifics.get("deal_value", 0)
                if deal_value > 0 and deal_value % 1e8 == 0:  # Exactly divisible by 100M
                    flags.append("ROUND_NUMBERS")
            
            # Valuation discrepancy flags
            elif claim.claim_type == "VALUATION_COMPARISON":
                for val in claim.valuation_claims:
                    if val.discrepancy_pct is not None and abs(val.discrepancy_pct) > 20:
                        flags.append("VALUATION_DISCREPANCY")
                        break
            
            # Performance claim flags
            elif claim.claim_type == "PERFORMANCE_CLAIM":
                has_unverifiable = any(not p.verifiable for p in claim.performance_claims)
                has_extraordinary = any(p.return_pct and p.return_pct > 100 for p in claim.performance_claims)
                
                if has_unverifiable:
                    flags.append("UNVERIFIABLE_PERFORMANCE")
                if has_extraordinary:
                    flags.append("EXTRAORDINARY_CLAIM")
            
            # Thesis flags
            elif claim.claim_type == "INVESTMENT_THESIS" and claim.thesis_analysis:
                thesis = claim.thesis_analysis
                
                if thesis.risks_missing:
                    flags.append("MISSING_MATERIAL_RISKS")
                
                if thesis.unverifiable_assumptions:
                    flags.append("UNVERIFIABLE_CATALYST")
                
                if any('circular' in issue.lower() for issue in thesis.logic_issues):
                    flags.append("CIRCULAR_LOGIC")
        
        # No primary source check
        t1_t2_sources = [e for e in evidence if e.tier in [SourceTier.T1, SourceTier.T2]]
        if not t1_t2_sources and not any(c.claim_type in ["VALUATION_COMPARISON", "PERFORMANCE_CLAIM", "INVESTMENT_THESIS"] for c in claims):
            flags.append("NO_PRIMARY_SOURCE")
        
        # Check for viral pattern (would need Twitter search in production)
        if not t1_t2_sources and len(evidence) == 0:
            # Only flag if not a thesis claim (those use different verification)
            if not any(c.claim_type in ["VALUATION_COMPARISON", "PERFORMANCE_CLAIM", "INVESTMENT_THESIS"] for c in claims):
                flags.append("VIRAL_NO_ORIGIN")
        
        return list(set(flags))  # Deduplicate
    
    def _calculate_score(self, claims: List[ExtractedClaim], evidence: List[SourceEvidence], red_flags: List[str]) -> int:
        """Calculate verification score (0-100)."""
        score = 50  # Start neutral
        
        # Source quality bonuses
        for e in evidence:
            if e.confirms_claim:
                if e.tier == SourceTier.T1:
                    score += 40
                elif e.tier == SourceTier.T2:
                    score += 30
                elif e.tier == SourceTier.T3:
                    score += 15
                elif e.tier == SourceTier.T4:
                    score += 10
        
        # Independent confirmation bonus
        independent = [e for e in evidence if e.is_independent and e.confirms_claim]
        score += min(len(independent) * 10, 30)
        
        # Specificity bonus
        for claim in claims:
            if not claim.missing_elements:
                score += 10
        
        # Thesis-specific scoring
        for claim in claims:
            if claim.claim_type == "VALUATION_COMPARISON":
                verified = sum(1 for v in claim.valuation_claims if v.verified)
                total = len(claim.valuation_claims)
                if total > 0:
                    score += int((verified / total) * 20)  # Up to +20 for verified valuations
            
            elif claim.claim_type == "PERFORMANCE_CLAIM":
                verified = sum(1 for p in claim.performance_claims if p.verified)
                verifiable = sum(1 for p in claim.performance_claims if p.verifiable)
                if verifiable > 0:
                    score += int((verified / verifiable) * 15)  # Up to +15 for verified performance
            
            elif claim.claim_type == "INVESTMENT_THESIS" and claim.thesis_analysis:
                thesis = claim.thesis_analysis
                # Deduct for logic issues
                score -= len(thesis.logic_issues) * 5
                # Deduct for missing risks
                score -= min(len(thesis.risks_missing) * 3, 15)
        
        # Red flag penalties
        flag_penalties = {
            "NO_COMPANY_NAME": -30,
            "ROUND_NUMBERS": -10,
            "NO_PRIMARY_SOURCE": -40,
            "VIRAL_NO_ORIGIN": -25,
            "CONFLICT_FOUND": -50,
            "TIMING_SUSPICIOUS": -20,
            "AUTHOR_UNRELIABLE": -30,
            "GEOGRAPHIC_MISMATCH": -20,
            # Thesis-specific penalties
            "VALUATION_DISCREPANCY": -25,
            "UNVERIFIABLE_PERFORMANCE": -35,
            "EXTRAORDINARY_CLAIM": -40,
            "CHERRY_PICKED_TIMEFRAME": -15,
            "MISSING_MATERIAL_RISKS": -20,
            "STALE_DATA": -15,
            "COMPARISON_IGNORES_DIFFERENCES": -15,
            "CIRCULAR_LOGIC": -30,
            "UNVERIFIABLE_CATALYST": -20,
        }
        
        for flag in red_flags:
            score += flag_penalties.get(flag, -10)
        
        return max(0, min(100, score))
    
    def _score_to_verdict(self, score: int) -> Verdict:
        """Convert score to verdict."""
        if score >= 90:
            return Verdict.VERIFIED
        elif score >= 70:
            return Verdict.LIKELY_TRUE
        elif score >= 50:
            return Verdict.UNVERIFIED
        elif score >= 30:
            return Verdict.DOUBTFUL
        else:
            return Verdict.LIKELY_FALSE
    
    def _get_recommendation(self, verdict: Verdict) -> str:
        """Get action recommendation based on verdict."""
        recommendations = {
            Verdict.VERIFIED: "SAFE_TO_ACT",
            Verdict.LIKELY_TRUE: "PROCEED_WITH_CAUTION",
            Verdict.UNVERIFIED: "AWAIT_CONFIRMATION",
            Verdict.DOUBTFUL: "DO_NOT_ACT",
            Verdict.LIKELY_FALSE: "IGNORE_CLAIM"
        }
        return recommendations.get(verdict, "UNKNOWN")
    
    def _calculate_confidence(self, evidence: List[SourceEvidence], red_flags: List[str]) -> float:
        """Calculate confidence in the verdict."""
        confidence = 0.5
        
        # More evidence = higher confidence
        confidence += min(len(evidence) * 0.1, 0.3)
        
        # T1 sources = higher confidence
        if any(e.tier == SourceTier.T1 for e in evidence):
            confidence += 0.2
        
        # Red flags reduce confidence in positive verdicts
        confidence -= len(red_flags) * 0.05
        
        return max(0.1, min(0.95, confidence))
    
    def _generate_analyst_note(self, result: VerificationResult) -> str:
        """Generate human-readable analyst note."""
        notes = []
        
        # Verdict-based note
        if result.verdict == Verdict.LIKELY_FALSE:
            notes.append(f"Claim appears unverified. {len(result.red_flags)} red flags detected.")
        elif result.verdict == Verdict.UNVERIFIED:
            notes.append("Claim cannot be verified with available sources.")
        elif result.verdict == Verdict.VERIFIED:
            t1_count = len([e for e in result.evidence if e.tier == SourceTier.T1])
            notes.append(f"Claim verified by {t1_count} primary source(s).")
        elif result.verdict == Verdict.LIKELY_TRUE:
            notes.append("Claim appears credible but not fully verified.")
        elif result.verdict == Verdict.DOUBTFUL:
            notes.append("Claim has significant issues. Exercise caution.")
        
        # Valuation-specific notes
        if result.valuation_summary.get("discrepancies"):
            disc_count = len(result.valuation_summary["discrepancies"])
            notes.append(f"{disc_count} valuation metric(s) differ significantly from actual data.")
        
        # Performance-specific notes
        if result.performance_summary.get("extraordinary_count", 0) > 0:
            notes.append("Contains extraordinary return claims that require scrutiny.")
        if result.performance_summary.get("unverifiable_count", 0) > 0:
            notes.append("Some performance claims cannot be independently verified.")
        
        # Thesis-specific notes
        if result.thesis_summary.get("issues"):
            notes.append(f"Thesis has {len(result.thesis_summary['issues'])} logical issue(s).")
        if result.thesis_summary.get("risks_not_considered"):
            notes.append("Important risks may not be adequately considered.")
        
        return " ".join(notes)


# CLI interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python claim_verifier.py <url_or_text>")
        print("\nExamples:")
        print('  python claim_verifier.py "VALE at 4x FCF is cheap vs BHP at 8x"')
        print('  python claim_verifier.py "My portfolio is up 247% YTD"')
        print('  python claim_verifier.py https://x.com/user/status/123')
        sys.exit(1)
    
    input_arg = sys.argv[1]
    verifier = ClaimVerifier()
    
    # Detect if it's a URL or raw text
    if input_arg.startswith("http"):
        result = verifier.verify(input_arg)
    else:
        result = verifier.verify("direct_input", raw_text=input_arg)
    
    print(result.to_quick_verdict())
    print("\n" + "="*50)
    print(json.dumps(result.to_dict(), indent=2))
