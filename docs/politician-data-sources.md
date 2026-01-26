# Politician Stock Trade Data Sources

## Important Limitation: SEC Form 4 vs. Government Disclosures

**SEC Form 4 filings are ONLY for corporate insiders** (officers, directors, 10% owners of public companies). Most politicians do NOT file SEC Form 4s because they're not corporate insiders.

### Data Sources by Government Role

| Role | Disclosure Form | Filing Location | Data Available |
|------|----------------|----------------|----------------|
| **Corporate Insiders** | SEC Form 4 | SEC EDGAR | ✅ Available via EdgarTools |
| **Executive Branch** (President, Cabinet) | OGE Form 278-T | Office of Government Ethics | ❌ Not in SEC EDGAR |
| **Congressional Members** | STOCK Act Disclosures | House/Senate Ethics Offices | ❌ Not in SEC EDGAR |
| **Former Corporate Insiders** | SEC Form 4 (if still insider) | SEC EDGAR | ✅ Available if they maintain corporate roles |

## Finding CIKs for Politicians

### Who Has CIKs?

Politicians only have SEC CIKs if they:
1. **Currently serve** as officers/directors of public companies
2. **Previously served** as officers/directors and still file Form 4s
3. **Own 10%+** of a public company's stock

### How to Find CIKs

1. **Go to SEC EDGAR Company Search**: https://www.sec.gov/edgar/searchedgar/companysearch

2. **Search by name** (try both formats):
   - "Last First" (e.g., "Trump Donald")
   - "First Last" (e.g., "Donald Trump")

3. **Look for individuals** (not companies) in results

4. **Check Form 4 filings** to verify it's the right person

5. **If no results**: They likely don't file SEC Form 4s

### Example: Finding Kelly Loeffler's CIK

Kelly Loeffler was CEO of Bakkt (a company). To find her CIK:

1. Search "Loeffler Kelly" in SEC EDGAR
2. Look for Bakkt-related filings
3. Check if she filed Form 4s as an officer/director
4. Use the CIK from those filings

## Alternative Data Sources

Since most politicians don't file SEC Form 4s, consider these alternatives:

### 1. Capitol Trades (capitoltrades.com)
- **Free** website tracking congressional trades
- Uses STOCK Act disclosure data
- **No official API** (would need scraping)

### 2. Quiver Quantitative
- **Free tier** includes congressional trades
- **Paid API** ($10-25/month) for programmatic access
- Tracks STOCK Act disclosures

### 3. OGE Form 278-T (Executive Branch)
- Publicly available at: https://extapps2.oge.gov/
- Requires manual parsing (no API)
- Includes President, VP, Cabinet members

### 4. House/Senate Ethics Offices
- STOCK Act disclosures are public
- Available on House/Senate websites
- Requires manual collection

## Recommendations

### For Trump Administration

**Option 1: Focus on Corporate Insiders**
- Only track Trump admin members who were/are corporate insiders
- These will have CIKs and file SEC Form 4s
- Example: Former CEOs who joined administration

**Option 2: Use Alternative Sources**
- Scrape Capitol Trades for congressional members
- Parse OGE Form 278-T for executive branch
- Combine with SEC Form 4 data

**Option 3: Hybrid Approach**
- Use SEC Form 4s for corporate insiders (via EdgarTools)
- Use alternative sources for others
- Combine in unified storage format

## Current Implementation

The current implementation uses **EdgarTools** which only accesses **SEC Form 4 filings**. This means:

✅ **Works for**: Politicians who are/were corporate insiders  
❌ **Doesn't work for**: Most politicians (they file different forms)

To track Trump admin trades comprehensively, you would need to:
1. Add OGE Form 278-T parser (executive branch)
2. Add STOCK Act parser (congressional)
3. Or integrate with Capitol Trades/Quiver Quantitative

## Next Steps

1. **Verify CIKs**: Search SEC EDGAR for each politician
2. **Identify corporate insiders**: Focus on those with CIKs
3. **Consider alternatives**: Add support for OGE/STOCK Act data sources
4. **Update config**: Only include politicians with verified CIKs
