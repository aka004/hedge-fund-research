"""Obsidian-formatted report generation for hedge-fund-research.

Generates markdown reports with YAML frontmatter suitable for Obsidian vaults.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from config import OBSIDIAN_PROJECT_PATH


def generate_obsidian_frontmatter(
    title: str,
    report_type: str,
    created: Optional[datetime] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate YAML frontmatter for Obsidian notes.
    
    Args:
        title: Report title
        report_type: Type of report (research, backtest, daily)
        created: Creation timestamp (defaults to now)
        tags: List of tags
        metadata: Additional metadata fields
        
    Returns:
        YAML frontmatter string
    """
    if created is None:
        created = datetime.now()
    
    if tags is None:
        tags = []
    
    # Ensure project tag is included
    if "project/hedge-fund-research" not in tags:
        tags.insert(0, "project/hedge-fund-research")
    
    # Ensure type tag is included
    type_tag = f"type/{report_type}"
    if type_tag not in tags:
        tags.append(type_tag)
    
    frontmatter = {
        "title": title,
        "project": "hedge-fund-research",
        "type": report_type,
        "created": created.strftime("%Y-%m-%d %H:%M:%S"),
        "tags": tags,
    }
    
    # Add any additional metadata
    if metadata:
        frontmatter.update(metadata)
    
    # Format as YAML
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    
    return "\n".join(lines)


def generate_obsidian_uri(vault_path: Path, file_path: Path) -> str:
    """Generate an Obsidian URI for opening a file.
    
    Args:
        vault_path: Path to Obsidian vault
        file_path: Path to file relative to vault
        
    Returns:
        obsidian:// URI string
    """
    # Get relative path from vault
    try:
        rel_path = file_path.relative_to(vault_path)
        # URL encode the path
        encoded_path = str(rel_path).replace("/", "%2F")
        vault_name = vault_path.name
        return f"obsidian://open?vault={vault_name}&file={encoded_path}"
    except ValueError:
        # File not in vault, return empty
        return ""


def save_obsidian_note(
    content: str,
    filename: str,
    subfolder: Optional[str] = None,
    ensure_dir: bool = True,
) -> Path:
    """Save content as an Obsidian note.
    
    Args:
        content: Markdown content with frontmatter
        filename: Filename (with or without .md extension)
        subfolder: Optional subfolder within project path
        ensure_dir: Create directory if it doesn't exist
        
    Returns:
        Path to saved file
    """
    # Ensure .md extension
    if not filename.endswith(".md"):
        filename += ".md"
    
    # Determine target path
    target_dir = OBSIDIAN_PROJECT_PATH
    if subfolder:
        target_dir = target_dir / subfolder
    
    # Try to create directory, fallback to project directory if permission denied
    if ensure_dir:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            # Fallback to project directory if Obsidian vault not accessible
            from config import PROJECT_ROOT
            fallback_dir = PROJECT_ROOT / "obsidian-reports"
            if subfolder:
                fallback_dir = fallback_dir / subfolder
            fallback_dir.mkdir(parents=True, exist_ok=True)
            target_dir = fallback_dir
            import warnings
            warnings.warn(
                f"Could not write to Obsidian vault at {OBSIDIAN_PROJECT_PATH}. "
                f"Saving to {target_dir} instead. "
                f"Please create the folder manually: {OBSIDIAN_PROJECT_PATH.parent} "
                f"Error: {e}"
            )
    
    target_path = target_dir / filename
    
    # Write file - catch permission errors and fallback if needed
    try:
        target_path.write_text(content, encoding="utf-8")
    except (PermissionError, OSError) as e:
        # If we're already in fallback, this is a real problem
        if target_dir == OBSIDIAN_PROJECT_PATH:
            # Try fallback
            from config import PROJECT_ROOT
            fallback_dir = PROJECT_ROOT / "obsidian-reports"
            if subfolder:
                fallback_dir = fallback_dir / subfolder
            fallback_dir.mkdir(parents=True, exist_ok=True)
            target_path = fallback_dir / filename
            target_path.write_text(content, encoding="utf-8")
            import warnings
            warnings.warn(
                f"Could not write to Obsidian vault at {OBSIDIAN_PROJECT_PATH}. "
                f"Saving to {fallback_dir} instead. "
                f"This is likely a macOS permission issue. Grant Terminal/Cursor access in: "
                f"System Settings > Privacy & Security > Files and Folders. "
                f"Error: {e}"
            )
        else:
            # Already in fallback, re-raise
            raise
    
    return target_path


