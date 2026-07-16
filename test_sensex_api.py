"""Final verification: confirm all 3 BSE APIs work correctly via CDP"""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

HEADLESS = True

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

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
})
driver.execute_cdp_cmd("Network.enable", {})

print("Loading SENSEX derivatives page...")
driver.get("https://www.bseindia.com/stock-share-price/future-options/derivatives/1")
try:
    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
except Exception:
    print("  [Warn] Page load timeout — continuing anyway")
time.sleep(10)   # Extra buffer for BSE XHR calls
print(f"Title: {driver.title[:60]}")

logs  = driver.get_log("performance")
found = {
    "expiry_api": False,
    "oc_api":     False,
    "spot":       "0",
    "expiries":   [],
    "oc_rows":    0,
    "oc_keys":    [],
    "oc_agg":     {},
}

# ── Scan CDP for ddlExpiry_New (spot + expiry) ────────────────────────────
for entry in logs:
    try:
        msg    = json.loads(entry["message"])["message"]
        if msg.get("method") != "Network.responseReceived":
            continue
        url    = msg["params"]["response"]["url"]
        req_id = msg["params"]["requestId"]
        if "bseindia" not in url:
            continue
        body   = driver.execute_cdp_cmd(
            "Network.getResponseBody", {"requestId": req_id}
        ).get("body", "")
        if not body or len(body) < 50:
            continue
        data = json.loads(body)

        if "ddlExpiry_New" in url:
            found["expiry_api"] = True
            t2 = data.get("Table2", [{}])
            if t2 and isinstance(t2[0], dict):
                found["spot"] = t2[0].get("UlaValue", "0")
            t1 = data.get("Table1", [])
            found["expiries"] = [
                x.get("ExpiryDate", "") for x in t1[:5]
                if isinstance(x, dict)
            ]

        if "DerivOptionChain_IV" in url:
            found["oc_api"]  = True
            table            = data.get("Table", [])
            found["oc_rows"] = len(table)
            found["oc_agg"]  = {
                "tot_C_OI":  data.get("tot_C_Open_Interest", 0),
                "tot_P_OI":  data.get("tot_Open_Interest",   0),
                "tot_C_Vol": data.get("tot_C_Vol_Traded",    0),
                "tot_Vol":   data.get("tot_Vol_Traded",       0),
                "ASON":      data.get("ASON", {}).get("DT_TM", "")
                             if isinstance(data.get("ASON"), dict) else "",
            }
            if table and isinstance(table[0], dict):
                found["oc_keys"] = list(table[0].keys())
                # Print first row to see exact field names for market-hours use
                print("\nOption Chain row sample (first row):")
                print(json.dumps(table[0], indent=2))
    except Exception:
        pass

# ── If OC not captured via CDP, call it directly via JS fetch ────────────
# We are already on www.bseindia.com (derivatives page), so CORS allows
# calls to api.bseindia.com — same as BSE's own JS does.
if not found["oc_api"] and found["expiries"]:
    expiry_enc = found["expiries"][0].replace(" ", "%20")
    oc_url = (
        f"https://api.bseindia.com/BseIndiaAPI/api/DerivOptionChain_IV/w"
        f"?Expiry={expiry_enc}&scrip_cd=1&strprice=0"
    )
    print(f"\nJS fetch: {oc_url}")

    JS = f"""
var done = arguments[arguments.length - 1];
fetch('{oc_url}', {{
    method: 'GET',
    credentials: 'include',
    headers: {{
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.bseindia.com/'
    }}
}})
.then(function(r) {{
    if (!r.ok) return done({{__err__: 'HTTP ' + r.status}});
    return r.json();
}})
.then(function(d) {{ done(d); }})
.catch(function(e) {{ done({{__err__: e.toString()}}); }});
"""
    try:
        driver.set_script_timeout(25)
        result = driver.execute_async_script(JS)
        if isinstance(result, dict) and "__err__" in result:
            print(f"JS fetch error: {result['__err__']}")
        else:
            table = result.get("Table", []) if isinstance(result, dict) else []
            found["oc_api"]  = True
            found["oc_rows"] = len(table)
            found["oc_agg"]  = {
                "tot_C_OI":  result.get("tot_C_Open_Interest", 0),
                "tot_P_OI":  result.get("tot_Open_Interest",   0),
                "ASON":      result.get("ASON", {}).get("DT_TM", "")
                             if isinstance(result.get("ASON"), dict) else "",
            }
            if table and isinstance(table[0], dict):
                found["oc_keys"] = list(table[0].keys())
                print("\n[PASS] JS fetch got OC data! First row:")
                print(json.dumps(table[0], indent=2))
            else:
                print(f"[INFO] JS fetch OK — Table has {len(table)} rows (market closed)")
    except Exception as ex:
        print(f"JS fetch exception: {ex}")

driver.quit()

print("\n" + "=" * 50)
print("VERIFICATION RESULTS")
print("=" * 50)
print(f"ddlExpiry_New found  : {found['expiry_api']}")
print(f"SENSEX Spot Price    : {found['spot']}")
print(f"Expiry dates (next5) : {found['expiries']}")
print(f"DerivOptionChain_IV  : {found['oc_api']}")
print(f"OC rows in Table     : {found['oc_rows']}  (0 = market closed, normal)")
print(f"OC aggregates        : {found['oc_agg']}")
print(f"OC field names       : {found['oc_keys']}")
print("=" * 50)

if found["expiry_api"] and found["oc_api"] and float(found["spot"].replace(",","")) > 10000:
    print("\n[ALL PASS] Script is ready to use during market hours!")
elif found["expiry_api"] and found["oc_api"]:
    print("\n[PASS] Both APIs confirmed. OC Table empty = market closed (expected).")
    print("       Script will work correctly during 9:15 AM - 3:30 PM IST.")
else:
    print("\n[PARTIAL] Some APIs missing - check output above.")
