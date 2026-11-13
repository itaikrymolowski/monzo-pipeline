import json
import os
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# Read credentials from GitHub Secrets
MONZO_ACCOUNT_ID = os.environ["MONZO_ACCOUNT_ID"]
MONZO_ACCESS_TOKEN = os.environ["MONZO_ACCESS_TOKEN"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GCP_SA_KEY_JSON = os.environ["GCP_SA_KEY_JSON"]

# Authenticate with Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds_dict = json.loads(GCP_SA_KEY_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# Verify or add standardized headers
existing_data = sheet.get_all_values()
if not existing_data:
    headers = [
        "Transaction ID",
        "Date",
        "Amount (£)",
        "Category",
        "Name / Payee",
        "Type",
    ]
    sheet.append_row(headers)
    existing_ids = set()
else:
    existing_ids = {row[0] for row in existing_data[1:] if row}

# Fetch transactions from Monzo (last 7 days)
since_date = (datetime.now() - timedelta(days=7)).isoformat() + "Z"
url = f"https://api.monzo.com/transactions?account_id={MONZO_ACCOUNT_ID}&since={since_date}&expand[]=merchant"
headers = {"Authorization": f"Bearer {MONZO_ACCESS_TOKEN}"}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    transactions = response.json().get("transactions", [])
    new_rows = []

    for tx in transactions:
        tx_id = tx["id"]
        if tx_id in existing_ids:
            continue

        amount = tx["amount"] / 100.0
        merchant_obj = tx.get("merchant")
        counterparty = tx.get("counterparty", {})

        if merchant_obj and isinstance(merchant_obj, dict):
            name = merchant_obj.get("name", tx.get("description", ""))
            tx_type = "Card Payment"
        elif counterparty and "name" in counterparty:
            name = counterparty["name"]
            tx_type = "Bank Transfer"
        elif "pot_id" in tx.get("metadata", {}):
            name = f"Pot Transfer: {tx.get('description', 'Savings')}"
            tx_type = "Pot Transfer"
        else:
            name = tx.get("description", "Unknown")
            tx_type = "Other"

        category = tx.get("category", "general")
        created_date = tx.get("created", "")[:10]

        new_rows.append([tx_id, created_date, amount, category, name, tx_type])

    if new_rows:
        sheet.append_rows(new_rows)
        print(f"Success! Appended {len(new_rows)} new rows.")
    else:
        print("Connected successfully, no new transactions.")
else:
    print(f"Monzo API Error: {response.status_code} - {response.text}")
    exit(1)
