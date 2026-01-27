# Macro Indicators Reference

Reference guide for macro indicators used in cross-asset and commodity analysis.

**Data Source:** Yahoo Finance (yfinance) unless noted otherwise.

---

## Quick Reference - Yahoo Finance Tickers

| Indicator | Yahoo Ticker | Notes |
|-----------|--------------|-------|
| Dollar Index (DXY) | `DX-Y.NYB` | |
| 10Y Treasury Yield | `^TNX` | In percentage points |
| 2Y Treasury Yield | `^IRX` | 13-week T-bill rate |
| VIX | `^VIX` | |
| Copper Futures | `HG=F` | |
| Gold Futures | `GC=F` | |
| Silver Futures | `SI=F` | |
| Crude Oil (WTI) | `CL=F` | |
| Natural Gas | `NG=F` | |
| Commodity ETF (GSCI) | `GSG` | CRB proxy |
| Commodity ETN | `DJP` | CRB proxy |
| High Yield Bond ETF | `HYG` | For credit spreads |
| Investment Grade ETF | `LQD` | For credit spreads |
| S&P 500 | `^GSPC` | |
| Nasdaq 100 | `^NDX` | |
| Russell 2000 | `^RUT` | Small caps |
| Nikkei 225 | `^N225` | Japan |
| Shanghai Composite | `000001.SS` | China |
| FTSE 100 | `^FTSE` | UK |
| Euro Stoxx 50 | `^STOXX50E` | Europe |

---

## CRB Index (Thomson Reuters/CoreCommodity CRB Index)

### Overview
- **What it is:** Broad commodity index tracking 19 core commodities across energy, metals, and agriculture
- **History:** Since 1957 - one of the oldest commodity benchmarks
- **Yahoo Finance:** Not available (use `GSG` or `DJP` as proxy)
- **TradingView:** `TVC:TRJCRB`

### Composition
- Energy (heavy weighting, ~39%): Crude oil, heating oil, natural gas
- Agriculture (~41%): Corn, soybeans, wheat, cotton, sugar, coffee, cocoa, orange juice, live cattle, lean hogs
- Metals (~20%): Gold, silver, copper, aluminum, nickel

### Use Cases

**1. Commodity Cycle Confirmation**
- When CRB is in strong uptrend: even commodities with weak fundamentals resist deep drops (cost push + inflation expectations create a floor)
- When CRB rolls over: signals global demand or liquidity problems - even low-inventory commodities struggle

**2. Breakout Validation for Individual Commodities**
- If copper breaks resistance AND CRB is making new highs = reliable breakout
- If commodity breaks out but CRB isn't moving = be cautious, potential false signal

**3. Inflation Pressure Gauge**
- Sustained CRB rise -> inflation pressure -> affects Treasury yields and USD -> feeds back into commodity prices

**4. Oil as Lead Indicator**
- Oil has heavy CRB weighting and is "mother of commodities"
- Oil rises -> higher smelting/transport costs -> lifts all metals

### Strengths & Weaknesses
- **Strengths:** Broad basket, good growth/inflation proxy, long history
- **Weaknesses:** Energy-heavy, gold underweighted, can lag individual moves

---

## Dollar Index (DXY)

### Overview
- **What it is:** Trade-weighted index of USD vs basket of 6 major currencies
- **Yahoo Finance:** `DX-Y.NYB`
- **Composition:** EUR (57.6%), JPY (13.6%), GBP (11.9%), CAD (9.1%), SEK (4.2%), CHF (3.6%)

### Use Cases
- **Inverse correlation with commodities:** Strong dollar = headwind for commodity prices (priced in USD)
- **Risk sentiment:** Dollar strengthens in risk-off, weakens in risk-on
- **EM pressure:** Strong dollar = stress for EM debt/equities

### Key Levels
- Above 100: Strong dollar regime
- Below 90: Weak dollar regime
- Watch for breakouts from multi-month ranges

---

## 10-Year Treasury Yield

### Overview
- **What it is:** Yield on US 10-year government bonds - benchmark "risk-free" rate
- **Yahoo Finance:** `^TNX` (multiply by 10 for actual yield in bps)

### Use Cases
- **Growth expectations:** Rising yields = stronger growth outlook (usually)
- **Equity valuations:** Higher yields = higher discount rate = lower equity multiples
- **Real yields:** 10Y minus inflation expectations = real yield (key for gold)

### Spread Indicators
- **2s10s spread:** `^TNX` minus 2Y yield - yield curve steepness
- **10Y minus Fed Funds:** Term premium indicator

---

## VIX (Volatility Index)

### Overview
- **What it is:** 30-day implied volatility of S&P 500 options - "fear gauge"
- **Yahoo Finance:** `^VIX`

