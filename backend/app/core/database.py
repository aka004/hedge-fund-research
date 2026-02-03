"""
Database connection management.
"""

import duckdb
from pathlib import Path
from contextlib import contextmanager

# Import from parent project
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config import RESEARCH_DB_PATH


@contextmanager
def get_db():
    """Get database connection context manager."""
    conn = duckdb.connect(str(RESEARCH_DB_PATH), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


def query_db(sql: str, params: dict = None):
    """Execute a query and return results as list of dicts."""
    with get_db() as conn:
        if params:
            result = conn.execute(sql, params).fetchdf()
        else:
            result = conn.execute(sql).fetchdf()
        return result.to_dict('records')
