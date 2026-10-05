import os
import subprocess
import warnings
import re
import time
import datetime
import json

warnings.filterwarnings("ignore", category=UserWarning, module="gspread")
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT DETECTION
# ─────────────────────────────────────────────────────────────────────────────
IS_COLAB = False
try:
    from google.colab import drive
    drive.mount('/content/drive')
    IS_COLAB = True
    print("> Running in Google Colab environment")
    try:
        import selenium
    except ImportError:
        subprocess.run([
            'pip', 'install', '-q',
            'selenium', 'webdriver-manager',
            'gspread', 'oauth2client',
            'pandas', 'scipy'
        ], check=True)
    os.system('wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -')
    os.system('echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" '
              '> /etc/apt/sources.list.d/google-chrome.list')
    os.system('apt-get update -qq && apt-get install -y google-chrome-stable -qq')
except ModuleNotFoundError:
    print("> Running in Local environment")

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import pandas as pd
import numpy as np
from scipy.stats import norm
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from sensex_analysis import ANALYSIS_HEADERS, add_oi_analysis

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
SYMBOL          = 'SENSEX'
SHEET_NAME      = 'Live Option Chain'
JSON_KEYFILE    = (
    '/content/drive/MyDrive/FnO/credentials.json'
    if IS_COLAB else
    r'C:\Users\Welcome\OneDrive - y6f4j\Desktop\option_Data\credentials.json'
)
REFRESH_SECONDS = 60
HEADLESS_MODE   = True

# ── Confirmed BSE endpoints (verified via CDP network interception) ──────────
#
#  Page that loads all required APIs automatically:
BSE_SENSEX_PAGE = "https://www.bseindia.com/stock-share-price/future-options/derivatives/1"
#
#  API 1 — Expiry list + Spot price  (always called on page load):
#    ddlExpiry_New/w?scrip_cd=1
#      Table  → [{StrikePrice: "66,500.00"}, ...]        (195 strikes)
#      Table1 → [{ExpiryDate: "16 Jul 2026"}, ...]       (19 expiry dates)
#      Table2 → [{UlaValue: "77185.43", DisplayIndexName: "BSE SENSEX"}]
#
#  API 2 — Option Chain with IV  (called by page JS or via JS fetch):
#    DerivOptionChain_IV/w?Expiry=16%20Jul%202026&scrip_cd=1&strprice=0
#      Table  → 184 rows, field names confirmed below
#      tot_C_Open_Interest, tot_Open_Interest  (aggregates)
#      ASON   → {DT_TM: "15 Jul 2026 | 15:30"}

# ── Confirmed field names from DerivOptionChain_IV (verified 15-Jul-2026) ────
#  CALL:  C_Open_Interest, C_Absolute_Change_OI, C_Last_Trd_Price,
#         C_NetChange, C_Vol_Traded, C_BIdQty, C_BidPrice,
#         C_OfferPrice, C_OfferQty, C_IV
#  STRIKE: Strike_Price (formatted "66,600.00") / Strike_Price1 (raw "66600.00")
#  PUT:   Open_Interest, Absolute_Change_OI, Last_Trd_Price,
#         NetChange, Vol_Traded, BIdQty, BidPrice,
#         OfferPrice, OfferQty, IV


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def parse(val):
    s = str(val).strip().replace(',', '')
    if s in ('', '-', '--', 'nan', 'N/A', 'NA', 'None', 'null'):
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def calculate_delta(S, K, T, r=0.10, sigma=0.0, option_type='CE'):
    if T <= 0 or sigma <= 0 or K <= 0 or S <= 0:
        return 0.0
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        return float(norm.cdf(d1) if option_type == 'CE' else norm.cdf(d1) - 1.0)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────────────────
def connect_to_sheet():
    scope  = ["https://spreadsheets.google.com/feeds",
              "https://www.googleapis.com/auth/drive"]
    creds  = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet("Sensex")


# ─────────────────────────────────────────────────────────────────────────────
# STEALTH CHROME (with performance logging for CDP capture)
# ─────────────────────────────────────────────────────────────────────────────
def build_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    if not HEADLESS_MODE:
        # Remove headless for debugging
        opts.arguments[:] = [a for a in opts.arguments if "headless" not in a]

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    })
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


