#!/usr/bin/env python3
"""
Test research orchestrator with a single company.

Usage:
    python scripts/test_research.py AAPL "Apple Inc."
    python scripts/test_research.py MSFT "Microsoft Corporation" --skip-db-check
    python scripts/test_research.py --help
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import subprocess
import os

from config import RESEARCH_DB_PATH, RESEARCH_OUTPUT_PATH, RESEARCH_FEEDBACK_PATH


def check_prerequisites():
    """Check that all prerequisites are met."""
    issues = []
    
    # Check if anthropic is installed
    try:
        import anthropic
    except ImportError:
        issues.append("❌ anthropic package not installed")
        issues.append("   Fix: pip install anthropic")
    
    # Check if rich is installed
    try:
        import rich
    except ImportError:
        issues.append("⚠️  rich package not installed (optional, for better output)")
        issues.append("   Fix: pip install rich")
    
    # Check if API key is set
    if not os.getenv("ANTHROPIC_API_KEY"):
        issues.append("❌ ANTHROPIC_API_KEY not set in .env file")
        issues.append("   Get your key from https://console.anthropic.com/")
        issues.append("   Then add to .env: ANTHROPIC_API_KEY=sk-ant-...")
    
    # Check if database exists
    if not RESEARCH_DB_PATH.exists():
        issues.append(f"⚠️  Research database not found at {RESEARCH_DB_PATH}")
        issues.append("   Run: python scripts/setup_research_db.py --ticker AAPL --years 7")
    
    if issues:
        print("\n" + "=" * 60)
        print("PREREQUISITES CHECK")
        print("=" * 60)
        for issue in issues:
            print(issue)
        print("=" * 60 + "\n")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Test research orchestrator on a company",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_research.py AAPL "Apple Inc."
  python scripts/test_research.py MSFT "Microsoft Corporation" --skip-db-check
  python scripts/test_research.py GOOGL "Alphabet Inc." --output-dir ./custom_output

Environment:
  ANTHROPIC_API_KEY must be set in .env file
  Database must be initialized (run setup_research_db.py first)
        """
    )
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("company_name", help="Company name")
    parser.add_argument(
        "--skip-db-check", 
        action="store_true", 
        help="Skip database availability check"
    )
    parser.add_argument(
        "--output-dir",
        help="Custom output directory (default: ./outputs/research)"
    )
    parser.add_argument(
        "--skip-prereq-check",
        action="store_true",
        help="Skip prerequisites check"
    )
    
    args = parser.parse_args()
    
    # Check prerequisites
    if not args.skip_prereq_check:
        if not check_prerequisites():
            print("Fix the issues above and try again.")
            print("Or use --skip-prereq-check to bypass this check.")
            sys.exit(1)
    
    print("\n" + "=" * 60)
    print("RESEARCH ORCHESTRATOR TEST")
    print("=" * 60)
    print(f"Ticker: {args.ticker}")
    print(f"Company: {args.company_name}")
    print(f"Database: {RESEARCH_DB_PATH}")
    print(f"Output: {args.output_dir or RESEARCH_OUTPUT_PATH}")
    print(f"Feedback: {RESEARCH_FEEDBACK_PATH}")
    print("=" * 60 + "\n")
    
    # Path to orchestrator
    orchestrator = Path(__file__).parent.parent / "research" / "orchestrator.py"
    
    # Build command
    cmd = ["python", str(orchestrator), args.ticker, args.company_name]
    
    if args.skip_db_check:
        cmd.append("--skip-db-check")
    
    if args.output_dir:
        cmd.extend(["--output-dir", args.output_dir])
    
    print(f"Running: {' '.join(cmd)}\n")
    
    # Run orchestrator
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("✅ RESEARCH SESSION COMPLETE")
        print("=" * 60)
        print(f"\nOutputs saved to:")
        print(f"  {args.output_dir or RESEARCH_OUTPUT_PATH}/")
        print(f"\nView the final memo:")
        print(f"  cat {args.output_dir or RESEARCH_OUTPUT_PATH}/{args.ticker}_*/final_memo.md")
        print(f"\nView session feedback:")
        print(f"  cat {args.output_dir or RESEARCH_OUTPUT_PATH}/{args.ticker}_*/session_feedback.json | jq .")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print("❌ RESEARCH SESSION FAILED")
        print("=" * 60)
        print("\nCheck the error messages above for details.")
        print("=" * 60 + "\n")
    
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
