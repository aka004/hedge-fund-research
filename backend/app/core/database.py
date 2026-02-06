"""
Database connection management.
"""

# Import from parent project
import sys
from contextlib import contextmanager
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config import RESEARCH_DB_PATH


def _check_db_path() -> None:
    """Verify the database path is reachable.

    If RESEARCH_DB_PATH is a symlink (e.g. to an external drive),
    ensure the mount point exists before attempting to connect.

    Raises:
        FileNotFoundError: When the external drive is not mounted or
            the parent directory is missing.
    """
    db_path = RESEARCH_DB_PATH
    if db_path.is_symlink():
        target = db_path.resolve()
        # Check that the volume mount point exists (e.g. /Volumes/Data_2026)
        parts = target.parts
        if len(parts) >= 3 and parts[1] == "Volumes":
            mount_path = Path("/") / parts[1] / parts[2]
            if not mount_path.exists():
                raise FileNotFoundError(
                    f"External drive not mounted: {mount_path}. "
                    "Connect the drive and retry."
                )
    resolved = db_path.resolve()
    if not resolved.parent.exists():
        raise FileNotFoundError(f"Database parent directory missing: {resolved.parent}")


@contextmanager
def get_db():
    """Get read-only database connection context manager."""
    _check_db_path()
    conn = duckdb.connect(str(RESEARCH_DB_PATH), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_write():
    """Get read-write database connection context manager."""
    _check_db_path()
    conn = duckdb.connect(str(RESEARCH_DB_PATH), read_only=False)
    try:
        yield conn
    finally:
        conn.close()


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean DataFrame by replacing NaN/NA with None."""
    # Replace NaN with None for JSON serialization
    df = df.replace({pd.NA: None, np.nan: None})
    return df


def query_db(sql: str, params: dict = None):
    """Execute a query and return results as list of dicts."""
    with get_db() as conn:
        if params:
            result = conn.execute(sql, params).fetchdf()
        else:
            result = conn.execute(sql).fetchdf()

        # Convert to records and handle None/NaN values
        records = result.to_dict("records")

        # Clean up each record
        for record in records:
            for key, value in list(record.items()):
                # Convert pandas NA/NaN to None
                if value is not None:
                    try:
                        import math

                        if isinstance(value, float) and math.isnan(value):
                            record[key] = None
                    except:
                        pass

        return records
