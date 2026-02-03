"""
Database connection management.
"""

import duckdb
from pathlib import Path
from contextlib import contextmanager
import pandas as pd
import numpy as np

# Import from parent project
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config import RESEARCH_DB_PATH


@contextmanager
def get_db():
    """Get database connection context manager."""
    # Create a new connection for each request (thread-safe)
    conn = duckdb.connect(str(RESEARCH_DB_PATH), read_only=True)
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
        records = result.to_dict('records')
        
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
