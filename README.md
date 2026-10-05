# SENSEX Live Option Chain Scraper & Analytics Dashboard

> **Real-time BSE India SENSEX option chain data pipeline** — fetches live derivatives data every 60 seconds using headless browser automation with anti-bot WAF bypass, computes Black-Scholes Greeks, and streams results into a Google Sheets dashboard.

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![Selenium](https://img.shields.io/badge/Selenium-Automation-green?logo=selenium)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-API-brightgreen?logo=googlesheets)
![BSE India](https://img.shields.io/badge/Data%20Source-BSE%20India-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## 🎯 What This Project Does

This tool automates the process of:
1. **Loading** BSE India's SENSEX derivatives page using a stealth headless Chrome browser
2. **Capturing** the internal option chain API response using Chrome DevTools Protocol (CDP)
3. **Computing** Delta (Black-Scholes), Put-Call Ratio (PCR), Support & Resistance, and open-interest trend signals for every strike price
4. **Pushing** the processed data into a live Google Sheet every 60 seconds

---

## ⚡ Key Technical Highlights

| Feature | Technology Used |
|---|---|
| Anti-bot WAF bypass | CDP Network Interception + UI Interaction Simulation |
| Headless Browser | Selenium 4 + ChromeDriver (via webdriver-manager) |
| Option Greeks | Black-Scholes Delta via `scipy.stats.norm` |
| Data Processing | Pandas DataFrame pipeline |
| Cloud Output | Google Sheets API via Service Account OAuth2 |
| Environment Support | Local Windows/Linux + Google Colab |

---

## 🏗️ System Architecture

```
 ┌──────────────────────────────────────────────────────────────┐
 │                    Python Script                             │
 │                                                              │
 │  ┌─────────────────┐   Loads Page    ┌────────────────────┐  │
 │  │  Stealth Chrome │ ─────────────→  │  BSE India SPA     │  │
 │  │  (CDP Enabled)  │                 │  (derivatives/1)   │  │
 │  └─────────────────┘                 └────────────────────┘  │
 │          │  CDP captures all                    │             │
 │          │  network responses         Fires XHR requests      │
 │          ↓                                      │             │
 │  ┌────────────────────────────────────────────────────────┐   │
 │  │             BSE Internal APIs (Captured via CDP)       │   │
 │  │  ddlExpiry_New  → Spot Price + 19 Expiry Dates         │   │
 │  │  DerivOptionChain_IV → 184 Strike Rows + Aggregates    │   │
 │  └────────────────────────────────────────────────────────┘   │
 │          │                                                     │
 │          ↓ Pandas DataFrame                                    │
 │  ┌────────────────────────────────────────────────────────┐   │
 │  │           Analytics Engine                             │   │
 │  │  • Black-Scholes Delta (CE & PE)                       │   │
 │  │  • Per-Strike PCR (Put OI / Call OI)                   │   │
 │  │  • Max Call OI → Resistance Level                      │   │
 │  │  • Max Put OI  → Support Level                         │   │
 │  │  • Overall Market PCR                                  │   │
 │  └────────────────────────────────────────────────────────┘   │
 │          │                                                     │
 │          ↓ gspread OAuth2                                      │
 │  ┌──────────────────┐                                         │
 │  │  Google Sheet    │ → Live "Sensex" Tab Dashboard           │
 │  └──────────────────┘                                         │
 └──────────────────────────────────────────────────────────────┘
```

---

## 📊 Output: Google Sheet Column Layout

The script writes **33 columns** per row (one row = one strike price), including the nine added open-interest analytics:

```
Call OI | Call ΔOI | Call Vol | Call IV | Call Δ | Call LTP | Call Chng | 
Call BidQ | Call Bid | Call Ask | Call AskQ | STRIKE PRICE |
Put BidQ | Put Bid | Put Ask | Put AskQ | Put Chng | Put LTP | 
Put IV | Put Δ | Put Vol | Put ΔOI | Put OI | PCR |
Call Sum | Put Sum | Difference | Call Boundary | Put Boundary |
Call Exits | Put Exits | Call ITM | Put ITM
```

The sums aggregate change in open interest across three nearby strikes: the current and next two higher strikes for calls, and the current and next two lower strikes for puts. `Difference` is Call Sum minus Put Sum; a negative value is labeled bullish and a positive value bearish in the near-ATM summary. `Call Exits`/`Put Exits` are set when the corresponding sum or boundary is negative. ITM flags use the analyzer's described far-OTM exit/writing ratio heuristic (greater than 1.5), looking four higher strikes for calls and two lower strikes for puts. Missing offset strikes do not produce an ITM flag.

**Row 1** contains summary metadata (Spot, PCR, Support, Resistance, near-ATM OI signals, Expiry, and ASON timestamp).

---

## 🛠️ Installation & Setup Guide

### Step 1 — Clone this Repository
```bash
git clone https://github.com/YOUR_USERNAME/sensex-option-chain.git
cd sensex-option-chain
```

### Step 2 — Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Google Cloud Credentials Setup

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Create a new project (e.g., `sensex-option-chain`)
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Click on the created account → **Keys → Add Key → JSON** → Download file
6. Save the JSON file to a secure path on your machine
7. Update `JSON_KEYFILE` path in `sensex_option_chain.py`

### Step 4 — Google Sheet Setup

1. Create a new Google Sheet named: **`Live Option Chain`**
2. Add a tab/worksheet named: **`Sensex`**
3. **Share** the sheet with the Service Account email (from your credentials JSON) → Give **Editor** access

### Step 5 — Configure the Script

Open `sensex_option_chain.py` and update these constants at the top:
```python
SHEET_NAME   = 'Live Option Chain'   # Your Google Sheet name
JSON_KEYFILE = r'path\to\your\credentials.json'
REFRESH_SECONDS = 60  # Refresh interval (seconds)
```

### Step 6 — Run
```bash
python sensex_option_chain.py
```

---

## 🧪 Testing

Test individual components before running the full scraper:

```bash
# Test Google Sheets connection & write permissions
python test_sheets.py

# Test BSE network capture (CDP interception diagnostic)
python test_sensex_api.py

# Unit tests for open-interest analytics (no network access required)
python -m unittest test_sensex_analysis.py
```

---

## 📸 Live Console Output (Sample)

```
============================================================
  SENSEX Option Chain Scraper  (BSE India)
  Method   : CDP + Page Interaction (confirmed working)
  Refresh  : every 60s
  Run during 9:15 AM - 3:30 PM IST for live data
  Ctrl+C to stop
============================================================

[09:16:05] ===== SENSEX Option Chain Update =====
> Launching Stealth Chrome...
> Loading BSE SENSEX derivatives page...
  Spot from ddlExpiry_New: 77185.43
  Expiry: 16 Jul 2026  (total 19 available)
  [Strategy B] Triggering page interaction...
  [Trigger] Clicked: 'Option Chain'
  OC rows: 184 | ASON: 16 Jul 2026 | 09:15
> Rows: 184 | Spot: 77185.43 | Expiry: 16 Jul 2026
> Call OI: 1,962,663  Put OI: 1,449,019  PCR: 0.74
> Resistance (Max Call OI): 78000.0  |  Support (Max Put OI): 76000.0
> [SUCCESS] Sheet updated — 184 rows.
> Sleeping 60s...
```

---

## 📁 Project File Structure

```
sensex-option-chain/
│
├── sensex_option_chain.py   # Main production scraper + Google Sheets pipeline
├── test_sensex_api.py       # BSE network capture diagnostic tool
├── test_sheets.py           # Google Sheets connectivity test
├── requirements.txt         # Python dependencies
├── .gitignore               # Excludes credentials and temp files
└── README.md                # This file
```

---

## 🔐 Security Notes

> ⚠️ **NEVER commit your `credentials.json` file to GitHub!**
> The `.gitignore` in this repo already excludes `*.json` files.
> Always store credentials outside your repository or use environment variables.

---

## 📈 Data Source

All market data is sourced directly from **[BSE India](https://www.bseindia.com/)** (Bombay Stock Exchange) via their publicly accessible web interface.

* **Spot Price API**: `api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexDatanew/w`
* **Expiry & Strike Data**: `api.bseindia.com/BseIndiaAPI/api/ddlExpiry_New/w?scrip_cd=1`
* **Option Chain Data**: `api.bseindia.com/BseIndiaAPI/api/DerivOptionChain_IV/w`

---

## 🛡️ Disclaimer

This project is for **educational and portfolio demonstration purposes only**.  
Option trading involves substantial financial risk. The calculations provided (including Black-Scholes Greeks and open-interest trend signals) are heuristic estimates and **should not be used as financial advice**.

---

## 📄 License

This project is open-sourced under the [MIT License](LICENSE).