# ─────────────────────────────────────────────────────────────────────────────
# CDP NETWORK SCANNER
# ─────────────────────────────────────────────────────────────────────────────
def scan_cdp(driver, keyword: str, min_size: int = 50):
    """Return first parsed JSON response whose URL contains keyword."""
    seen = set()
    try:
        logs = driver.get_log("performance")
    except Exception:
        return None
    for entry in logs:
        try:
            msg    = json.loads(entry["message"])["message"]
            if msg.get("method") != "Network.responseReceived":
                continue
            url    = msg["params"]["response"]["url"]
            req_id = msg["params"]["requestId"]
            if keyword.lower() not in url.lower() or req_id in seen:
                continue
            seen.add(req_id)
            body = driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": req_id}
            ).get("body", "")
            if len(body) >= min_size:
                return json.loads(body)
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# XHR FETCH  (more reliable than fetch() in headless Chrome for cross-subdomain)
# ─────────────────────────────────────────────────────────────────────────────
_JS_XHR = """
var done = arguments[arguments.length - 1];
var xhr = new XMLHttpRequest();
xhr.open('GET', '{url}', true);
xhr.withCredentials = true;
xhr.setRequestHeader('Accept', 'application/json, text/plain, * /*');
xhr.setRequestHeader('Referer', 'https://www.bseindia.com/');
xhr.onreadystatechange = function() {{
    if (xhr.readyState === 4) {{
        if (xhr.status === 200) {{
            try {{ done(JSON.parse(xhr.responseText)); }}
            catch(e) {{ done({{__err__: 'parse: ' + e}}); }}
        }} else {{
            done({{__err__: 'HTTP ' + xhr.status}});
        }}
    }}
}};
xhr.onerror = function() {{ done({{__err__: 'XHR network error'}}); }};
xhr.ontimeout = function() {{ done({{__err__: 'XHR timeout'}}); }};
xhr.timeout = 20000;
xhr.send();
"""

