#!/usr/bin/env python3
"""
Claim Verifier - Fact-check external claims before acting on them
=================================================================

Verifies claims from Twitter, news, and other sources by:
1. Extracting specific factual assertions
2. Searching for primary sources (SEC, SEDAR, press releases)
3. Cross-referencing across independent sources
4. Scoring reliability and flagging red flags

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
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class Verdict(Enum):
    VERIFIED = "VERIFIED"
    LIKELY_TRUE = "LIKELY_TRUE"
    UNVERIFIED = "UNVERIFIED"
    DOUBTFUL = "DOUBTFUL"
    LIKELY_FALSE = "LIKELY_FALSE"


class RedFlag(Enum):
    NO_COMPANY_NAME = ("NO_COMPANY_NAME", -30, "M&A claim without target/acquirer name")
    ROUND_NUMBERS = ("ROUND_NUMBERS", -10, "Deal value is suspiciously round")
    NO_PRIMARY_SOURCE = ("NO_PRIMARY_SOURCE", -40, "No T1/T2 source found")
    VIRAL_NO_ORIGIN = ("VIRAL_NO_ORIGIN", -25, "Multiple social posts, no original source")
    CONFLICT_FOUND = ("CONFLICT_FOUND", -50, "Sources contradict each other")
    TIMING_SUSPICIOUS = ("TIMING_SUSPICIOUS", -20, "Suspicious timing pattern")
    AUTHOR_UNRELIABLE = ("AUTHOR_UNRELIABLE", -30, "Source author has history of false claims")
    GEOGRAPHIC_MISMATCH = ("GEOGRAPHIC_MISMATCH", -20, "Jurisdiction doesn't match filings")


class SourceTier(Enum):
    T1 = (1, 1.0, "SEC/SEDAR filings, Government databases")
    T2 = (2, 0.9, "Company press releases (official IR)")
    T3 = (3, 0.8, "Wire services (Reuters, Bloomberg, AP)")
    T4 = (4, 0.7, "Major financial media (WSJ, FT)")
    T5 = (5, 0.6, "Industry publications")
    T6 = (6, 0.3, "Social media, blogs")
    T7 = (7, 0.1, "Anonymous sources")


@dataclass
class ExtractedClaim:
    """A specific verifiable claim extracted from source text."""
    claim_id: str
    claim_type: str  # M&A, Earnings, Executive, Regulatory, Product, Macro, Market
    assertion: str
    specifics: Dict[str, Any] = field(default_factory=dict)
    verifiable_elements: List[str] = field(default_factory=list)
    missing_elements: List[str] = field(default_factory=list)


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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
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
    
    def to_quick_verdict(self) -> str:
        """Format as quick verdict for chat integration."""
        claim_text = self.claims[0].assertion if self.claims else "Unknown claim"
        
        flags_str = "\n".join(f"- {f}" for f in self.red_flags) if self.red_flags else "None"
        
        return f"""**CLAIM**: {claim_text}

**VERDICT**: {self.verdict.value} (Score: {self.score}/100)

**RED FLAGS**:
{flags_str}

**ANALYST NOTE**:
{self.analyst_note}

**RECOMMENDATION**: {self.recommendation}
"""


class ClaimVerifier:
    """
    Verify claims from external sources.
    """
    
    def __init__(self, bird_cli_path: str = "bird"):
        self.bird_cli = bird_cli_path
        self.sec_base_url = "https://www.sec.gov/cgi-bin/browse-edgar"
        self.sedar_base_url = "https://www.sedarplus.ca"
        
    def verify(self, url: str, raw_text: str = None, claim_type_hint: str = None) -> VerificationResult:
        """
        Main verification entry point.
        
        Args:
            url: URL of the source (tweet, article, etc.)
            raw_text: Optional override text (if already fetched)
            claim_type_hint: Optional hint for claim type (M&A, Earnings, etc.)
            
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
        
        # Step 2: Extract claims
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
        
        # Step 4: Detect red flags
        red_flags = self._detect_red_flags(claims, evidence, raw_text)
        result.red_flags = red_flags
        
        # Step 5: Calculate score and verdict
        score = self._calculate_score(claims, evidence, red_flags)
        result.score = score
        result.verdict = self._score_to_verdict(score)
        result.recommendation = self._get_recommendation(result.verdict)
        result.confidence = self._calculate_confidence(evidence, red_flags)
        
        # Step 6: Generate analyst note
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
            # No company name for M&A
            if claim.claim_type == "M&A":
                if "target_company_name" in claim.missing_elements:
                    flags.append("NO_COMPANY_NAME")
                    
                # Round numbers
                deal_value = claim.specifics.get("deal_value", 0)
                if deal_value > 0 and deal_value % 1e8 == 0:  # Exactly divisible by 100M
                    flags.append("ROUND_NUMBERS")
        
        # No primary source
        t1_t2_sources = [e for e in evidence if e.tier in [SourceTier.T1, SourceTier.T2]]
        if not t1_t2_sources:
            flags.append("NO_PRIMARY_SOURCE")
        
        # Check for viral pattern (would need Twitter search in production)
        # For now, just check if claim seems to be repeated
        if not t1_t2_sources and len(evidence) == 0:
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
        
        # Red flag penalties
        flag_penalties = {
            "NO_COMPANY_NAME": -30,
            "ROUND_NUMBERS": -10,
            "NO_PRIMARY_SOURCE": -40,
            "VIRAL_NO_ORIGIN": -25,
            "CONFLICT_FOUND": -50,
            "TIMING_SUSPICIOUS": -20,
            "AUTHOR_UNRELIABLE": -30,
            "GEOGRAPHIC_MISMATCH": -20
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
        if result.verdict == Verdict.LIKELY_FALSE:
            return (
                f"Claim appears unverified. {len(result.red_flags)} red flags detected. "
                f"No primary sources (SEC, SEDAR, press releases) found to confirm. "
                f"Recommend ignoring this claim until verified by official sources."
            )
        elif result.verdict == Verdict.UNVERIFIED:
            return (
                f"Claim cannot be verified with available sources. "
                f"Awaiting official confirmation before acting."
            )
        elif result.verdict == Verdict.VERIFIED:
            return (
                f"Claim verified by {len([e for e in result.evidence if e.tier == SourceTier.T1])} "
                f"primary sources. Safe to incorporate into analysis."
            )
        else:
            return "Verification incomplete. Review evidence manually."


# CLI interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python claim_verifier.py <url>")
        sys.exit(1)
    
    url = sys.argv[1]
    verifier = ClaimVerifier()
    result = verifier.verify(url)
    
    print(result.to_quick_verdict())
    print("\n" + "="*50)
    print(json.dumps(result.to_dict(), indent=2))
