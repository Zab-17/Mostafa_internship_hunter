"""Quick verdict saver. Usage: python3 save_verdict.py '<json>'"""
import sys, json, sqlite3
from datetime import datetime, timezone

data = json.loads(sys.argv[1])
conn = sqlite3.connect("/Users/zeyadkhaled/Desktop/Mostafa_internship_hunter/db/mostafa.db")
conn.execute(
    "INSERT OR REPLACE INTO seen_jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
    (
        data["url"], data["company"], data["title"], data["verdict"],
        data["reason"], data.get("fit_score", 0), data.get("posted", ""),
        datetime.now(timezone.utc).isoformat(),
        data.get("description", "")[:2000],
        data.get("description_summary", ""),
    ),
)
conn.commit()
conn.close()
print(f"Saved {data['verdict']}: {data['title']} at {data['company']}")
