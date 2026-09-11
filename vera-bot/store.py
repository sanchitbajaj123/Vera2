import json
import os

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

SCOPES = ["category", "merchant", "customer", "trigger"]

KEY_CONTEXT = "vera:{scope}"
KEY_CONV = "vera:conv"
KEY_CUSTOMERS_OF = "vera:cust_of:{merchant_id}"
KEY_SENT = "vera:sent"
KEY_LAST_TICK = "vera:lasttick"
KEY_TICK_NUMBER = "vera:ticknum"
KEY_AUTO_COUNT = "vera:autocount"
KEY_QUOTA_OVER = "vera:quota_over"


def save(scope, context_id, version, payload):
    if scope not in SCOPES:
        return False, "invalid_scope", None

    key = KEY_CONTEXT.format(scope=scope)
    old_raw = r.hget(key, context_id)

    if old_raw:
        old = json.loads(old_raw)
        if old["version"] == version:
            return True, None, version
        if old["version"] > version:
            return False, "stale_version", old["version"]

    r.hset(key, context_id, json.dumps({"version": version, "payload": payload}))

    if scope == "customer":
        merchant_id = payload.get("merchant_id")
        if merchant_id:
            r.sadd(KEY_CUSTOMERS_OF.format(merchant_id=merchant_id), context_id)

    return True, None, version


def get(scope, context_id):
    if not context_id or scope not in SCOPES:
        return None
    raw = r.hget(KEY_CONTEXT.format(scope=scope), context_id)
    return json.loads(raw)["payload"] if raw else None


def count():
    return {scope: r.hlen(KEY_CONTEXT.format(scope=scope)) for scope in SCOPES}


def customer_count(merchant_id):
    return r.scard(KEY_CUSTOMERS_OF.format(merchant_id=merchant_id))


def collect(trigger_id):
    trigger = get("trigger", trigger_id)
    if not trigger:
        return None

    merchant = get("merchant", trigger.get("merchant_id"))
    if not merchant:
        return None

    category = get("category", merchant.get("category_slug"))
    if not category:
        return None

    customer = get("customer", trigger.get("customer_id"))

    news = None
    news_id = (trigger.get("payload") or {}).get("top_item_id")
    if news_id:
        for item in category.get("digest", []):
            if item.get("id") == news_id:
                news = item
                break

    return {
        "trigger": trigger,
        "merchant": merchant,
        "category": category,
        "customer": customer,
        "customer_count": 0 if customer else customer_count(merchant["merchant_id"]),
        "news": news,
    }


def start_conversation(conversation_id, merchant_id, customer_id, trigger_id, merchant):
    history = [
        {"role": turn.get("from", "vera"), "message": turn.get("body", "")}
        for turn in merchant.get("conversation_history", [])
    ]
    chat = {
        "merchant_id": merchant_id,
        "customer_id": customer_id,
        "trigger_id": trigger_id,
        "history": history,
    }
    r.hset(KEY_CONV, conversation_id, json.dumps(chat))
    return chat


def get_conversation(conversation_id):
    raw = r.hget(KEY_CONV, conversation_id)
    return json.loads(raw) if raw else None


def add_turn(conversation_id, role, message):
    chat = get_conversation(conversation_id)
    if not chat:
        return
    chat["history"].append({"role": role, "message": message})
    r.hset(KEY_CONV, conversation_id, json.dumps(chat))


def pick_language(merchant, customer):
    if customer:
        pref = (customer.get("identity", {}).get("language_pref") or "").lower()
        return "Hinglish (Hindi-English mix, roman script)" if "hi" in pref else "simple English"

    langs = [x.lower() for x in merchant.get("identity", {}).get("languages", [])]
    return "Hinglish (Hindi-English mix, roman script)" if "hi" in langs else "simple English"


def format_history(conversation_id, limit=8):
    chat = get_conversation(conversation_id)
    if not chat or not chat["history"]:
        return "(no earlier conversation)"

    lines = []
    for turn in chat["history"][-limit:]:
        speaker = "Vera" if turn["role"] == "vera" else turn["role"].capitalize()
        lines.append(f"{speaker}: {turn['message']}")
    return "\n".join(lines)


def was_sent(suppression_key):
    return bool(r.sismember(KEY_SENT, suppression_key))


def mark_sent(suppression_key):
    r.sadd(KEY_SENT, suppression_key)


def last_tick(merchant_id):
    value = r.hget(KEY_LAST_TICK, merchant_id)
    return int(value) if value else -99


def set_last_tick(merchant_id, tick_number):
    r.hset(KEY_LAST_TICK, merchant_id, tick_number)


def next_tick_number():
    return r.incr(KEY_TICK_NUMBER)


def bump_auto_reply(merchant_id):
    return r.hincrby(KEY_AUTO_COUNT, merchant_id, 1)


def is_quota_over(model):
    return bool(r.sismember(KEY_QUOTA_OVER, model))


def mark_quota_over(model):
    r.sadd(KEY_QUOTA_OVER, model)
    r.expire(KEY_QUOTA_OVER, 3600)


def clear():
    keys = list(r.scan_iter("vera:*"))
    if keys:
        r.delete(*keys)
