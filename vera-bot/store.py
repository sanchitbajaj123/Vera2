CATEGORIES = {}
MERCHANTS = {}
CUSTOMERS = {}
TRIGGERS = {}

BOXES = {
    "category": CATEGORIES,
    "merchant": MERCHANTS,
    "customer": CUSTOMERS,
    "trigger": TRIGGERS,
}

CONVERSATIONS = {}


def save(scope, context_id, version, payload):
    box = BOXES.get(scope)
    if box is None:
        return False, "invalid_scope", None

    old = box.get(context_id)

    if old and old["version"] == version:
        return True, None, version

    if old and old["version"] > version:
        return False, "stale_version", old["version"]

    box[context_id] = {"version": version, "payload": payload}
    return True, None, version


def get(scope, context_id):
    if not context_id:
        return None
    row = BOXES[scope].get(context_id)
    return row["payload"] if row else None


def count():
    return {scope: len(box) for scope, box in BOXES.items()}


def customers_of(merchant_id):
    return [row["payload"] for row in CUSTOMERS.values()
            if row["payload"].get("merchant_id") == merchant_id]


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
    all_customers = [] if customer else customers_of(merchant["merchant_id"])

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
        "all_customers": all_customers,
        "news": news,
    }


def start_conversation(conversation_id, merchant_id, customer_id, trigger_id, merchant):
    history = [
        {"role": turn.get("from", "vera"), "message": turn.get("body", "")}
        for turn in merchant.get("conversation_history", [])
    ]

    CONVERSATIONS[conversation_id] = {
        "merchant_id": merchant_id,
        "customer_id": customer_id,
        "trigger_id": trigger_id,
        "history": history,
    }
    return CONVERSATIONS[conversation_id]


def get_conversation(conversation_id):
    return CONVERSATIONS.get(conversation_id)


def add_turn(conversation_id, role, message):
    chat = CONVERSATIONS.get(conversation_id)
    if chat:
        chat["history"].append({"role": role, "message": message})


def pick_language(merchant, customer):
    if customer:
        pref = (customer.get("identity", {}).get("language_pref") or "").lower()
        return "Hinglish (Hindi-English mix, roman script)" if "hi" in pref else "simple English"

    langs = [x.lower() for x in merchant.get("identity", {}).get("languages", [])]
    return "Hinglish (Hindi-English mix, roman script)" if "hi" in langs else "simple English"


def format_history(conversation_id, limit=8):
    chat = CONVERSATIONS.get(conversation_id)
    if not chat or not chat["history"]:
        return "(no earlier conversation)"

    lines = []
    for turn in chat["history"][-limit:]:
        speaker = "Vera" if turn["role"] == "vera" else turn["role"].capitalize()
        lines.append(f"{speaker}: {turn['message']}")
    return "\n".join(lines)


def clear():
    for box in BOXES.values():
        box.clear()
    CONVERSATIONS.clear()
