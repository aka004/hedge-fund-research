#!/usr/bin/env python3
"""
Test suite for ClaimVerifier - including thesis-style claim verification.
"""

import sys
from datetime import datetime

# Import the verifier
from claim_verifier import ClaimVerifier, Verdict


def test_valuation_claims():
    """Test valuation comparison claim extraction and verification."""
    print("\n" + "="*60)
    print("TEST: Valuation Claims")
    print("="*60)
    
    verifier = ClaimVerifier()
    
    # Test case 1: Simple valuation comparison
    text1 = "VALE at 4x FCF is ridiculously cheap compared to BHP at 8x"
    result1 = verifier.verify("test://valuation1", raw_text=text1)
    
    print(f"\n📊 Input: {text1}")
    print(f"Claims extracted: {len(result1.claims)}")
    print(f"Verdict: {result1.verdict.value} (Score: {result1.score})")
    
    for claim in result1.claims:
        if claim.claim_type == "VALUATION_COMPARISON":
            print(f"  Valuation claims found: {len(claim.valuation_claims)}")
            for vc in claim.valuation_claims:
                status = "✓" if vc.verified else "✗"
                actual = f" (actual: {vc.actual_value:.1f}x)" if vc.actual_value else ""
                print(f"    {status} {vc.ticker} {vc.metric_type}: {vc.claimed_value}x{actual}")
    
    # Test case 2: Multiple metrics
    text2 = "AAPL P/E of 28 and P/FCF at 25x - still expensive vs GOOG at 22x PE"
    result2 = verifier.verify("test://valuation2", raw_text=text2)
    
    print(f"\n📊 Input: {text2}")
    print(f"Verdict: {result2.verdict.value} (Score: {result2.score})")
    print(f"Red flags: {result2.red_flags}")
    
    # Test case 3: EV/EBITDA
    text3 = "META trading at just 12x EV/EBITDA while peers average 18x"
    result3 = verifier.verify("test://valuation3", raw_text=text3)
    
    print(f"\n📊 Input: {text3}")
    print(f"Verdict: {result3.verdict.value} (Score: {result3.score})")
    
    return True


def test_performance_claims():
    """Test performance claim extraction and verification."""
    print("\n" + "="*60)
    print("TEST: Performance Claims")
    print("="*60)
    
    verifier = ClaimVerifier()
    
    # Test case 1: Unverifiable portfolio claim
    text1 = "My portfolio is up 247% this year 🚀"
    result1 = verifier.verify("test://perf1", raw_text=text1)
    
    print(f"\n📈 Input: {text1}")
    print(f"Verdict: {result1.verdict.value} (Score: {result1.score})")
    print(f"Red flags: {result1.red_flags}")
    assert "UNVERIFIABLE_PERFORMANCE" in result1.red_flags or "EXTRAORDINARY_CLAIM" in result1.red_flags, "Should flag unverifiable/extraordinary claim"
    print("✓ Correctly flagged extraordinary unverifiable claim")
    
    # Test case 2: Verifiable ticker return
    text2 = "NVDA up 180% YTD. Insane."
    result2 = verifier.verify("test://perf2", raw_text=text2)
    
    print(f"\n📈 Input: {text2}")
    print(f"Verdict: {result2.verdict.value} (Score: {result2.score})")
    
    for claim in result2.claims:
        if claim.claim_type == "PERFORMANCE_CLAIM":
            for pc in claim.performance_claims:
                status = "VERIFIED" if pc.verified else ("MISMATCH" if pc.actual_return else "CHECKING")
                print(f"  {pc.claim_text}: {status}")
                if pc.actual_return:
                    print(f"    Actual return: {pc.actual_return:.1f}%")
    
    # Test case 3: Relative performance claim
    text3 = "I beat the S&P by 50% this year"
    result3 = verifier.verify("test://perf3", raw_text=text3)
    
    print(f"\n📈 Input: {text3}")
    print(f"Verdict: {result3.verdict.value} (Score: {result3.score})")
    print(f"Red flags: {result3.red_flags}")
    
    return True


