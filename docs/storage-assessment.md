# Data Storage Assessment

## Current Setup

**Storage Format:** Parquet files + DuckDB for queries  
**Current Location:** `hedge-fund-research/data/cache/` (42MB currently)  
**Storage Structure:**
- `prices/` - OHLCV data per symbol
- `fundamentals/` - Fundamental metrics per symbol
- `sentiment/` - Sentiment history per symbol

## Why Parquet + DuckDB is Suitable

### Advantages

1. **Time-series data optimized**: Parquet is columnar format, perfect for time-series price data
2. **Fast analytics**: DuckDB provides SQL interface over Parquet files efficiently
3. **Zero-dependency storage**: No database server required
4. **Fast reads for backtesting**: Columnar format allows efficient date range queries
5. **Compression**: Parquet files are compressed (Snappy compression used)
6. **Scalable**: Can handle large datasets efficiently

### Current Data Volume

- **42MB** of cached data (S&P 500, ~7 years)
- **Growth rate**: ~6MB per year for full S&P 500 universe
- **Projected 10-year size**: ~100MB (well within any storage capacity)

## SQL (SQLite) Assessment

### Would SQL add value?

**Not needed for current use case:**

1. **DuckDB already provides SQL**: DuckDB gives you SQL queries over Parquet files
2. **Data volume doesn't require SQL**: 42MB is tiny, doesn't need database optimization
3. **No transactional requirements**: No need for ACID guarantees
4. **No complex joins**: Current queries are simple time-series lookups

**SQL could be useful if:**

1. **ACID transactions needed**: If you need transactional guarantees
2. **Single database file preference**: If you prefer one `.db` file vs many `.parquet` files
3. **Complex multi-table joins**: If you need to join across many different data sources frequently
4. **Concurrent writes**: If multiple processes need to write simultaneously

## Recommendation

**Keep Parquet + DuckDB setup.**

### Rationale

1. Current setup is optimal for time-series financial data
2. DuckDB provides SQL interface when needed
3. No performance issues at current scale
4. Simpler architecture (no database server)
5. Easy to backup (just copy parquet files)

### When to Consider SQL

Consider migrating to SQLite if:
- Data grows beyond 10GB
- You need transactional guarantees
- You prefer single-file storage
- You need complex multi-table joins frequently

## Configuration

Storage path is now configurable via `.env`:

```bash
# Set to external disk if desired
DATA_STORAGE_PATH=/Volumes/ExternalDrive/hedge-fund-data
```

If not set, defaults to `./data/cache` (project-relative).

## Migration Notes

- Existing data in `data/cache/` remains accessible
- New storage path will be used for new data
- Both paths can coexist during transition
- Use `scripts/migrate_data.py` (if created) for bulk migration
