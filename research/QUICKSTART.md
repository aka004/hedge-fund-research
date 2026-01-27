# Research Orchestrator Quick Start

This guide will help you set up and run your first research session using the multi-agent equity research system.

## Prerequisites

1. **Python packages** - Install required dependencies:
   ```bash
   pip install anthropic rich duckdb pandas pyarrow yfinance
   ```

2. **Anthropic API Key** - Get your API key from [https://console.anthropic.com/](https://console.anthropic.com/)

## Step 1: Configure API Key

Add your Anthropic API key to the `.env` file:

```bash
# Open .env file
nano .env

# Add this line:
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Save and exit (Ctrl+X, Y, Enter)
```

Verify it's set:
```bash
python -c "from config import get_anthropic_api_key; print('✅ API key configured')"
```

## Step 2: Initialize Database

Create the research database schema and load test data for Apple (AAPL):

```bash
python scripts/setup_research_db.py --ticker AAPL --years 7
```

This will:
- Create DuckDB database at `/Volumes/Data_2026/hedge-fund-research-data/research.duckdb`
- Create tables: `prices`, `fundamentals`, `social_metrics`, `filings`, `improvement_backlog`, `session_history`
- Fetch 7 years of price data for AAPL from Yahoo Finance
- Load the data into the database

Expected output:
```
✅ Schema initialized successfully
✅ Saved 1753 rows to Parquet
✅ Loaded 1753 price records for AAPL
✅ Setup complete!
```

## Step 3: Check Database Status

Verify data was loaded correctly:

```bash
python scripts/setup_research_db.py --status --ticker AAPL
```

Expected output:
```
PRICES:
  Records: 1753
  Date range: 2018-01-27 to 2026-01-26
  Days stale: 0

FUNDAMENTALS: NO DATA
SOCIAL_METRICS: NO DATA
FILINGS: NO DATA
```

Note: It's normal for `fundamentals`, `social_metrics`, and `filings` to be empty initially. The research agents will identify these as data gaps and log them for future improvement.

## Step 4: Run Your First Research Session

Research Apple using the multi-agent system:

```bash
python scripts/test_research.py AAPL "Apple Inc."
```

This will:
1. **Data Quality Agent** - Check what data exists in the database
2. **Data Agent** - Gather external sources to fill gaps (targets 60+ sources)
3. **Quant Agent** - Build DCF model, calculate expected return
4. **Risk Agent** - Analyze downside scenarios and capital structure
5. **Competitive Agent** - Assess market position and moat strength
6. **Qualitative Agent** - Evaluate management and execution quality
7. **Synthesis Agent** - Compile everything into investment memo

Expected time: 5-10 minutes (depends on API speed and number of agents)

## Step 5: View Results

After the session completes, check the outputs:

### View Final Memo

```bash
# Find the latest session directory
ls -lt outputs/research/ | head -5

# View the memo
cat outputs/research/AAPL_*/final_memo.md | less
```

The memo includes:
- Executive Summary
- Rating & Price Targets
- Investment Thesis
- 21 detailed sections with [Fact/Analysis/Inference] labels
- Coverage log appendix
- Model appendix

### View Session Feedback

```bash
# View feedback with jq for pretty printing
cat outputs/research/AAPL_*/session_feedback.json | jq .

# Or without jq
cat outputs/research/AAPL_*/session_feedback.json
```

Key metrics to check:
- `database_hit_rate` - Percentage of data from database vs external sources
- `workaround_time_minutes` - Time spent gathering missing data
- `data_gaps` - List of specific data missing from database

### View Individual Agent Outputs

```bash
cd outputs/research/AAPL_*/

# Data availability assessment
cat data_availability.json | jq .

# Coverage log (60+ sources)
cat coverage_log.json | jq .coverage_validator

# Valuation package
cat valuation_package.json | jq .fair_value_band

# Risk assessment
cat risk_assessment.json | jq .bear_case

# Quality scorecard
cat quality_scorecard.json | jq .
```

## Step 6: Check Improvement Backlog

The system tracks data gaps across sessions. Check what's been logged:

```bash
# Query the improvement backlog table
python -c "
import duckdb
from config import RESEARCH_DB_PATH
con = duckdb.connect(str(RESEARCH_DB_PATH))
backlog = con.execute('SELECT * FROM improvement_backlog ORDER BY priority').fetchdf()
print(backlog)
"
```

## Troubleshooting

### Issue: API Key Error

```
ValueError: ANTHROPIC_API_KEY not set
```

**Fix:**
```bash
# Check if .env file has the key
grep ANTHROPIC_API_KEY .env

# If empty or missing, add it:
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> .env
```

### Issue: Database Not Found

```
⚠️ Research database not found at /Volumes/Data_2026/hedge-fund-research-data/research.duckdb
```

**Fix:**
```bash
# Initialize the database
python scripts/setup_research_db.py --initialize-only

# Then load data
python scripts/setup_research_db.py --ticker AAPL --years 7
```

### Issue: No Price Data

```
PRICES: NO DATA
```

**Fix:**
```bash
# Fetch and load price data
python scripts/setup_research_db.py --ticker AAPL --years 7

# Verify
python scripts/setup_research_db.py --status --ticker AAPL
```

### Issue: Module Not Found

```
ModuleNotFoundError: No module named 'anthropic'
```

**Fix:**
```bash
pip install anthropic rich
```

### Issue: Agent Timeout or Error

Check the error message in the output. Common causes:
- API rate limiting (wait a minute and retry)
- Invalid API key (check .env file)
- Network issues (check internet connection)

## Next Steps

### Research More Companies

```bash
# Microsoft
python scripts/test_research.py MSFT "Microsoft Corporation"

# Google
python scripts/test_research.py GOOGL "Alphabet Inc."

# Tesla
python scripts/test_research.py TSLA "Tesla Inc."
```

### Add More Data Sources

The system will identify data gaps. To improve database hit rate over time:

1. **Add Fundamentals Data**
   ```bash
   # Extend fetch_data.py to fetch fundamentals from Yahoo Finance
   # Or manually add to database
   ```

2. **Add SEC Filings**
   ```bash
   # Use existing sec_edgar provider
   python scripts/fetch_sec_filings.py --ticker AAPL
   ```

3. **Add Social Sentiment**
   ```bash
   # Use existing stocktwits provider
   python scripts/fetch_social_data.py --ticker AAPL
   ```

### View Improvement Metrics Over Time

After running multiple sessions:
```bash
# Query session history
python -c "
import duckdb
from config import RESEARCH_DB_PATH
con = duckdb.connect(str(RESEARCH_DB_PATH))
history = con.execute('''
    SELECT 
        ticker,
        start_time,
        database_hit_rate,
        workaround_time_minutes,
        data_quality_score
    FROM session_history
    ORDER BY start_time DESC
    LIMIT 10
''').fetchdf()
print(history)
"
```

Expected improvement over time:
- Database hit rate: 40% → 60% → 80%
- Workaround time: 60 min → 30 min → 15 min
- Data quality score: 65 → 80 → 90

## Understanding the Output

### Quality Scorecard (100 points total)

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| Market | 25 | TAM size, growth rate, market structure |
| Moat | 25 | Competitive advantages, barriers to entry |
| Unit Economics | 20 | Margins, CAC/LTV, capital efficiency |
| Execution | 15 | Management track record, delivery vs promises |
| Financial Quality | 15 | Balance sheet strength, cash generation |

### Rating System

- **BUY** (70+ quality score, E[TR] ≥30%, all gates pass)
- **HOLD** (60-69 quality score, or some gates fail)
- **WAIT-FOR-ENTRY** (Good business but valuation stretched)
- **SELL** (<60 quality score - forces sell)

### Gates (Must ALL Pass for BUY)

1. **Coverage** - 60+ sources, validator passes
2. **Expected Return** - E[TR] ≥30%
3. **Skew** - E[TR]/Bear Drawdown ≥1.7×
4. **Margin of Safety** - Price ≤75% of mid fair value
5. **Quality** - Score ≥70/100
6. **Why Now** - Catalyst within 24 months

## System Architecture

```
┌─────────────────┐
│  Orchestrator   │ Coordinates the full research loop
└────────┬────────┘
         │
         ├──────────────────┬──────────────┬──────────────┐
         ▼                  ▼              ▼              ▼
  ┌─────────────┐   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │ Data Quality│   │ Data Agent  │ │ Quant Agent │ │ Risk Agent  │
  └─────────────┘   └─────────────┘ └─────────────┘ └─────────────┘
         │                  │              │              │
         │                  ▼              ▼              ▼
         │          ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
         │          │Competitive  │ │Qualitative  │ │Synthesis    │
         │          │   Agent     │ │   Agent     │ │   Agent     │
         │          └─────────────┘ └─────────────┘ └─────────────┘
         │                  │              │              │
         ▼                  ▼              ▼              ▼
  ┌──────────────────────────────────────────────────────────┐
  │             Session Feedback & Improvement Backlog       │
  └──────────────────────────────────────────────────────────┘
```

## Further Reading

- [`README.md`](README.md) - Full system documentation
- [`00-ORCHESTRATOR.md`](00-ORCHESTRATOR.md) - Orchestrator agent prompt
- [`07-HANDOFF-CONTRACTS.md`](07-HANDOFF-CONTRACTS.md) - Agent input/output schemas
- [`../docs/plans/2026-01-26-AFML-implementation-roadmap.md`](../docs/plans/2026-01-26-AFML-implementation-roadmap.md) - AFML integration details

## Support

If you encounter issues:
1. Check troubleshooting section above
2. Review error messages in terminal output
3. Check agent logs in `outputs/research/TICKER_*/`
4. Verify database status with `--status` flag

Happy researching! 📊
