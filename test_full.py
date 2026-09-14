"""
test_full.py — Poora test suite. Har endpoint, har edge case.

Chalao:
    BOT_URL=https://vera-bot-mu.vercel.app python test_full.py
"""
import json
import glob
import os
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BOT = os.environ.get("BOT_URL", "http://localhost:8080")
PASS, FAIL, WARN = [], [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def warn(name, detail=""):
    WARN.append(name)
    print(f"  WARN  {name}" + (f"   [{detail}]" if detail else ""))


def post(path, body, timeout=60):
    t = time.time()
    r = requests.post(f"{BOT}{path}", json=body, timeout=timeout)
    return r, time.time() - t


def get(path, timeout=60):
    t = time.time()
    r = requests.get(f"{BOT}{path}", timeout=timeout)
    return r, time.time() - t


def push(scope, cid, payload, version=1):
    return post("/v1/context", {"scope": scope, "context_id": cid, "version": version,
                                "payload": payload, "delivered_at": "2026-04-26T10:00:00Z"})


print("=" * 74)
print("SECTION 1 — endpoints zinda hain")
print("=" * 74)
post("/v1/teardown", {})

r, dt = get("/v1/healthz")
check("healthz 200", r.status_code == 200)
check("healthz me saare 4 scope", set(r.json().get("contexts_loaded", {})) ==
      {"category", "merchant", "customer", "trigger"})
check("healthz saaf state se shuru", sum(r.json()["contexts_loaded"].values()) == 0)
check(f"healthz < 2s", dt < 2, f"{dt:.2f}s")

r, dt = get("/v1/metadata")
m = r.json()
check("metadata 200", r.status_code == 200)
for f in ["team_name", "team_members", "model", "approach", "contact_email", "version", "submitted_at"]:
    check(f"metadata.{f} hai", f in m and m[f])
check("metadata me TODO nahi", "TODO" not in json.dumps(m))

print()
print("=" * 74)
print("SECTION 2 — /v1/context ke rules")
print("=" * 74)
cat = json.load(open("dataset/expanded/categories/dentists.json"))
mer = json.load(open("dataset/expanded/merchants/m_001_drmeera_dentist_delhi.json"))

r, dt = push("category", "dentists", cat)
check("valid context accepted", r.json().get("accepted") is True)
check("ack_id milta hai", "ack_id" in r.json())
check("stored_at milta hai", "stored_at" in r.json())
check(f"context < 5s (judge budget)", dt < 5, f"{dt:.2f}s")

r, _ = push("category", "dentists", cat, version=1)
check("same version dobara = accepted (no-op)", r.json().get("accepted") is True)

r, _ = push("category", "dentists", cat, version=2)
check("naya version accepted", r.json().get("accepted") is True)

r, _ = push("category", "dentists", cat, version=1)
check("purana version reject", r.json().get("accepted") is False and
      r.json().get("reason") == "stale_version")
check("stale me current_version bhi", r.json().get("current_version") == 2)

r, _ = push("bakwaas_scope", "x", {})
check("galat scope reject", r.json().get("accepted") is False and
      r.json().get("reason") == "invalid_scope")

r, _ = post("/v1/context", {"scope": "merchant"})
check("adhoori body pe crash nahi", r.status_code in (200, 422), f"HTTP {r.status_code}")

print()
print("=" * 74)
print("SECTION 3 — PARTIAL DATA (judge ne pichli baar kam data bheja tha)")
print("=" * 74)
push("merchant", mer["merchant_id"], mer)

orphan = {"id": "trg_orphan", "kind": "test", "merchant_id": "m_koi_nahi",
          "customer_id": None, "payload": {}, "urgency": 3, "suppression_key": "orphan"}
push("trigger", "trg_orphan", orphan)
r, dt = post("/v1/tick", {"now": "x", "available_triggers": ["trg_orphan"]})
check("merchant missing -> crash nahi", r.status_code == 200, f"HTTP {r.status_code}")
check("merchant missing -> 0 actions", len(r.json().get("actions", [])) == 0)
check(f"aur jaldi lauta", dt < 5, f"{dt:.2f}s")

r, _ = post("/v1/tick", {"now": "x", "available_triggers": ["trg_bilkul_anjaan"]})
check("anjaan trigger id -> crash nahi", r.status_code == 200 and r.json().get("actions") == [])

r, _ = post("/v1/tick", {"now": "x", "available_triggers": []})
check("khaali trigger list -> crash nahi", r.status_code == 200 and r.json().get("actions") == [])

r, _ = post("/v1/tick", {})
check("tick bina body -> crash nahi", r.status_code in (200, 422), f"HTTP {r.status_code}")

trg = json.load(open("dataset/expanded/triggers/trg_001_research_digest_dentists.json"))
push("trigger", trg["id"], trg)
r, dt = post("/v1/tick", {"now": "x", "available_triggers": [trg["id"]]})
acts = r.json().get("actions", [])
check("sirf 1 cat + 1 merchant + 1 trigger se bhi message bana", len(acts) == 1, f"{dt:.2f}s")

if acts:
    a = acts[0]
    for f in ["conversation_id", "merchant_id", "customer_id", "send_as", "trigger_id",
              "template_name", "template_params", "body", "cta", "suppression_key", "rationale"]:
        check(f"action.{f} hai", f in a)
    check("body khaali nahi", bool(a["body"].strip()))
    check("body me URL nahi (-3 penalty)", "http" not in a["body"].lower() and "www." not in a["body"].lower())
    check("send_as sahi", a["send_as"] in ("vera", "merchant_on_behalf"))
    check("cta sahi", a["cta"] in ("open_ended", "binary_yes_no", "binary_confirm_cancel",
                                   "multi_choice_slot", "none"))
    check("rationale likha hua", len(a["rationale"]) > 20)

ctrg = json.load(open("dataset/expanded/triggers/trg_003_recall_due_priya.json"))
push("trigger", ctrg["id"], ctrg)
r, _ = post("/v1/tick", {"now": "x", "available_triggers": [ctrg["id"]]})
check("customer trigger, customer push nahi hua -> crash nahi", r.status_code == 200)

cust = json.load(open("dataset/expanded/customers/c_001_priya_for_m001.json"))
push("customer", cust["customer_id"], cust)
ctrg2 = dict(ctrg); ctrg2["id"] = "trg_recall_2"; ctrg2["suppression_key"] = "recall2"
push("trigger", "trg_recall_2", ctrg2)
r, _ = post("/v1/tick", {"now": "x", "available_triggers": ["trg_recall_2"]})
acts = r.json().get("actions", [])
if acts:
    check("customer message send_as=merchant_on_behalf", acts[0]["send_as"] == "merchant_on_behalf")
    check("customer message me customer_id", bool(acts[0]["customer_id"]))
else:
    warn("customer-facing message is tick me nahi aaya (cooldown ho sakta hai)")

print()
print("=" * 74)
print("SECTION 4 — /v1/reply ke saare case")
print("=" * 74)
M = mer["merchant_id"]


def reply(conv, msg, turn=2, role="merchant"):
    r, dt = post("/v1/reply", {"conversation_id": conv, "merchant_id": M, "customer_id": None,
                               "from_role": role, "message": msg, "received_at": "x",
                               "turn_number": turn})
    return r.json(), dt


d, dt = reply("t_no", "Not interested, stop messaging me")
check("hard no -> end", d.get("action") == "end", f"{dt:.2f}s")
check("end me rationale", bool(d.get("rationale")))

d, _ = reply("t_no2", "Bhai band karo ye sab")
check("hindi me mana -> end", d.get("action") == "end")

d, _ = reply("t_hostile", "Why are you bothering me. This is useless spam.")
check("gaali -> end", d.get("action") == "end")

AUTO = "Thank you for contacting us! Our team will respond shortly."
d1, _ = reply("t_auto", AUTO, 2)
d2, _ = reply("t_auto", AUTO, 3)
d3, _ = reply("t_auto", AUTO, 4)
check("auto-reply 1 -> send", d1.get("action") == "send")
check("auto-reply 2 -> wait", d2.get("action") == "wait")
check("auto-reply 2 me wait_seconds", isinstance(d2.get("wait_seconds"), int))
check("auto-reply 3 -> end", d3.get("action") == "end")

d, dt = reply("t_yes", "Ok lets do it. Whats next?")
body = (d.get("body") or "").lower()
check("commit -> send", d.get("action") == "send")
check("commit -> action words", any(w in body for w in ["done", "draft", "sending", "confirm", "next", "here"]))
check("commit -> koi naya sawaal nahi",
      not any(w in body for w in ["would you", "do you", "can you tell", "what if", "how about"]))
check(f"commit reply fast", dt < 5, f"{dt:.2f}s")

d, _ = reply("t_hi", "Haan bhejo")
check("hinglish haan -> send", d.get("action") == "send")

d, dt = reply("t_gst", "Btw can you also help me with my GST filing this month?")
check("off-topic -> send (mission pe wapas)", d.get("action") == "send", f"{dt:.2f}s")
check("off-topic reply me URL nahi", "http" not in (d.get("body") or "").lower())

d, _ = reply("t_q", "What exactly will you change on my profile?")
check("sawaal -> send", d.get("action") == "send")
check("sawaal ka jawab action-mode nahi",
      "draft bana rahi" not in (d.get("body") or "").lower())

d, _ = reply("t_unknown_conv_xyz", "Hello?")
check("anjaan conversation_id -> crash nahi", d.get("action") in ("send", "wait", "end"))

d, _ = reply("t_empty", "")
check("khaali message -> crash nahi", d.get("action") in ("send", "wait", "end"))

d, _ = reply("t_long", "hello " * 500)
check("bahut lamba message -> crash nahi", d.get("action") in ("send", "wait", "end"))

d, _ = reply("t_cust", "Yes Wednesday works", role="customer")
check("from_role=customer -> crash nahi", d.get("action") in ("send", "wait", "end"))

r, _ = post("/v1/reply", {"conversation_id": "t_min"})
check("reply adhoori body -> crash nahi", r.status_code in (200, 422), f"HTTP {r.status_code}")

print()
print("=" * 74)
print("SECTION 5 — load aur latency (judge 10 req/s tak maar sakta hai)")
print("=" * 74)
post("/v1/teardown", {})

files = sorted(glob.glob("dataset/expanded/customers/*.json"))[:40]


def push_one(f):
    d = json.load(open(f))
    t = time.time()
    try:
        r = requests.post(f"{BOT}/v1/context", json={"scope": "customer", "context_id": d["customer_id"],
                          "version": 1, "payload": d, "delivered_at": "x"}, timeout=30)
        return r.status_code, time.time() - t
    except Exception:
        return "ERR", time.time() - t


t0 = time.time()
with ThreadPoolExecutor(max_workers=10) as pool:
    res = list(pool.map(push_one, files))
codes = {}
for c, _ in res:
    codes[c] = codes.get(c, 0) + 1
times = sorted(d for _, d in res)
check("40 concurrent context push, sab 200", codes.get(200) == 40, str(codes))
check("koi bhi 5s se slow nahi", times[-1] < 5, f"max {times[-1]:.2f}s")

r, dt = get("/v1/healthz")
check("load ke baad healthz thik", r.status_code == 200 and dt < 2, f"{dt:.2f}s")

print()
print("=" * 74)
print("SECTION 6 — poora tick cycle (judge jaisa)")
print("=" * 74)
post("/v1/teardown", {})
for f in glob.glob("dataset/expanded/categories/*.json"):
    d = json.load(open(f)); push("category", d["slug"], d)
for f in sorted(glob.glob("dataset/expanded/merchants/*.json"))[:12]:
    d = json.load(open(f)); push("merchant", d["merchant_id"], d)
for f in sorted(glob.glob("dataset/expanded/customers/*.json"))[:8]:
    d = json.load(open(f)); push("customer", d["customer_id"], d)
ids = []
for f in sorted(glob.glob("dataset/expanded/triggers/*.json"))[:12]:
    d = json.load(open(f)); push("trigger", d["id"], d); ids.append(d["id"])

total_actions = 0
slow = 0
bodies = []
for run in range(1, 13):
    r, dt = post("/v1/tick", {"now": "x", "available_triggers": ids})
    acts = r.json().get("actions", [])
    total_actions += len(acts)
    bodies += [a["body"] for a in acts]
    if dt >= 10:
        slow += 1
    print(f"    tick {run:2}: {dt:5.2f}s  actions={len(acts)}")

check("12 tick me kam se kam 5 message gaye", total_actions >= 5, f"{total_actions} messages")
check("koi tick 10s se slow nahi", slow == 0, f"{slow} slow")
check("koi message repeat nahi", len(bodies) == len(set(bodies)))
check("kisi message me URL nahi", not any("http" in b.lower() or "www." in b.lower() for b in bodies))
check("har message me koi number hai (specificity)",
      all(any(ch.isdigit() for ch in b) for b in bodies))

print()
print("=" * 74)
print("SECTION 7 — teardown")
print("=" * 74)
r, dt = post("/v1/teardown", {})
check("teardown 200", r.status_code == 200)
r, _ = get("/v1/healthz")
check("teardown ke baad sab 0", sum(r.json()["contexts_loaded"].values()) == 0)

print()
print("=" * 74)
print(f"RESULT:  {len(PASS)} PASS   {len(FAIL)} FAIL   {len(WARN)} WARN")
print("=" * 74)
if FAIL:
    print("\nFAILURES:")
    for f in FAIL:
        print("  -", f)
if WARN:
    print("\nWARNINGS:")
    for w in WARN:
        print("  -", w)
raise SystemExit(1 if FAIL else 0)
