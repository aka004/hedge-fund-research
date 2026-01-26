#!/usr/bin/env python3
"""Generate Obsidian reports from existing data.

This script allows manual generation of Obsidian-formatted reports from:
- Alpha research results
- Backtest results
- Daily notes

Usage:
    # Generate research summary from latest results
    python scripts/generate_obsidian_report.py --type research

    # Generate research summary for specific run
    python scripts/generate_obsidian_report.py --type research --run-id 20250125_120000

    # Generate daily note
    python scripts/generate_obsidian_report.py --type daily --date 2025-01-25
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from analysis.obsidian_reports import (
    generate_daily_note_obsidian,
    generate_research_summary_obsidian,
    save_obsidian_note,
)
from config import RESEARCH_PATH


def generate_research_report(run_id: str | None = None) -> Path:
    """Generate Obsidian report from research results.
    
    Args:
        run_id: Optional run ID, if None uses latest
        
    Returns:
        Path to saved Obsidian note
    """
    results_file = RESEARCH_PATH / "alpha_research_results.csv"
    
    if not results_file.exists():
        print(f"Error: Results file not found at {results_file}")
        print("Run alpha_research.py first to generate results.")
        sys.exit(1)
    
    df = pd.read_csv(results_file)
    
    if df.empty:
        print("Error: No results found in CSV file.")
        sys.exit(1)
    
    # Determine run_id
    if run_id is None:
        # Use most recent run_id
        if "run_id" in df.columns:
            run_id = df["run_id"].iloc[-1]
        else:
            # Generate from timestamp
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Filter to specific run if specified
    if "run_id" in df.columns:
        df_filtered = df[df["run_id"] == run_id]
        if df_filtered.empty:
            print(f"Warning: No results found for run_id {run_id}")
            print(f"Available run_ids: {df['run_id'].unique()}")
            # Use all results instead
            df_filtered = df
    else:
        df_filtered = df
    
    # Convert to list of dicts
    results = df_filtered.to_dict("records")
    
    # Generate Obsidian content
    obsidian_content = generate_research_summary_obsidian(
        results,
        run_id,
    )
    
    # Save to Obsidian vault
    obsidian_path = save_obsidian_note(
        obsidian_content,
        f"{run_id}-summary.md",
        subfolder="Research/Alpha-Research",
    )
    
    print(f"✓ Generated Obsidian research report: {obsidian_path}")
    return obsidian_path


def generate_daily_report(note_date: date | None = None) -> Path:
    """Generate Obsidian daily note.
    
    Args:
        note_date: Date for the note (defaults to today)
        
    Returns:
        Path to saved Obsidian note
    """
    if note_date is None:
        note_date = date.today()
    
    # Generate daily note content
    obsidian_content = generate_daily_note_obsidian(
        date=note_date,
        summary=None,
        tasks=None,
        notes=None,
    )
    
    # Save to Obsidian vault
    filename = f"{note_date.strftime('%Y-%m-%d')}.md"
    obsidian_path = save_obsidian_note(
        obsidian_content,
        filename,
        subfolder="Daily-Notes",
    )
    
    print(f"✓ Generated Obsidian daily note: {obsidian_path}")
    return obsidian_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Obsidian reports from existing data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--type",
        type=str,
        required=True,
        choices=["research", "daily"],
        help="Type of report to generate",
    )
    
    parser.add_argument(
        "--run-id",
        type=str,
        help="Run ID for research reports (default: latest)",
    )
    
    parser.add_argument(
        "--date",
        type=str,
        help="Date for daily notes (YYYY-MM-DD, default: today)",
    )
    
    args = parser.parse_args()
    
    if args.type == "research":
        generate_research_report(run_id=args.run_id)
    elif args.type == "daily":
        note_date = None
        if args.date:
            note_date = date.fromisoformat(args.date)
        generate_daily_report(note_date=note_date)
    else:
        print(f"Error: Unknown report type: {args.type}")
        sys.exit(1)


if __name__ == "__main__":
    main()
