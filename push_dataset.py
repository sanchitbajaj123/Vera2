"""
push_dataset.py — Judge ki nakal. Poora dataset bot ko bhej deta hai.

Chalao:  ./venv/bin/python push_dataset.py
"""
import json, sys, glob, os, time
import requests

BOT = os.environ.get("BOT_URL", "http://localhost:8080")
D = "dataset/expanded"

def push(scope, cid, payload, tries=3):
    for attempt in range(tries):
        try:
            r = requests.post(f"{BOT}/v1/context", json={
                "scope": scope, "context_id": cid, "version": 1,
                "payload": payload, "delivered_at": "2026-04-26T10:00:00Z"}, timeout=30)
            if r.status_code == 200:
                return r.json().get("accepted")
        except Exception:
            pass
        time.sleep(1)
    print(f"  FAILED after {tries} tries: {scope}/{cid}")
    return False

n = 0
for f in glob.glob(f"{D}/categories/*.json"):
    d = json.load(open(f)); push("category", d["slug"], d); n += 1
for f in glob.glob(f"{D}/merchants/*.json"):
    d = json.load(open(f)); push("merchant", d["merchant_id"], d); n += 1
for f in glob.glob(f"{D}/customers/*.json"):
    d = json.load(open(f)); push("customer", d["customer_id"], d); n += 1

print(f"{n} base contexts bheje")
print(requests.get(f"{BOT}/v1/healthz").json())