def test_thesis_analysis():
    """Test investment thesis logic analysis."""
    print("\n" + "="*60)
    print("TEST: Investment Thesis Analysis")
    print("="*60)
    
    verifier = ClaimVerifier()
    
    # Test case 1: Good thesis with some issues
    text1 = """
    Long $BABA thesis:
    - Trading at 10x earnings vs US tech at 25x
    - Catalyst: Jack Ma back, China stimulus
    - Cloud growing 30% YoY
    - Undervalued because it's cheap
    
    This is a can't-lose trade IMO.
    """
    result1 = verifier.verify("test://thesis1", raw_text=text1)
    
    print(f"\n📝 Input: {text1[:100]}...")
    print(f"Verdict: {result1.verdict.value} (Score: {result1.score})")
    print(f"Red flags: {result1.red_flags}")
    
    for claim in result1.claims:
        if claim.claim_type == "INVESTMENT_THESIS" and claim.thesis_analysis:
            thesis = claim.thesis_analysis
            print(f"\n  Thesis Summary: {thesis.thesis_summary}")
            print(f"  Tickers: {thesis.tickers}")
            print(f"  Catalysts: {thesis.catalysts}")
            print(f"  Risks mentioned: {thesis.risks_mentioned}")
            print(f"  Risks missing: {thesis.risks_missing}")
            print(f"  Logic issues: {thesis.logic_issues}")
    
    # Should catch "undervalued because cheap" circular logic and "can't lose" overconfidence
    assert any("circular" in flag.lower() or "CIRCULAR" in flag for flag in result1.red_flags + (result1.thesis_summary.get("issues", []))), "Should detect circular logic"
    print("✓ Correctly identified thesis issues")
    
    # Test case 2: Mining thesis with missing risks
    text2 = """
    Bullish on VALE:
    - 4x FCF, massive dividend yield
    - Iron ore prices recovering
    - Expecting 50% upside to $18 target
    
    Easy money here.
    """
    result2 = verifier.verify("test://thesis2", raw_text=text2)
    
    print(f"\n📝 Input: {text2[:100]}...")
    print(f"Verdict: {result2.verdict.value} (Score: {result2.score})")
    print(f"Thesis summary: {result2.thesis_summary}")
    
    # Should flag missing mining-specific risks
    risks_missing = result2.thesis_summary.get("risks_not_considered", [])
    print(f"  Risks not considered: {risks_missing}")
    
    return True


def test_existing_functionality():
    """Ensure existing M&A/Earnings verification still works."""
    print("\n" + "="*60)
    print("TEST: Existing Functionality (M&A, Earnings)")
    print("="*60)
    
    verifier = ClaimVerifier()
    
    # Test M&A claim
    text1 = "China acquired Canadian gold miner for $2.5 billion"
    result1 = verifier.verify("test://ma1", raw_text=text1)
    
    print(f"\n🏢 Input: {text1}")
    print(f"Claims: {[c.claim_type for c in result1.claims]}")
    print(f"Verdict: {result1.verdict.value} (Score: {result1.score})")
    
    ma_claims = [c for c in result1.claims if c.claim_type == "M&A"]
    assert len(ma_claims) > 0, "Should extract M&A claim"
    print("✓ M&A claim extraction still works")
    
    # Test Earnings claim
    text2 = "AAPL reported earnings of $1.52 EPS, beating estimates"
    result2 = verifier.verify("test://earnings1", raw_text=text2)
    
    print(f"\n💰 Input: {text2}")
    print(f"Claims: {[c.claim_type for c in result2.claims]}")
    print(f"Verdict: {result2.verdict.value}")
    
    earnings_claims = [c for c in result2.claims if c.claim_type == "Earnings"]
    assert len(earnings_claims) > 0, "Should extract Earnings claim"
    print("✓ Earnings claim extraction still works")
    
    return True


def test_quick_verdict_format():
    """Test the quick verdict output format."""
    print("\n" + "="*60)
    print("TEST: Quick Verdict Format")
    print("="*60)
    
    verifier = ClaimVerifier()
    
    text = """
    Thread on $VALE:
    
    Trading at 4x FCF (actual is probably 6x lol)
    My portfolio up 300% thanks to this one
    
    Long thesis: undervalued Brazilian miner
    Catalyst: China infrastructure spending
    """
    
    result = verifier.verify("test://format", raw_text=text)
    
    print("\n" + result.to_quick_verdict())
    print("\n📋 Full result dict:")
    import json
    print(json.dumps(result.to_dict(), indent=2))
    
    return True


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print("\n" + "="*60)
    print("TEST: Edge Cases")
    print("="*60)
    
    verifier = ClaimVerifier()
    
    # Empty text
    result1 = verifier.verify("test://empty", raw_text="")
    print(f"\n🔲 Empty text: {result1.verdict.value}")
    assert result1.verdict == Verdict.UNVERIFIED, "Empty text should be unverified"
    
    # No claims
    result2 = verifier.verify("test://noclaims", raw_text="Just a random tweet about nothing")
    print(f"🔲 No claims: {result2.verdict.value}")
    
    # Mixed claims
    text3 = "AAPL P/E at 28x, I'm up 50% on my position. China acquired a gold miner for $3B."
    result3 = verifier.verify("test://mixed", raw_text=text3)
    print(f"🔲 Mixed claims: {[c.claim_type for c in result3.claims]}")
    print(f"   Should have multiple claim types")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("CLAIM VERIFIER TEST SUITE")
    print(f"Run at: {datetime.now().isoformat()}")
    print("="*60)
    
    tests = [
        ("Existing Functionality", test_existing_functionality),
        ("Valuation Claims", test_valuation_claims),
        ("Performance Claims", test_performance_claims),
        ("Thesis Analysis", test_thesis_analysis),
        ("Quick Verdict Format", test_quick_verdict_format),
        ("Edge Cases", test_edge_cases),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, "PASS" if passed else "FAIL"))
        except Exception as e:
            print(f"\n❌ ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, "ERROR"))
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    for name, status in results:
        emoji = "✅" if status == "PASS" else "❌"
        print(f"  {emoji} {name}: {status}")
    
    passed = sum(1 for _, s in results if s == "PASS")
    print(f"\n{passed}/{len(results)} tests passed")
    
    return all(s == "PASS" for _, s in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
