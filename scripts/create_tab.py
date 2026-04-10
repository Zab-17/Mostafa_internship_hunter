"""
Create a new worksheet tab with the same schema + beautiful formatting
as 'Mostafa Internships'. Idempotent — safe to run multiple times.

Usage: python3 scripts/create_tab.py "Mostafa Mechatronics"
"""
import sys
from pathlib import Path

import gspread

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import config

HEADERS = ["Scrape Date", "Company", "Job Title", "Posted", "Fit Score",
           "Reason", "Apply URL", "Source", "Job Description"]
COL_WIDTHS = [140, 220, 360, 150, 100, 520, 460, 160, 420]
HEADER_BG = {"red": 0.07, "green": 0.07, "blue": 0.10}
HEADER_FG = {"red": 0.83, "green": 0.66, "blue": 0.35}
ZEBRA_BG  = {"red": 0.97, "green": 0.97, "blue": 0.99}
BORDER    = {"red": 0.85, "green": 0.85, "blue": 0.88}


def main(tab_name: str):
    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_PATH)
    sh = gc.open_by_key(config.GOOGLE_SHEETS_ID)

    try:
        ws = sh.worksheet(tab_name)
        print(f"tab '{tab_name}' exists (rows={ws.row_count})")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=2000, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option="RAW")
        print(f"✅ created tab '{tab_name}'")

    sid = ws.id
    reqs = []

    for i, w in enumerate(COL_WIDTHS):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i+1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}})

    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 56}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 1, "endIndex": 500},
        "properties": {"pixelSize": 96}, "fields": "pixelSize"}})

    reqs.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 0, "endColumnIndex": len(COL_WIDTHS)},
        "cell": {"userEnteredFormat": {
            "backgroundColor": HEADER_BG,
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "wrapStrategy": "WRAP",
            "textFormat": {"foregroundColor": HEADER_FG, "fontFamily": "Inter",
                           "fontSize": 12, "bold": True},
            "padding": {"top": 12, "bottom": 12, "left": 14, "right": 14}}},
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat,padding)"}})
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount"}})

    reqs.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 500,
                  "startColumnIndex": 0, "endColumnIndex": len(COL_WIDTHS)},
        "cell": {"userEnteredFormat": {
            "wrapStrategy": "WRAP", "verticalAlignment": "TOP",
            "horizontalAlignment": "LEFT",
            "textFormat": {"fontFamily": "Inter", "fontSize": 11},
            "padding": {"top": 10, "bottom": 10, "left": 14, "right": 14}}},
        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,horizontalAlignment,textFormat,padding)"}})

    reqs.append({"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 500,
                  "startColumnIndex": 4, "endColumnIndex": 5},
        "cell": {"userEnteredFormat": {
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "textFormat": {"fontFamily": "Inter", "fontSize": 18, "bold": True,
                           "foregroundColor": HEADER_FG}}},
        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat)"}})

    reqs.append({"updateBorders": {
        "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 500,
                  "startColumnIndex": 0, "endColumnIndex": len(COL_WIDTHS)},
        "innerHorizontal": {"style": "SOLID", "width": 1, "color": BORDER},
        "innerVertical":   {"style": "SOLID", "width": 1, "color": BORDER},
        "top":    {"style": "SOLID_MEDIUM", "width": 2, "color": HEADER_BG},
        "bottom": {"style": "SOLID", "width": 1, "color": BORDER},
        "left":   {"style": "SOLID", "width": 1, "color": BORDER},
        "right":  {"style": "SOLID", "width": 1, "color": BORDER}}})

    sh.batch_update({"requests": reqs})
    print(f"✅ formatted '{tab_name}'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/create_tab.py <tab name>")
        sys.exit(1)
    main(sys.argv[1])
