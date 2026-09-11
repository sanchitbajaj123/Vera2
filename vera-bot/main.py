import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timezone

from fastapi import FastAPI

import store
import trigger
import reply
from schemas import ContextBody, TickBody, ReplyBody

app = FastAPI(title="Vera 2.0")
STARTED_AT = time.time()

MAX_PER_TICK = 2
TICK_BUDGET_SECONDS = 8


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
    triggers = store.get_many("trigger", trigger_ids)
    if not triggers:
        return []

    options = sorted(triggers.items(), key=lambda kv: kv[1].get("urgency", 2), reverse=True)

    already_sent = store.were_sent([t.get("suppression_key") for _, t in options])
    ticks = store.last_ticks([t.get("merchant_id") for _, t in options if t.get("merchant_id")])

    chosen = []
    done = set()

    for tid, trg in options:
        merchant_id = trg.get("merchant_id")

        if not merchant_id or merchant_id in done:
            continue
        if trg.get("suppression_key") in already_sent:
            continue
        if tick_number - ticks.get(merchant_id, -99) < 3:
            continue
        if trg.get("urgency", 2) <= 1:
            continue

        chosen.append(tid)
        done.add(merchant_id)

        if len(chosen) >= MAX_PER_TICK:
            break

    return chosen


@app.post("/v1/tick")
def tick(body: TickBody):
    started = time.time()
    tick_number = store.next_tick_number()

    chosen = choose(body.available_triggers, tick_number)
    if not chosen:
        return {"actions": []}

    actions = []
    pool = ThreadPoolExecutor(max_workers=MAX_PER_TICK)
    futures = [pool.submit(trigger.make_message, tid) for tid in chosen]

    try:
        left = TICK_BUDGET_SECONDS - (time.time() - started)
        for future in as_completed(futures, timeout=max(0.5, left)):
            action = future.result()
            if not action:
                continue
            actions.append(action)
            store.mark_sent(action["suppression_key"])
            store.set_last_tick(action["merchant_id"], tick_number)
    except TimeoutError:
        pass
    finally:
        pool.shutdown(wait=False)

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
        "team_name": "Sanchit Bajaj",
        "team_members": ["Sanchit Bajaj"],
        "model": "gemini-3.6-flash (falls back to gemini-3.5-flash-lite on quota)",
        "approach": "Context join by trigger id, fact-grounded prompt, rule-based reply routing",
        "contact_email": "sanchitbajaj2003@gmail.com",
        "version": "1.0.0",
        "submitted_at": now(),
    }


@app.post("/v1/teardown")
def teardown():
    store.clear()
    return {"ok": True}
