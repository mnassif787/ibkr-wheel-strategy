# Wheel Strategy Updates - January 25, 2026

## ✅ Issues Fixed

### 1. Entry Signal Now Wheel Strategy Specific
**Before:** Entry signal was generic "BUY NOW" without context
**After:** Entry signal is now specifically for **selling cash-secured PUTS**

- Signal changed from "BUY NOW" → **"SELL PUT NOW"**
- Analysis focused on PUT-selling conditions:
  - ✅ RSI oversold/neutral = good time to sell puts
  - ✅ Near support levels = good strike selection
  - ✅ High IV = better premium collection
  - ✅ Away from resistance = lower assignment risk

### 2. "Why?" Button Now Working
**Fixed:** Modal JavaScript was trying to access DOM before it loaded
**Solution:** Wrapped event listener in `DOMContentLoaded`

Click "Why?" to see detailed analysis:
- 🎯 EXCELLENT: Best time to sell puts (75+ score)
- ✅ GOOD: Good put-selling opportunity (60-74 score)
- ⏳ WAIT: Mixed conditions (45-59 score)
- 🚫 AVOID: Poor put-selling conditions (<45 score)

### 3. Market-Wide Scanning Added
**Before:** Only showing 4 stocks you manually added
**After:** Can discover and scan hundreds of stocks from major indices

## 🚀 How to Add More Stocks

### Option 1: Use Batch Script (Easiest)
Double-click: `add_market_stocks.bat`

This will:
1. Add 50 popular wheel strategy stocks
2. Calculate technical indicators
3. Sync options data
4. Ready to screen!

### Option 2: Command Line (Custom)

**Add Popular Stocks (Recommended)**
```bash
python manage.py discover_stocks --preset=popular --limit=50
```
Adds: AAPL, MSFT, TSLA, F, SOFI, SPY, QQQ, SCHD, and 42 more

**Add S&P 500 Stocks**
```bash
python manage.py discover_stocks --preset=sp500 --limit=100
```

**Add Tech Stocks**
```bash
python manage.py discover_stocks --preset=tech --limit=30
```

**Add Dow 30**
```bash
python manage.py discover_stocks --preset=dow --limit=30
```

**After adding stocks, run:**
```bash
python manage.py calculate_indicators
python manage.py sync_yfinance_options
```

## 📊 New Features

### Dual Indicator System

**🎯 Wheel Score (0-100)**
- **Purpose:** Identifies WHICH stocks are good wheel candidates
- **Factors:** 
  - Volatility 25% (IV from options)
  - Liquidity 20% (volume, open interest)
  - Technical 25% (RSI, EMA, support)
  - Stability 20% (market cap, beta, dividend)
  - Price 10% (sweet spot $10-$50)
- **Grade:** A (80+), B (65+), C (50+), D (<50)

**🎬 Entry Signal (0-100)**
- **Purpose:** Identifies WHEN to sell cash-secured puts
- **Factors:**
  - Technical Setup 40% (RSI oversold, near support)
  - Options Premium 30% (High IV, good open interest)
  - Market Context 20% (52-week lows, Bollinger position)
  - Risk Penalty -10% (Near resistance, overbought)
- **Signal:** SELL PUT NOW (60+), WAIT (45-59), AVOID (<45)
- **Quality:** EXCELLENT (75+), GOOD (60+), FAIR (45+), POOR (<45)

## 💡 Usage Workflow

1. **Discover Stocks**
   ```bash
   python manage.py discover_stocks --preset=popular --limit=50
   ```

2. **Calculate Indicators**
   ```bash
   python manage.py calculate_indicators
   ```

3. **Sync Options**
   ```bash
   python manage.py sync_yfinance_options
   ```

4. **Screen on Webpage**
   - Go to: http://127.0.0.1:8000/ibkr/stocks/
   - Sort by "Blended Score" to find best stocks
   - Sort by "Entry Signal" to find best timing
   - Filter by Grade (A/B/C/D)
   - Filter by Price Range (sweet spot $10-$50)
   - Click "View Details" for wheel score breakdown
   - Click "Why?" for entry signal analysis

5. **Export Results**
   - Click "Export Top 10 CSV" button
   - Get spreadsheet with all scores

## 🎯 Example Workflow

**Finding a Put to Sell:**

1. Sort by "Entry Signal" (highest first)
2. Look for "SELL PUT NOW" with EXCELLENT/GOOD quality
3. Click "Why?" to see reasons:
   - "✅ RSI oversold (28.5) - great entry point"
   - "✅ Near support $13.20 (2.8% away)"
   - "✅ High IV (48.2%) - excellent premium"
4. Click stock name to see details
5. Click "View Options Chain" to select strike
6. Sell cash-secured put at support level

## 🔧 Available Commands

```bash
# Discover stocks from market
python manage.py discover_stocks --preset=popular --limit=50

# Calculate technical indicators (RSI, EMA, support, resistance)
python manage.py calculate_indicators

# Calculate indicators for specific stock
python manage.py calculate_indicators --ticker=F

# Sync options data from Yahoo Finance
python manage.py sync_yfinance_options

# Refresh all watchlist data
python manage.py refresh_stocks

# Run development server
python manage.py runserver
```

## 📁 New Files

- `apps/ibkr/management/commands/discover_stocks.py` - Discovers stocks from indices
- `add_market_stocks.bat` - Batch script to add 50 popular stocks
- `calculate_ford_indicators.bat` - Fix Ford's missing indicators
- `check_ford.py` - Diagnostic script for debugging

## 🎨 UI Updates

- Entry Signal badge shows "SELL PUT NOW" instead of "BUY NOW"
- Modal meaning text explains PUT-selling context
- Yellow notice when <20 stocks in database
- Instructions to add more stocks inline
- Color coding: 🟢 Excellent, 🔵 Good, 🟡 Wait, 🔴 Avoid
