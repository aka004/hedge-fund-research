#!/usr/bin/env python3
"""Create a comprehensive project report for hedge-fund-research.

Generates an Obsidian-formatted project overview report.
"""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.obsidian_reports import generate_obsidian_frontmatter, save_obsidian_note
from config import OBSIDIAN_PROJECT_PATH, STORAGE_PATH
from data.storage.parquet import ParquetStorage


def create_project_report() -> Path:
    """Create a comprehensive project report."""
    
    # Get project stats
    storage = ParquetStorage(STORAGE_PATH)
    price_symbols = storage.list_symbols("prices")
    fundamental_symbols = storage.list_symbols("fundamentals")
    sentiment_symbols = storage.list_symbols("sentiment")
    
    # Generate frontmatter
    frontmatter = generate_obsidian_frontmatter(
        title="Hedge Fund Research System - Project Overview",
        report_type="project",
        created=datetime.now(),
        tags=["project/hedge-fund-research", "type/project", "status/active"],
        metadata={
            "project": "hedge-fund-research",
            "version": "1.0",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
        },
    )
    
    # Generate report content
    lines = [
        frontmatter,
        "",
        "# Hedge Fund Research System - Project Overview",
        "",
        f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Project Description",
        "",
        "A lean, cost-effective EOD (End-of-Day) equities backtesting system for strategy research.",
        "The system focuses on momentum + value + social sentiment strategies for the S&P 500 universe.",
        "",
        "## Strategy Overview",
        "",
        "```",
        "Universe (S&P 500)",
        "    |",
        "    v",
        "Momentum Screen (12-1 month returns, price > 200 MA)",
        "    |",
        "    v",
        "Value Filter (P/E < 50, positive earnings, revenue growth)",
        "    |",
        "    v",
        "Social Signal (StockTwits attention + sentiment)",
        "    |",
        "    v",
        "Ranking & Selection (top 10-20 stocks)",
        "```",
        "",
        "## Current Status",
        "",
        "### Data Storage",
        f"- **Location**: `{STORAGE_PATH}`",
        f"- **Price Data**: {len(price_symbols)} symbols cached",
        f"- **Fundamental Data**: {len(fundamental_symbols)} symbols",
        f"- **Sentiment Data**: {len(sentiment_symbols)} symbols",
        "",
        "### Configuration",
        f"- **Database**: External drive (Data_2026)",
        f"- **Obsidian Notes**: iCloud Drive (syncs across devices)",
        "",
        "## Key Features",
        "",
        "### 1. Data Pipeline",
        "- **Yahoo Finance**: Free price and fundamental data",
        "- **StockTwits**: Social sentiment data",
        "- **Parquet Storage**: Efficient columnar format",
        "- **DuckDB**: Fast SQL queries over Parquet",
        "",
        "### 2. Strategy Signals",
        "- **Momentum Signal**: 12-1 month returns with moving average filter",
        "- **Value Signal**: P/E ratios, earnings quality",
        "- **Social Signal**: StockTwits sentiment and attention",
        "- **Signal Combiner**: Weighted combination of signals",
        "",
        "### 3. Backtesting Engine",
        "- **Walk-Forward Validation**: Train/test splits with purging",
        "- **Transaction Costs**: Models slippage and commissions",
        "- **Performance Metrics**: Sharpe, Sortino, Calmar ratios, drawdowns",
        "",
        "### 4. Alpha Research Loop",
        "- **Parameter Sweeps**: Automated exploration of strategy space",
        "- **Results Logging**: CSV and Obsidian reports",
        "- **Resume Capability**: Skip already-tested configurations",
        "",
        "### 5. Obsidian Integration",
        "- **Research Summaries**: Auto-generated from alpha research",
        "- **Backtest Reports**: Performance analysis in Obsidian format",
        "- **Daily Notes**: Track research progress",
        "- **iCloud Sync**: Access reports on all devices",
        "",
        "## Project Structure",
        "",
        "```",
        "hedge-fund-research/",
        "├── data/",
        "│   ├── providers/       # Data source implementations",
        "│   └── storage/         # Parquet + DuckDB storage",
        "├── strategy/",
        "│   ├── signals/         # Signal generators",
        "│   └── backtest/        # Backtesting engine",
        "├── analysis/            # Performance analysis & reports",
        "├── scripts/             # CLI tools",
        "└── docs/               # Documentation",
        "```",
        "",
        "## Configuration",
        "",
        "### Data Storage (Hard Drive)",
        f"- **Path**: `{STORAGE_PATH}`",
        "- **Format**: Parquet files + DuckDB",
        "- **Purpose**: Market data, prices, fundamentals, sentiment",
        "",
        "### Obsidian Notes (iCloud Drive)",
        f"- **Vault**: iCloud Drive",
        f"- **Project Folder**: `{OBSIDIAN_PROJECT_PATH.name}`",
        "- **Purpose**: Research reports, summaries, daily notes",
        "",
        "## Usage Examples",
        "",
        "### Fetch Data",
        "```bash",
        "python scripts/fetch_data.py --universe sp500 --years 7",
        "```",
        "",
        "### Run Alpha Research",
        "```bash",
        "# Quick test",
        "python scripts/alpha_research.py --quick --obsidian",
        "",
        "# Full parameter sweep",
        "python scripts/alpha_research.py --full --obsidian",
        "```",
        "",
        "### Generate Reports",
        "```bash",
        "# Generate Obsidian report from existing results",
        "python scripts/generate_obsidian_report.py --type research",
        "",
        "# Generate daily note",
        "python scripts/generate_obsidian_report.py --type daily",
        "```",
        "",
        "## Design Decisions",
        "",
        "| Aspect | Choice | Rationale |",
        "|---------|--------|-----------|",
        "| Portfolio size | < $100K | Lean, cost-conscious design |",
        "| Latency | EOD | Daily batch processing |",
        "| Data storage | Parquet + DuckDB | Zero ops, fast analytics |",
        "| Price data | Yahoo Finance | Free, sufficient for research |",
        "| Social data | StockTwits | Free tier, pre-labeled sentiment |",
        "| Framework | Custom Python | Full control, learning opportunity |",
        "",
        "## Backtest Safeguards",
        "",
        "- **Survivorship bias**: Include delisted stocks in historical universe",
        "- **Look-ahead bias**: Use point-in-time data only",
        "- **Transaction costs**: Model slippage + commissions",
        "- **Walk-forward validation**: Train/test splits with purging",
        "",
        "## Next Steps",
        "",
        "- [ ] Run full parameter sweep",
        "- [ ] Analyze top-performing configurations",
        "- [ ] Implement additional signals",
        "- [ ] Expand universe beyond S&P 500",
        "- [ ] Add real-time monitoring",
        "",
        "## Related Documents",
        "",
        "- [[_Index|Project Index]]",
        "- [[Research/Alpha-Research/|Alpha Research Reports]]",
        "- [[Research/Backtests/|Backtest Reports]]",
        "- [[Daily-Notes/|Daily Notes]]",
        "",
        "## Technical Stack",
        "",
        "- **Python 3.11+**",
        "- **pandas, numpy**: Data manipulation",
        "- **yfinance**: Price data",
        "- **duckdb**: Fast queries",
        "- **pyarrow**: Parquet storage",
        "- **matplotlib, plotly**: Visualization",
        "",
    ]
    
    content = "\n".join(lines)
    
    # Save to Obsidian
    obsidian_path = save_obsidian_note(
        content,
        "_Index.md",
        subfolder=None,  # Save to project root
    )
    
    print(f"✓ Created project report: {obsidian_path}")
    return obsidian_path


if __name__ == "__main__":
    create_project_report()