def generate_research_summary_obsidian(
    results: List[Dict[str, Any]],
    run_id: str,
    generated_at: Optional[datetime] = None,
) -> str:
    """Generate Obsidian-formatted research summary report.
    
    Args:
        results: List of research result dictionaries
        run_id: Unique run identifier
        generated_at: Generation timestamp
        
    Returns:
        Markdown content with frontmatter
    """
    if generated_at is None:
        generated_at = datetime.now()
    
    if not results:
        title = f"Research Summary - {run_id}"
        frontmatter = generate_obsidian_frontmatter(
            title=title,
            report_type="research",
            created=generated_at,
            tags=["status/empty"],
        )
        content = f"{frontmatter}\n\n# {title}\n\nNo results to report.\n"
        return content
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(results)
    
    # Rank by Sharpe ratio
    df_sorted = df.sort_values("sharpe_ratio", ascending=False)
    
    # Generate content
    title = f"Alpha Research Summary - {run_id}"
    frontmatter = generate_obsidian_frontmatter(
        title=title,
        report_type="research",
        created=generated_at,
        tags=["status/complete"],
        metadata={
            "run_id": run_id,
            "configurations_tested": len(results),
            "top_sharpe": float(df_sorted.iloc[0]["sharpe_ratio"]) if len(df_sorted) > 0 else 0.0,
        },
    )
    
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"**Run ID:** `{run_id}`",
        f"**Generated:** {generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Configurations tested:** {len(results)}",
        "",
        "## Top 10 Configurations by Sharpe Ratio",
        "",
    ]
    
    top_10 = df_sorted.head(10)
    for idx, (_, row) in enumerate(top_10.iterrows(), 1):
        config_hash = row.get("config_hash", "unknown")
        sharpe = row.get("sharpe_ratio", 0.0)
        cagr = row.get("cagr", 0.0)
        max_dd = row.get("max_drawdown", 0.0)
        sortino = row.get("sortino_ratio", 0.0)
        
        lines.extend([
            f"### #{idx}: `{config_hash}`",
            "",
            f"- **Sharpe Ratio:** {sharpe:.3f}",
            f"- **CAGR:** {cagr*100:.2f}%",
            f"- **Max Drawdown:** {max_dd*100:.2f}%",
            f"- **Sortino Ratio:** {sortino:.3f}",
            "",
        ])
        
        # Add parameter details if available
        param_keys = [k for k in row.index if k.startswith("param_")]
        if param_keys:
            lines.append("**Parameters:**")
            for key in param_keys:
                param_name = key.replace("param_", "").replace("_", " ").title()
                value = row[key]
                if pd.isna(value):
                    value = "None"
                lines.append(f"- {param_name}: {value}")
            lines.append("")
    
    # Parameter sensitivity analysis
    lines.extend([
        "",
        "## Parameter Sensitivity Analysis",
        "",
        "### Lookback Period Impact",
        "",
    ])
    
    if "param_lookback_months" in df.columns:
        for lookback in sorted(df["param_lookback_months"].dropna().unique()):
            subset = df[df["param_lookback_months"] == lookback]
            avg_sharpe = subset["sharpe_ratio"].mean()
            std_sharpe = subset["sharpe_ratio"].std()
            lines.append(
                f"- **{lookback}mo:** Avg Sharpe={avg_sharpe:.3f}, Std={std_sharpe:.3f}"
            )
    
    lines.extend(["", "### Rebalance Frequency Impact", ""])
    if "param_rebalance_frequency" in df.columns:
        for rebal in df["param_rebalance_frequency"].dropna().unique():
            subset = df[df["param_rebalance_frequency"] == rebal]
            avg_sharpe = subset["sharpe_ratio"].mean()
            avg_trades = subset["total_trades"].mean()
            lines.append(
                f"- **{rebal}:** Avg Sharpe={avg_sharpe:.3f}, Avg Trades={avg_trades:.0f}"
            )
    
    lines.extend(["", "### Position Count Impact", ""])
    if "param_max_positions" in df.columns:
        for positions in sorted(df["param_max_positions"].dropna().unique()):
            subset = df[df["param_max_positions"] == positions]
            avg_sharpe = subset["sharpe_ratio"].mean()
            avg_cagr = subset["cagr"].mean()
            lines.append(
                f"- **{positions}:** Avg Sharpe={avg_sharpe:.3f}, Avg CAGR={avg_cagr*100:.2f}%"
            )
    
    # Overall statistics
    lines.extend([
        "",
        "## Overall Statistics",
        "",
        f"- **Mean Sharpe:** {df['sharpe_ratio'].mean():.3f}",
        f"- **Max Sharpe:** {df['sharpe_ratio'].max():.3f}",
        f"- **Min Sharpe:** {df['sharpe_ratio'].min():.3f}",
        f"- **Mean CAGR:** {df['cagr'].mean()*100:.2f}%",
        f"- **Mean Max DD:** {df['max_drawdown'].mean()*100:.2f}%",
        "",
        f"- **Positive Sharpe configs:** {(df['sharpe_ratio'] > 0).sum()} / {len(df)}",
        f"- **Sharpe > 0.5:** {(df['sharpe_ratio'] > 0.5).sum()} / {len(df)}",
        f"- **Sharpe > 1.0:** {(df['sharpe_ratio'] > 1.0).sum()} / {len(df)}",
        "",
        "## Related",
        "- [[_Index|Back to Project Index]]",
        "",
    ])
    
    return "\n".join(lines)


