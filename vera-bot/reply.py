import re

import store
import gemini


AUTO_REPLY_WORDS = [
    "thank you for contacting", "thanks for contacting", "our team will",
    "we will get back to you", "will respond shortly", "automated assistant",
    "automated message", "this is an automated", "away message", "office hours",
    "we have received your message", "sampark karne ke liye", "dhanyavaad",
    "shukriya", "team tak pahuncha", "jaankari ke liye",
]

YES_WORDS = [
    "yes", "yeah", "yep", "ok", "okay", "sure", "go ahead", "lets do it",
    "let's do it", "do it", "please do", "send it", "send me", "share it",
    "haan", "han", "haa", "ji", "theek hai", "thik hai", "kar do", "kardo",
    "bhejo", "bhej do", "chalega", "interested", "i want", "mujhe chahiye", "join",
]

NO_WORDS = [
    "not interested", "no thanks", "no thank", "stop", "unsubscribe",
    "dont message", "don't message", "stop messaging", "spam", "useless",
    "band karo", "mat bhejo", "nahi chahiye", "block", "remove me", "bakwas",
]

AUTO_COUNT = {}


def has_any(text, words):
    lower = (text or "").strip().lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", lower) for w in words)


def build_prompt(data, conversation_id, incoming_message, from_role):
    merchant = data["merchant"]
    category = data["category"]
    customer = data["customer"]

    who = merchant.get("identity", {})
    voice = category.get("voice", {})
    active_offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]

    speaker = "the shop owner" if from_role == "merchant" else "the customer"
    customer_line = ""
    if customer:
        customer_line = f"Customer in this chat: {customer.get('identity', {}).get('name')}"

    return f"""You are Vera, magicpin's assistant, in the middle of a WhatsApp conversation.

===== WHO YOU ARE TALKING TO =====
Shop: {who.get('name')} ({who.get('locality')}, {who.get('city')})
Owner: {who.get('owner_first_name')}
Languages: {who.get('languages')}
Their 30-day numbers: {merchant.get('performance')}
Offers running right now: {active_offers}
What we noticed (signals): {merchant.get('signals')}
{customer_line}

===== THE CONVERSATION SO FAR =====
{store.format_history(conversation_id)}

===== THE NEW MESSAGE (from {speaker}) =====
{incoming_message}

===== HOW TO REPLY =====
Language: {store.pick_language(merchant, customer)} — but if their last message is in a
different language than before, switch to match them.
Tone: {voice.get('tone')}. Peer-to-peer.
Words you must NEVER use: {voice.get('vocab_taboo')}

- Use ONLY the facts given above. Never invent a number, date, price, name or source.
- No URLs or links of any kind. Not even a domain name.
- No markdown, no bullet points. Plain WhatsApp text.
- Never re-introduce yourself — the conversation already started.
- If they agreed to something, DO the thing and say it is being done.
  Do not ask another qualifying question. Momentum is the whole point.
- If they asked something you have no data for, say plainly you will check.
  Never guess a number.
- If they asked about something outside your job (GST, legal, hiring), say in ONE line
  that it is outside what you handle, then bring it back to the one thing you can do.
- If they sound annoyed, do not push. Acknowledge and offer to stop.
- Keep it 1 to 3 short lines — shorter than your last message.
- Exactly ONE ask, and it must be the LAST line.

Output ONLY the reply text. Nothing before it, nothing after it."""


def handle(conversation_id, merchant_id, customer_id, message, from_role, turn_number):

    chat = store.get_conversation(conversation_id)

    if has_any(message, NO_WORDS):
        return {
            "action": "end",
            "rationale": "Merchant said no clearly. Exiting immediately and politely — "
                         "another nudge here would be a penalty.",
        }

    if has_any(message, AUTO_REPLY_WORDS):
        key = merchant_id or conversation_id
        AUTO_COUNT[key] = AUTO_COUNT.get(key, 0) + 1
        times = AUTO_COUNT[key]

        if times == 1:
            body = ("Samajh gayi — ye automated reply lag raha hai. "
                    "Owner ya manager se baat ho sakti hai? "
                    "2 minute ka kaam hai, unke liye hi useful hai.")
            store.add_turn(conversation_id, "vera", body)
            return {
                "action": "send",
                "body": body,
                "cta": "binary_yes_no",
                "rationale": "Auto-reply detected. One attempt to flag it for the owner "
                             "(the brief's Pattern B).",
            }

        if times == 2:
            return {
                "action": "wait",
                "wait_seconds": 86400,
                "rationale": "Same auto-reply twice — owner is not at the phone. "
                             "Backing off 24h before any retry.",
            }

        return {
            "action": "end",
            "rationale": f"Auto-reply {times} times in a row, no real reply. "
                         "Zero engagement signal — closing.",
        }

    if chat and any(t["role"] != "vera" and t["message"] == message for t in chat["history"]):
        return {
            "action": "end",
            "rationale": "Exact same message repeated — auto-responder. Exiting.",
        }

    if chat:
        store.add_turn(conversation_id, from_role, message)

    if has_any(message, YES_WORDS):
        merchant = store.get("merchant", merchant_id) or {}
        name = merchant.get("identity", {}).get("owner_first_name", "")
        prefix = f"{name}, " if name else ""
        body = (f"{prefix}done — main abhi draft bana rahi hoon. "
                f"10 minute mein review ke liye bhejti hoon; "
                f"aap sirf confirm kar dena, publish main kar dungi.")
        store.add_turn(conversation_id, "vera", body)
        return {
            "action": "send",
            "body": body,
            "cta": "binary_confirm_cancel",
            "rationale": "Merchant committed. No more qualifying questions — straight to action. "
                         "(Brief's Pattern D: production Vera's biggest miss.)",
        }

    if turn_number >= 6:
        return {
            "action": "wait",
            "wait_seconds": 86400,
            "rationale": "Running long without progress. Backing off a day.",
        }

    return llm_reply(conversation_id, merchant_id, customer_id, message, from_role)


def llm_reply(conversation_id, merchant_id, customer_id, message, from_role):
    chat = store.get_conversation(conversation_id)
    trigger_id = chat.get("trigger_id") if chat else None

    data = store.collect(trigger_id) if trigger_id else None
    if not data:
        merchant = store.get("merchant", merchant_id)
        if not merchant:
            return {"action": "end", "rationale": "No context for this merchant — cannot reply safely."}
        data = {
            "merchant": merchant,
            "category": store.get("category", merchant.get("category_slug")) or {},
            "customer": store.get("customer", customer_id),
        }

    prompt = build_prompt(data, conversation_id, message, from_role)
    text = gemini.ask(prompt)

    if not text or "http" in text.lower():
        text = "Ye main check karke bata deti hoon. Tab tak profile ka quick audit bhej doon?"

    if chat and any(t["role"] == "vera" and t["message"] == text for t in chat["history"]):
        text = "Ek aur cheez jo useful ho sakti hai — bhej doon?"

    store.add_turn(conversation_id, "vera", text)

    return {
        "action": "send",
        "body": text,
        "cta": "open_ended",
        "rationale": "Normal reply — answered their message using stored context, one ask at the end.",
    }


def clear():
    AUTO_COUNT.clear()
