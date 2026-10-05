"""
Test script to verify Google Sheets integration.
Pushes sample/mock SENSEX option chain rows to the spreadsheet
to confirm credentials, sheet name, and connection are 100% working.
"""
import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from sensex_analysis import ANALYSIS_HEADERS

SYMBOL        = 'SENSEX (TEST)'
SHEET_NAME    = 'Live Option Chain'
JSON_KEYFILE  = r'C:\Users\Welcome\OneDrive - y6f4j\Desktop\option_Data\credentials.json'

HEADERS = [
    'Call OI',    'Call Chng OI', 'Call Vol',     'Call IV',     'Call Delta',
    'Call LTP',   'Call Chng',    'Call Bid Qty', 'Call Bid',    'Call Ask', 'Call Ask Qty',
    'Strike Price',
    'Put Bid Qty','Put Bid',      'Put Ask',      'Put Ask Qty',
    'Put Chng',   'Put LTP',      'Put IV',       'Put Delta',
    'Put Vol',    'Put Chng OI',  'Put OI',       'PCR (Strike)'
] + ANALYSIS_HEADERS

def connect_to_sheet():
    scope  = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds  = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet("Sensex")

def push_test_data():
    print("> Connecting to Google Sheets...", flush=True)
    try:
        sheet = connect_to_sheet()
        print("  Connected successfully!", flush=True)
        
        print("> Preparing test SENSEX data...", flush=True)
        # Create 3 mock rows around 77,000 strike
        mock_rows = [
            [15000, 200, 50000, 12.5, 0.65, 120.5, 10.2, 500, 120.0, 121.0, 400, 76800.0, 200, 95.0, 96.0, 300, -8.5, 95.5, 13.2, -0.35, 45000, 150, 12000, 0.8, 500, -100, 600, 300, -150, 'No', 'Yes', 'No', 'No'],
            [25000, -500, 85000, 11.8, 0.50, 65.0, 2.5, 800, 64.5, 65.5, 900, 77000.0, 600, 140.0, 141.0, 700, 12.0, 140.5, 12.4, -0.50, 78000, 400, 28000, 1.12, -300, 450, -750, -200, 400, 'Yes', 'No', 'No', 'No'],
            [12000, 100, 35000, 12.2, 0.35, 30.2, -2.1, 300, 29.8, 30.5, 500, 77200.0, 800, 210.0, 211.0, 400, 22.4, 210.5, 12.9, -0.65, 32000, 300, 34000, 2.83, 100, 700, -600, 50, 300, 'No', 'No', 'No', 'No']
        ]
        
        df = pd.DataFrame(mock_rows, columns=HEADERS)
        
        print("> Clearing sheet and updating...", flush=True)
        sheet.clear()
        
        # Meta info row
        sheet.append_row([
            f"Symbol: {SYMBOL}",
            f"Expiry: 16 Jul 2026 (TEST)",
            f"Spot: 77185.43",
            f"PCR: 1.12",
            f"Support: 77200.0",
            f"Resistance: 77000.0",
            f"TTE: 1 days",
            f"Near-ATM OI Bias: Bullish",
            f"Call Exits: Yes",
            f"Put Exits: No",
            f"Call ITM: No",
            f"Put ITM: No",
            f"Updated: {datetime.datetime.now().strftime('%d-%b-%Y %H:%M:%S')} (TEST CONNECTION)",
        ])
        
        # Headers
        sheet.append_row(HEADERS)
        
        # Data
        sheet.update('A3', df.values.tolist())
        print("[SUCCESS] Sheet has been updated with test data! Check your Google Sheet now.", flush=True)
        
    except Exception as e:
        print(f"[FAIL] Google Sheets update failed: {e}", flush=True)

if __name__ == "__main__":
    push_test_data()