def generate_backtest_report_obsidian(
    result: Dict[str, Any],
    metrics: Dict[str, Any],
    backtest_id: Optional[str] = None,
    generated_at: Optional[datetime] = None,
) -> str:
    """Generate Obsidian-formatted backtest report.
    
    Args:
        result: Backtest result dictionary
        metrics: Performance metrics dictionary
        backtest_id: Optional backtest identifier
        generated_at: Generation timestamp
        
    Returns:
        Markdown content with frontmatter
    """
    if generated_at is None:
        generated_at = datetime.now()
    
    if backtest_id is None:
        backtest_id = generated_at.strftime("%Y%m%d_%H%M%S")
    
    title = f"Backtest Report - {backtest_id}"
    frontmatter = generate_obsidian_frontmatter(
        title=title,
        report_type="backtest",
        created=generated_at,
        tags=["status/complete"],
        metadata={
            "backtest_id": backtest_id,
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "cagr": metrics.get("cagr", 0.0),
        },
    )
    
    start_date = result.get("start_date", "Unknown")
    end_date = result.get("end_date", "Unknown")
    initial_capital = result.get("initial_capital", 0.0)
    final_equity = result.get("final_equity", 0.0)
    
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"**Backtest ID:** `{backtest_id}`",
        f"**Generated:** {generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Period",
        f"- **Start:** {start_date}",
        f"- **End:** {end_date}",
        f"- **Initial Capital:** ${initial_capital:,.2f}",
        f"- **Final Equity:** ${final_equity:,.2f}",
        "",
        "## Returns",
        f"- **Total Return:** {metrics.get('total_return', 0.0)*100:.2f}%",
        f"- **CAGR:** {metrics.get('cagr', 0.0)*100:.2f}%",
        f"- **Annualized Volatility:** {metrics.get('annualized_volatility', 0.0)*100:.2f}%",
        "",
        "## Risk-Adjusted Metrics",
        f"- **Sharpe Ratio:** {metrics.get('sharpe_ratio', 0.0):.2f}",
        f"- **Sortino Ratio:** {metrics.get('sortino_ratio', 0.0):.2f}",
        f"- **Calmar Ratio:** {metrics.get('calmar_ratio', 0.0):.2f}",
        "",
        "## Drawdown",
        f"- **Max Drawdown:** {metrics.get('max_drawdown', 0.0)*100:.2f}%",
        f"- **Max Drawdown Duration:** {metrics.get('max_drawdown_duration_days', 0)} days",
        "",
        "## Trading Statistics",
        f"- **Total Trades:** {metrics.get('total_trades', 0)}",
        f"- **Win Rate:** {metrics.get('win_rate', 0.0)*100:.1f}%",
        f"- **Profit Factor:** {metrics.get('profit_factor', 0.0):.2f}",
        f"- **Average Win:** ${metrics.get('avg_win', 0.0):,.2f}",
        f"- **Average Loss:** ${metrics.get('avg_loss', 0.0):,.2f}",
        "",
        "## Distribution",
        f"- **Skewness:** {metrics.get('skewness', 0.0):.2f}",
        f"- **Kurtosis:** {metrics.get('kurtosis', 0.0):.2f}",
        "",
        "## Related",
        "- [[_Index|Back to Project Index]]",
        "",
    ]
    
    return "\n".join(lines)


def generate_daily_note_obsidian(
    date: date,
    summary: Optional[str] = None,
    tasks: Optional[List[str]] = None,
    notes: Optional[str] = None,
) -> str:
    """Generate Obsidian-formatted daily note.
    
    Args:
        date: Date for the note
        summary: Optional summary of the day
        tasks: Optional list of tasks
        notes: Optional notes section
        
    Returns:
        Markdown content with frontmatter
    """
    title = f"Daily Note - {date.strftime('%Y-%m-%d')}"
    frontmatter = generate_obsidian_frontmatter(
        title=title,
        report_type="daily",
        created=datetime.combine(date, datetime.min.time()),
        tags=["daily"],
    )
    
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
    ]
    
    if summary:
        lines.extend([
            "## Summary",
            "",
            summary,
            "",
        ])
    
    if tasks:
        lines.extend([
            "## Tasks",
            "",
        ])
        for task in tasks:
            lines.append(f"- [ ] {task}")
        lines.append("")
    
    if notes:
        lines.extend([
            "## Notes",
            "",
            notes,
            "",
        ])
    
    lines.extend([
        "## Related",
        "- [[_Index|Back to Project Index]]",
        "",
    ])
    
    return "\n".join(lines)
