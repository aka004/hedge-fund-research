#!/usr/bin/env python3
"""
Multi-Agent Alpha Testing System

Entry point for the multi-agent orchestration system.

Usage:
    # Test data availability
    python scripts/run_agents.py --test-data
    
    # Run full alpha workflow
    python scripts/run_agents.py --run-alpha
    
    # Verbose mode
    python scripts/run_agents.py --run-alpha --verbose
    
    # Custom symbols
    python scripts/run_agents.py --test-data --symbols AAPL MSFT GOOGL
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator import Orchestrator
from data.storage.universe import SP500_SYMBOLS


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Quiet down noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Alpha Testing System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Quick data test (5 symbols)
    python scripts/run_agents.py --test-data --quick
    
    # Full universe data test
    python scripts/run_agents.py --test-data
    
    # Run alpha workflow with logging
    python scripts/run_agents.py --run-alpha --verbose
        """,
    )
    
    # Mode selection
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--test-data",
        action="store_true",
        help="Test if agents can fetch all required data",
    )
    mode.add_argument(
        "--run-alpha",
        action="store_true",
        help="Run full alpha testing workflow",
    )
    
    # Options
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to test (default: S&P 500)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: test only 5 symbols",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Max alpha retry iterations (default: 3)",
    )
    
    return parser.parse_args()


def run_data_test(orchestrator: Orchestrator, symbols: list[str]) -> int:
    """Run data availability test."""
    print("\n" + "=" * 60)
    print("DATA AVAILABILITY TEST")
    print("=" * 60)
    print(f"Testing {len(symbols)} symbols...")
    
    result = orchestrator.run_data_test(symbols)
    
    print("\n" + "-" * 60)
    print(f"Status: {result['status'].upper()}")
    print(f"Symbols tested: {result['symbols_tested']}")
    print(f"Symbols OK: {result['symbols_ok']}")
    print(f"Symbols failed: {len(result['symbols_failed'])}")
    
    if result['symbols_failed']:
        print("\nFailed symbols:")
        for sym in result['symbols_failed'][:10]:
            print(f"  - {sym}")
        if len(result['symbols_failed']) > 10:
            print(f"  ... and {len(result['symbols_failed']) - 10} more")
    
    if result['issues']:
        print("\nIssues found:")
        for issue in result['issues'][:5]:
            print(f"  - {issue}")
    
    print("=" * 60)
    
    return 0 if result['status'] == 'pass' else 1


def run_alpha_workflow(
    orchestrator: Orchestrator,
    symbols: list[str],
    max_iterations: int,
) -> int:
    """Run full alpha testing workflow."""
    print("\n" + "=" * 60)
    print("ALPHA TESTING WORKFLOW")
    print("=" * 60)
    print(f"Universe: {len(symbols)} symbols")
    print(f"Max iterations: {max_iterations}")
    print("-" * 60)
    
    result = orchestrator.run_alpha_workflow(
        symbols=symbols,
        max_iterations=max_iterations,
    )
    
    # Print summary
    orchestrator.print_summary()
    
    print("\n" + "-" * 60)
    print(f"Final Status: {result['status'].upper()}")
    
    if result['status'] == 'success':
        print(f"PSR: {result.get('psr', 'N/A')}")
        print(f"Sharpe: {result.get('sharpe', 'N/A')}")
        print("✅ Alpha validated successfully!")
        return 0
    else:
        print(f"Message: {result.get('message', 'Unknown')}")
        
        # Check for pending reviews
        pending = orchestrator.get_pending_reviews()
        if pending:
            print(f"\n⚠️ {len(pending)} items pending human review:")
            for event in pending:
                print(f"  - {event.payload.get('proposal', event.payload)}")
        
        return 1


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Determine symbols
    if args.symbols:
        symbols = args.symbols
    elif args.quick:
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    else:
        symbols = SP500_SYMBOLS
    
    # Create orchestrator
    orchestrator = Orchestrator(verbose=args.verbose)
    
    try:
        if args.test_data:
            return run_data_test(orchestrator, symbols)
        elif args.run_alpha:
            return run_alpha_workflow(orchestrator, symbols, args.max_iterations)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        logging.exception(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
