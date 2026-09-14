"""
test_tick_deadline.py — Bug pakadne wala test.

Bug: agar message banane mein budget se zyada time lage, to tick
bana hua message PHENK deta hai aur {"actions": []} bhejta hai.

Sahi behaviour: jo message ban chuka hai wo BHEJNA chahiye.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vera-bot"))

import main
import store
import trigger
from schemas import TickBody

FAKE_TRIGGER_ID = "trg_test_slow"

store.save("category", "dentists", 1, {"slug": "dentists", "voice": {}, "peer_stats": {}})
store.save("merchant", "m_test", 1, {
    "merchant_id": "m_test", "category_slug": "dentists",
    "identity": {"name": "Test Clinic", "owner_first_name": "Test", "languages": ["en"]},
    "conversation_history": [],
})
store.save("trigger", FAKE_TRIGGER_ID, 1, {
    "id": FAKE_TRIGGER_ID, "kind": "test", "merchant_id": "m_test",
    "customer_id": None, "payload": {}, "urgency": 3,
    "suppression_key": "test:slow",
})

real_make_message = trigger.make_message


def slow_make_message(trigger_id):
    """Message banane mein budget se thoda zyada time lagta hai."""
    time.sleep(main.TICK_SOFT_BUDGET + 1)
    return {
        "conversation_id": f"conv_m_test_{trigger_id}",
        "merchant_id": "m_test", "customer_id": None, "send_as": "vera",
        "trigger_id": trigger_id, "template_name": "t", "template_params": [],
        "body": "This message was composed successfully.",
        "cta": "open_ended", "suppression_key": "test:slow", "rationale": "test",
    }


trigger.make_message = slow_make_message
try:
    started = time.time()
    result = main.tick(TickBody(now="2026-04-26T10:30:00Z", available_triggers=[FAKE_TRIGGER_ID]))
    took = time.time() - started
finally:
    trigger.make_message = real_make_message
    store.clear()

count = len(result["actions"])
print(f"tick liya      : {took:.1f}s")
print(f"actions mile   : {count}")
print()
if count == 1:
    print("PASS — bana hua message bheja gaya")
    sys.exit(0)
else:
    print("FAIL — message ban gaya tha par tick ne PHENK diya")
    print("       judge ko {\"actions\": []} gaya = 0 score")
    sys.exit(1)