### Use Cases
- **Risk sentiment:** VIX spike = fear/risk-off, VIX crush = complacency
- **Mean reversion:** Extreme VIX levels tend to revert
- **Vol regime:** VIX < 15 = low vol regime, VIX > 25 = elevated, VIX > 35 = crisis

### Key Levels
- < 12: Extreme complacency (often precedes correction)
- 15-20: Normal
- 25-30: Elevated fear
- > 35: Panic/crisis

---

## Credit Spreads

### Overview
- **What it is:** Yield difference between corporate bonds and Treasuries
- **Yahoo Finance proxy:** Compare `HYG` (high yield) vs `LQD` (investment grade) price action

### Use Cases
- **Credit stress:** Widening spreads = credit stress, risk-off
- **Economic health:** Tight spreads = confidence in corporate health
- **Leading indicator:** Credit often leads equities at turning points

### How to Calculate
```python
# Simple proxy using ETF yields
hy_yield = 1 / HYG_price * 100  # Rough approximation
ig_yield = 1 / LQD_price * 100
hy_ig_spread = hy_yield - ig_yield
```

---

## Copper/Gold Ratio

### Overview
- **What it is:** Copper price divided by gold price
- **Yahoo Finance:** `HG=F` / `GC=F`

### Use Cases
- **Growth vs safety:** Rising ratio = growth optimism (copper = industrial), falling = safety bid (gold = haven)
- **Reflation indicator:** Rising copper/gold often confirms reflation trades
- **Equity correlation:** Tends to correlate with equity risk appetite

---

## Baltic Dry Index

### Overview
- **What it is:** Cost of shipping dry bulk commodities (iron ore, coal, grain)
- **Yahoo Finance:** Not available (use `BDRY` ETF as proxy, or pull from external source)

### Use Cases
- **Global trade activity:** Rising BDI = strong trade demand
- **China demand:** BDI sensitive to Chinese commodity imports
- **Leading indicator:** Can lead commodity and equity moves

---

## Key Futures Contracts

### Metals
| Metal | Yahoo Ticker | Use |
|-------|--------------|-----|
| Copper | `HG=F` | Industrial demand, "Dr. Copper" |
| Gold | `GC=F` | Safe haven, real rates inverse |
| Silver | `SI=F` | Industrial + monetary hybrid |
| Platinum | `PL=F` | Auto catalyst demand |
| Palladium | `PA=F` | Auto catalyst demand |

### Energy
| Commodity | Yahoo Ticker | Use |
|-----------|--------------|-----|
| Crude Oil (WTI) | `CL=F` | Energy benchmark |
| Brent Crude | `BZ=F` | International oil benchmark |
| Natural Gas | `NG=F` | Power generation, heating |

### Agriculture
| Commodity | Yahoo Ticker | Use |
|-----------|--------------|-----|
| Corn | `ZC=F` | Food/feed/ethanol |
| Soybeans | `ZS=F` | Food/feed |
| Wheat | `ZW=F` | Food staple |

---

## Regime Detection Framework

```python
def macro_regime(dxy, vix, hy_lg_spread, copper_gold):
    """
    Simple macro regime classification
    """
    if vix > 25 and hy_lg_spread > 4:
        return "RISK_OFF_CRISIS"
    elif vix > 20 and dxy > 100:
        return "RISK_OFF_DEFENSIVE"
    elif vix < 15 and copper_gold > 0.005:
        return "RISK_ON_GROWTH"
    elif vix < 18 and dxy < 95:
        return "RISK_ON_REFLATION"
    else:
        return "NEUTRAL"
```

---

## Data Collection Code

```python
import yfinance as yf
import pandas as pd

MACRO_TICKERS = {
    'DXY': 'DX-Y.NYB',
    'US10Y': '^TNX',
    'VIX': '^VIX',
    'Copper': 'HG=F',
    'Gold': 'GC=F',
    'Silver': 'SI=F',
    'Oil': 'CL=F',
    'SPX': '^GSPC',
    'HYG': 'HYG',
    'LQD': 'LQD',
    'GSG': 'GSG',  # Commodity proxy
}

def fetch_macro_data(period='1y'):
    """Fetch macro indicator data from Yahoo Finance"""
    data = {}
    for name, ticker in MACRO_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            data[name] = hist['Close']
        except Exception as e:
            print(f"Error fetching {name}: {e}")
    return pd.DataFrame(data)

def calculate_ratios(df):
    """Calculate derived indicators"""
    df['Copper_Gold'] = df['Copper'] / df['Gold']
    df['HY_IG_Ratio'] = df['HYG'] / df['LQD']
    return df
```

---

*Last updated: 2026-01-26*
