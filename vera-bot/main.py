import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import FastAPI

import store
import trigger
import reply
from schemas import ContextBody, TickBody, ReplyBody

app = FastAPI(title="Vera 2.0")
STARTED_AT = time.time()

SENT_KEYS = set()
LAST_TICK = {}
TICK_NUMBER = [0]
MAX_PER_TICK = 3


def now():
    return datetime.now(timezone.utc).isoformat()


@app.post("/v1/context")
def push_context(body: ContextBody):
    ok, reason, current = store.save(body.scope, body.context_id, body.version, body.payload)

    if reason == "invalid_scope":
        return {"accepted": False, "reason": "invalid_scope", "details": body.scope}
    if not ok:
        return {"accepted": False, "reason": "stale_version", "current_version": current}

    return {"accepted": True, "ack_id": f"ack_{body.context_id}_v{body.version}", "stored_at": now()}


def choose(trigger_ids, tick_number):
    options = []
    for tid in trigger_ids:
        data = store.collect(tid)
        if data:
            options.append((tid, data))

    options.sort(key=lambda x: x[1]["trigger"].get("urgency", 2), reverse=True)

    chosen = []
    done = set()

    for tid, data in options:
        merchant_id = data["merchant"]["merchant_id"]

        if data["trigger"].get("suppression_key") in SENT_KEYS:
            continue
        if merchant_id in done:
            continue
        if tick_number - LAST_TICK.get(merchant_id, -99) < 3:
            continue
        if data["trigger"].get("urgency", 2) <= 1:
            continue

        chosen.append(tid)
        done.add(merchant_id)

        if len(chosen) >= MAX_PER_TICK:
            break

    return chosen


@app.post("/v1/tick")
def tick(body: TickBody):
    TICK_NUMBER[0] += 1
    tick_number = TICK_NUMBER[0]

    chosen = choose(body.available_triggers, tick_number)
    if not chosen:
        return {"actions": []}

    with ThreadPoolExecutor(max_workers=MAX_PER_TICK) as pool:
        results = list(pool.map(trigger.make_message, chosen))

    actions = []
    for action in results:
        if not action:
            continue
        actions.append(action)
        SENT_KEYS.add(action["suppression_key"])
        LAST_TICK[action["merchant_id"]] = tick_number

    return {"actions": actions}


@app.post("/v1/reply")
def handle_reply(body: ReplyBody):
    return reply.handle(
        conversation_id=body.conversation_id,
        merchant_id=body.merchant_id,
        customer_id=body.customer_id,
        message=body.message,
        from_role=body.from_role,
        turn_number=body.turn_number,
    )


@app.get("/v1/healthz")
def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - STARTED_AT),
        "contexts_loaded": store.count(),
    }


@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": "TODO — apna naam daalo",
        "team_members": ["TODO"],
        "model": "gemini-3.6-flash",
        "approach": "Context join by trigger id, fact-grounded prompt, rule-based reply routing",
        "contact_email": "TODO@example.com",
        "version": "1.0.0",
        "submitted_at": now(),
    }


@app.post("/v1/teardown")
def teardown():
    store.clear()
    reply.clear()
    SENT_KEYS.clear()
    LAST_TICK.clear()
    return {"ok": True}
