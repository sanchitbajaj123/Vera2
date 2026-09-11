"""
make_submission.py — 30 canonical test pairs ke messages banata hai.

Seedha composer call karta hai (tick ke spam-guards ke bina), kyunki
submission file mein har pair ka message chahiye.

Chalao:
    set -a; source .env; set +a
    python make_submission.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vera-bot"))

import store
import trigger

PAIRS = json.load(open("dataset/expanded/test_pairs.json"))["pairs"]


def load(scope, folder, key):
    import glob
    for path in glob.glob(f"dataset/expanded/{folder}/*.json"):
        payload = json.load(open(path))
        store.save(scope, payload[key], 1, payload)


store.clear()
load("category", "categories", "slug")
load("merchant", "merchants", "merchant_id")
load("customer", "customers", "customer_id")
load("trigger", "triggers", "id")
print("loaded:", store.count(), "\n")

rows = []
for pair in PAIRS:
    message = trigger.make_message(pair["trigger_id"])
    if not message:
        print(f"  {pair['test_id']}: FAILED — {pair['trigger_id']}")
        continue

    rows.append({
        "test_id": pair["test_id"],
        "body": message["body"],
        "cta": message["cta"],
        "send_as": message["send_as"],
        "suppression_key": message["suppression_key"],
        "rationale": message["rationale"],
    })
    print(f"  {pair['test_id']}  {message['send_as']:20} {message['body'][:62]}...")

with open("submission.jsonl", "w") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"\nsubmission.jsonl — {len(rows)}/30 lines")