def xhr_fetch(driver, url, timeout=25):
    """Execute XHR inside browser context — uses browser's own session/cookies."""
    try:
        driver.set_script_timeout(timeout)
        # Remove whitespace in mime-type header if needed
        script_content = _JS_XHR.replace('* /*', '*/*').format(url=url)
        result = driver.execute_async_script(script_content)
        if isinstance(result, dict) and "__err__" in result:
            print(f"  [XHR error] {result['__err__']}", flush=True)
            return None
        return result
    except Exception as e:
        print(f"  [XHR exception] {e}", flush=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PAGE INTERACTION — scroll + trigger expiry dropdown to force API call
# ─────────────────────────────────────────────────────────────────────────────
def trigger_oc_api(driver):
    """
    Scroll the BSE page and interact with elements to force
    DerivOptionChain_IV to be called by BSE's own JavaScript.
    """
    try:
        # Scroll down to reveal the option chain section (lazy loading)
        for scroll_y in [300, 600, 900, 1200]:
            driver.execute_script(f"window.scrollTo(0, {scroll_y});")
            time.sleep(0.5)
        time.sleep(2)

        # Try to find and click "Option Chain" tab or button
        for selector in [
            "a[href*='option']", "button[data-tab*='option']",
            ".option-chain-tab", "#optionChainTab", "[id*='option'][id*='tab']",
            "li.nav-item a[href*='opt']", ".nav-tabs a",
        ]:
            try:
                els = driver.find_elements(
                    __import__("selenium").webdriver.common.by.By.CSS_SELECTOR,
                    selector
                )
                for el in els:
                    txt = el.text.strip().lower()
                    if "option" in txt or "chain" in txt:
                        driver.execute_script("arguments[0].click();", el)
                        print(f"  [Trigger] Clicked: '{el.text.strip()}'", flush=True)
                        time.sleep(3)
                        break
            except Exception:
                pass

        # Try dispatching change event on any select (expiry dropdown)
        driver.execute_script("""
            var sels = document.querySelectorAll('select');
            for(var i=0; i<sels.length; i++){
                sels[i].dispatchEvent(new Event('change', {bubbles:true}));
            }
        """)
        time.sleep(3)

    except Exception as e:
        print(f"  [Trigger warn] {e}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# PARSE DerivOptionChain_IV response → clean DataFrame
# Field names confirmed via CDP on 15-Jul-2026
# ─────────────────────────────────────────────────────────────────────────────
def parse_oc_table(table: list) -> pd.DataFrame:
    if not table:
        return pd.DataFrame()

    rows = []
    for item in table:
        if not isinstance(item, dict):
            continue
        try:
            rows.append({
                # ── CALL ────────────────────────────────────────────────────
                'Call OI':         parse(item.get('C_Open_Interest',       0)),
                'Call Chng in OI': parse(item.get('C_Absolute_Change_OI',  0)),
                'Call Volume':     parse(item.get('C_Vol_Traded',           0)),
                'Call IV':         parse(item.get('C_IV',                   0)),
                'Call LTP':        parse(item.get('C_Last_Trd_Price',       0)),
                'Call Chng':       parse(item.get('C_NetChange',            0)),
                'Call Bid Qty':    parse(item.get('C_BIdQty',               0)),
                'Call Bid':        parse(item.get('C_BidPrice',             0)),
                'Call Ask':        parse(item.get('C_OfferPrice',           0)),
                'Call Ask Qty':    parse(item.get('C_OfferQty',             0)),
                # ── STRIKE ──────────────────────────────────────────────────
                # Strike_Price1 = unformatted (no commas), more reliable
                'Strike Price':    parse(item.get('Strike_Price1',
                                         item.get('Strike_Price', 0))),
                # ── PUT ─────────────────────────────────────────────────────
                'Put Bid Qty':     parse(item.get('BIdQty',                 0)),
                'Put Bid':         parse(item.get('BidPrice',               0)),
                'Put Ask':         parse(item.get('OfferPrice',             0)),
                'Put Ask Qty':     parse(item.get('OfferQty',             0)),
                'Put Chng':        parse(item.get('NetChange',              0)),
                'Put LTP':         parse(item.get('Last_Trd_Price',         0)),
                'Put IV':          parse(item.get('IV',                     0)),
                'Put Volume':      parse(item.get('Vol_Traded',             0)),
                'Put Chng in OI':  parse(item.get('Absolute_Change_OI',    0)),
                'Put OI':          parse(item.get('Open_Interest',          0)),
            })
        except Exception as e:
            print(f"    [Row skip] {e}", flush=True)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[df['Strike Price'] > 0].reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FETCH ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────
def fetch_live_data():
    print("> Launching Stealth Chrome...", flush=True)
    driver = build_driver()
    oc_df      = None
    spot_price = 0.0
    expiry     = None
    ason_time  = ""
    agg        = {}

    try:
        # ── Load SENSEX derivatives page ─────────────────────────────────
        print(f"> Loading BSE SENSEX derivatives page...", flush=True)
        driver.get(BSE_SENSEX_PAGE)
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            print("  [Warn] Page load timeout — continuing", flush=True)
        time.sleep(10)   # Allow all XHR calls to complete

        # ── API 1: ddlExpiry_New — spot + expiry list (CDP) ──────────────
        expiry_data = scan_cdp(driver, "ddlExpiry_New", min_size=200)
        if expiry_data:
            t2 = expiry_data.get('Table2', [{}])
            if t2 and isinstance(t2[0], dict):
                spot_price = parse(t2[0].get('UlaValue', 0))
                print(f"  Spot from ddlExpiry_New: {spot_price}", flush=True)

            t1 = expiry_data.get('Table1', [])
            expiries = [x.get('ExpiryDate', '').strip()
                        for x in t1 if isinstance(x, dict) and x.get('ExpiryDate')]
            if expiries:
                expiry = expiries[0]
                print(f"  Expiry: {expiry}  (total {len(expiries)} available)", flush=True)
        else:
            print("  [Warn] ddlExpiry_New not found in CDP log", flush=True)

        # ── API 2: DerivOptionChain_IV — option chain ────────────────────
        # Step A: Try CDP (page may have auto-called it)
        oc_raw = scan_cdp(driver, "DerivOptionChain_IV", min_size=100)

        # Step B: If not in CDP, trigger page interaction to force it naturally
        if oc_raw is None:
            print("  [Strategy B] Triggering page interaction...", flush=True)
            trigger_oc_api(driver)
            oc_raw = scan_cdp(driver, "DerivOptionChain_IV", min_size=100)

        # Step C: If still not in CDP, call it directly via XHR fetch
        if oc_raw is None and expiry:
            expiry_enc = expiry.replace(" ", "%20")
            oc_url     = (
                f"https://api.bseindia.com/BseIndiaAPI/api/DerivOptionChain_IV/w"
                f"?Expiry={expiry_enc}&scrip_cd=1&strprice=0"
            )
            print(f"  [Strategy C] XHR: {oc_url}", flush=True)
            oc_raw = xhr_fetch(driver, oc_url, timeout=30)

        # ── Parse option chain response ───────────────────────────────────
        if isinstance(oc_raw, dict):
            table     = oc_raw.get('Table', [])
            ason_info = oc_raw.get('ASON', {})
            ason_time = ason_info.get('DT_TM', '') if isinstance(ason_info, dict) else ''
            agg = {
                'tot_C_OI':  parse(oc_raw.get('tot_C_Open_Interest', 0)),
                'tot_P_OI':  parse(oc_raw.get('tot_Open_Interest',   0)),
                'tot_C_Vol': parse(oc_raw.get('tot_C_Vol_Traded',    0)),
                'tot_Vol':   parse(oc_raw.get('tot_Vol_Traded',       0)),
            }
            print(f"  OC rows: {len(table)} | ASON: {ason_time}", flush=True)
            if table:
                oc_df = parse_oc_table(table)
            else:
                print("  [Info] Market closed — OC Table is empty (aggregates still valid)", flush=True)

        # ── Spot fallback: from UlaValue in OC rows ───────────────────────
        if spot_price == 0.0 and oc_raw and isinstance(oc_raw, dict):
            for row in oc_raw.get('Table', []):
                sp = parse(row.get('UlaValue', 0))
                if sp > 10000:
                    spot_price = sp
                    print(f"  Spot from OC UlaValue: {sp}", flush=True)
                    break

        # ── Expiry fallback ───────────────────────────────────────────────
        if not expiry:
            today      = datetime.date.today()
            days       = (1 - today.weekday()) % 7   # Tuesday
            days       = days if days > 0 else 7
            near_tue   = today + datetime.timedelta(days=days)
            expiry     = near_tue.strftime("%d %b %Y")
            print(f"  Expiry fallback: {expiry}", flush=True)

        return oc_df, spot_price, expiry, ason_time, agg

    except Exception as e:
        print(f"[fetch_live_data error] {e}", flush=True)
        return None, 0.0, "unknown", "", {}
    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS + PUSH TO GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────────────────
BASE_HEADERS = [
    'Call OI',    'Call Chng OI', 'Call Vol',     'Call IV',     'Call Delta',
    'Call LTP',   'Call Chng',    'Call Bid Qty', 'Call Bid',    'Call Ask', 'Call Ask Qty',
    'Strike Price',
    'Put Bid Qty','Put Bid',      'Put Ask',      'Put Ask Qty',
    'Put Chng',   'Put LTP',      'Put IV',       'Put Delta',
    'Put Vol',    'Put Chng OI',  'Put OI',       'PCR (Strike)'
]
HEADERS = BASE_HEADERS + ANALYSIS_HEADERS


def update_dashboard():
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"\n[{ts}] ===== SENSEX Option Chain Update =====", flush=True)

    df, spot_price, expiry, ason_time, agg = fetch_live_data()

    if df is None or df.empty:
        print("> No option chain data. Market may be closed.", flush=True)
        print(f"  Spot={spot_price}  Expiry={expiry}  ASON={ason_time}", flush=True)
        return

    print(f"> Rows: {len(df)} | Spot: {spot_price} | Expiry: {expiry}", flush=True)

    # Time to expiry
    try:
        exp_date = datetime.datetime.strptime(expiry, "%d %b %Y").date()
        tte_days = max((exp_date - datetime.date.today()).days, 0)
    except Exception:
        tte_days = 1
    T = max(tte_days, 1) / 365.0

    # Build clean rows with Greeks + per-strike PCR
    clean_rows = []
    for _, row in df.iterrows():
        try:
            strike  = parse(row.get('Strike Price', 0))
            if strike <= 0:
                continue
            c_iv    = parse(row.get('Call IV',  0))
            p_iv    = parse(row.get('Put IV',   0))
            c_oi    = parse(row.get('Call OI',  0))
            p_oi    = parse(row.get('Put OI',   0))
            c_delta = calculate_delta(spot_price, strike, T, 0.10, c_iv / 100.0, 'CE')
            p_delta = calculate_delta(spot_price, strike, T, 0.10, p_iv / 100.0, 'PE')
            pcr     = round(p_oi / c_oi, 2) if c_oi > 0 else 0.0

            clean_rows.append([
                c_oi,
                parse(row.get('Call Chng in OI', 0)),
                parse(row.get('Call Volume',     0)),
                c_iv,   round(c_delta, 4),
                parse(row.get('Call LTP',        0)),
                parse(row.get('Call Chng',       0)),
                parse(row.get('Call Bid Qty',    0)),
                parse(row.get('Call Bid',        0)),
                parse(row.get('Call Ask',        0)),
                parse(row.get('Call Ask Qty',    0)),
                strike,
                parse(row.get('Put Bid Qty',     0)),
                parse(row.get('Put Bid',         0)),
                parse(row.get('Put Ask',         0)),
                parse(row.get('Put Ask Qty',     0)),
                parse(row.get('Put Chng',        0)),
                parse(row.get('Put LTP',         0)),
                p_iv,   round(p_delta, 4),
                parse(row.get('Put Volume',      0)),
                parse(row.get('Put Chng in OI',  0)),
                p_oi,   pcr,
            ])
        except Exception as e:
            print(f"  [Row skip] {e}", flush=True)

    final_df = pd.DataFrame(clean_rows, columns=BASE_HEADERS)
    final_df = add_oi_analysis(final_df)

    if final_df.empty:
        print("[Warning] All strikes filtered out (market may be closed).", flush=True)
        return

    # Summary stats — prefer BSE's own aggregates, fallback to sum
    total_c_oi  = agg.get('tot_C_OI') or final_df['Call OI'].sum()
    total_p_oi  = agg.get('tot_P_OI') or final_df['Put OI'].sum()
    overall_pcr = round(total_p_oi / total_c_oi, 2) if total_c_oi > 0 else 0.0
    resistance  = final_df.loc[final_df['Call OI'].idxmax(), 'Strike Price']
    support     = final_df.loc[final_df['Put OI'].idxmax(),  'Strike Price']
    if spot_price > 0:
        atm_index = (final_df['Strike Price'] - spot_price).abs().idxmin()
        atm_row = final_df.loc[atm_index]
        oi_bias = (
            'Bullish' if atm_row['Difference'] < 0 else
            'Bearish' if atm_row['Difference'] > 0 else
            'Sideways'
        )
        atm_signals = {
            'Call Exits': atm_row['Call Exits'],
            'Put Exits': atm_row['Put Exits'],
            'Call ITM': atm_row['Call ITM'],
            'Put ITM': atm_row['Put ITM'],
        }
    else:
        oi_bias = 'Unavailable'
        atm_signals = {key: 'Unavailable' for key in (
            'Call Exits', 'Put Exits', 'Call ITM', 'Put ITM'
        )}

    print(f"> Call OI: {int(total_c_oi):,}  Put OI: {int(total_p_oi):,}  PCR: {overall_pcr}", flush=True)
    print(f"> Resistance (Max Call OI): {resistance}  |  Support (Max Put OI): {support}", flush=True)
    print(
        f"> Near-ATM OI bias: {oi_bias} | Call exits: {atm_signals['Call Exits']} "
        f"| Put exits: {atm_signals['Put Exits']}",
        flush=True
    )

    # Push to Google Sheet
    try:
        sheet = connect_to_sheet()
        sheet.clear()
        sheet.append_row([
            f"Symbol: {SYMBOL}",
            f"Expiry: {expiry}",
            f"Spot: {spot_price}",
            f"PCR: {overall_pcr}",
            f"Support: {support}",
            f"Resistance: {resistance}",
            f"TTE: {tte_days} days",
            f"Near-ATM OI Bias: {oi_bias}",
            f"Call Exits: {atm_signals['Call Exits']}",
            f"Put Exits: {atm_signals['Put Exits']}",
            f"Call ITM: {atm_signals['Call ITM']}",
            f"Put ITM: {atm_signals['Put ITM']}",
            f"ASON: {ason_time}",
            f"Updated: {datetime.datetime.now().strftime('%d-%b-%Y %H:%M:%S')}",
        ])
        sheet.append_row(HEADERS)
        sheet.update('A3', final_df.values.tolist())
        print(f"> [SUCCESS] Sheet updated — {len(final_df)} rows.", flush=True)
    except Exception as e:
        print(f"[Sheet Error] {e}", flush=True)
        print(final_df.to_string(), flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("  SENSEX Option Chain Scraper  (BSE India)", flush=True)
    print("  Method   : CDP + JS fetch (confirmed working)", flush=True)
    print(f"  Refresh  : every {REFRESH_SECONDS}s", flush=True)
    print("  Run during 9:15 AM - 3:30 PM IST for live data", flush=True)
    print("  Ctrl+C to stop", flush=True)
    print("=" * 60, flush=True)
    try:
        while True:
            update_dashboard()
            print(f"\n> Sleeping {REFRESH_SECONDS}s...\n", flush=True)
            time.sleep(REFRESH_SECONDS)
    except KeyboardInterrupt:
        print("\n> Stopped.", flush=True)
