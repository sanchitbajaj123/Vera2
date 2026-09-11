import store
import gemini


def build_prompt(data, conversation_id):
    trigger = data["trigger"]
    merchant = data["merchant"]
    category = data["category"]
    customer = data["customer"]
    news = data["news"]

    who = merchant.get("identity", {})
    perf = merchant.get("performance", {})
    peer = category.get("peer_stats", {})
    voice = category.get("voice", {})

    active_offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]
    catalog = [o["title"] for o in category.get("offer_catalog", [])][:6]

    if customer:
        role_line = (f"You are writing as {who.get('name')} (the shop itself) to one of its own "
                     f"customers. Warm but professional. You are the shop, not a marketing agency.")
    else:
        role_line = ("You are Vera, magicpin's assistant. You message shop owners like a knowledgeable "
                     "colleague who noticed something in their data — never like a salesperson.")

    prompt = f"""{role_line}

Write ONE WhatsApp message.

===== THE SHOP =====
Name: {who.get('name')}
Owner: {who.get('owner_first_name')}
Area: {who.get('locality')}, {who.get('city')}
Languages: {who.get('languages')}
Plan: {merchant.get('subscription', {}).get('plan')} — {merchant.get('subscription', {}).get('days_remaining')} days left
Last 30 days: {perf.get('views')} views, {perf.get('calls')} calls, {perf.get('directions')} directions, CTR {perf.get('ctr')}
Change in last 7 days: {perf.get('delta_7d')}
Peer shops nearby average: CTR {peer.get('avg_ctr')}, rating {peer.get('avg_rating')}, reviews {peer.get('avg_reviews')}
Their customer totals: {merchant.get('customer_aggregate')}
What we noticed (signals): {merchant.get('signals')}
What their reviews say: {merchant.get('review_themes')}
Offers running right now: {active_offers}
Offers available in this category: {catalog}

===== WHY WE ARE MESSAGING TODAY =====
Event: {trigger.get('kind')}
Details: {trigger.get('payload')}
Urgency (1 = low, 5 = high): {trigger.get('urgency')}"""

    if news:
        prompt += f"""

===== THE NEWS ITEM THIS IS ABOUT =====
Headline: {news.get('title')}
Source: {news.get('source')}
Study size: {news.get('trial_n')}
Applies to: {news.get('patient_segment')}
Summary: {news.get('summary')}
What they can do about it: {news.get('actionable')}"""

    if customer:
        rel = customer.get("relationship", {})
        prompt += f"""

===== THE CUSTOMER YOU ARE WRITING TO =====
Name: {customer.get('identity', {}).get('name')}
Last visit: {rel.get('last_visit')} (total visits: {rel.get('visits_total')})
Services they took before: {rel.get('services_received')}
Their status: {customer.get('state')}
When they prefer to come: {customer.get('preferences', {}).get('preferred_slots')}
They consented to: {customer.get('consent', {}).get('scope')}"""
    elif data.get("customer_count"):
        prompt += f"\n\nThis shop has {data['customer_count']} customers on record."

    prompt += f"""

===== WHAT WAS ALREADY SAID (never repeat any of it) =====
{store.format_history(conversation_id)}

===== HOW TO WRITE IT =====
Language: {store.pick_language(merchant, customer)}
Tone: {voice.get('tone')}. Talk peer-to-peer. Never promotional, never excited, no ALL CAPS.
Words you must NEVER use: {voice.get('vocab_taboo')}
Words that are fine to use: {voice.get('vocab_allowed', [])[:10]}

- Use ONLY the facts given above. Never invent a number, date, price, name or source.
- No URLs or links of any kind. Not even a domain name.
- No markdown, no bold, no bullet points. Plain WhatsApp text.
- No greeting preamble like "I hope you are doing well".
- Start with their name (the owner's first name, or the customer's name), then go straight
  into the single most specific fact you have — a number, a date, or a source.
  A message with no number in the first two lines is a weak message.
- The ask at the end MUST be about the event above. Never pivot to selling an offer
  in a message whose event is about compliance, research, news or a milestone —
  that breaks trust and reads like a sales bot.
- Only mention an offer when the event itself is about offers, bookings, or weak
  performance. When you do, name it as "service @ price" (like "Dental Cleaning @ Rs 299"),
  never a vague discount like "10% off" or "special offer".
- Keep it 2 to 5 short lines.
- Exactly ONE ask, and it must be the LAST line — something they can answer in three words.

Output ONLY the message text. Nothing before it, nothing after it."""

    return prompt


def check(text, data):
    if not text or len(text.strip()) < 25:
        return ["too short"]

    problems = []
    lower = text.lower()

    if "http" in lower or "www." in lower:
        problems.append("contains a URL")

    for word in data["category"].get("voice", {}).get("vocab_taboo", []):
        clean = word.split("(")[0].strip().lower()
        if clean and clean in lower:
            problems.append(f"banned word: {clean}")

    if len(text) > 700:
        problems.append("too long")

    if text.rstrip()[-1] not in ".?!)।":
        problems.append("looks cut off in the middle")

    return problems


def backup_message(data):
    who = data["merchant"].get("identity", {})
    name = who.get("owner_first_name") or who.get("name")
    news = data["news"]

    if news:
        return (f"{name}, {news.get('source')} — {news.get('title')}. "
                f"Aapke setup pe relevant lagta hai. Short summary bhej doon?")

    perf = data["merchant"].get("performance", {})
    if perf.get("views") and perf.get("calls"):
        return (f"{name}, pichhle 30 din mein profile {perf['views']} baar dikhi "
                f"par sirf {perf['calls']} calls aayin. Check karke bataun kahan gap hai?")

    return f"{name}, ek cheez aapke account mein dekhi jo batani thi. Bhej doon?"


def build_rationale(data):
    trigger, merchant, category = data["trigger"], data["merchant"], data["category"]
    parts = [f"Trigger '{trigger.get('kind')}' fired (urgency {trigger.get('urgency')})."]

    if data["news"]:
        parts.append(f"Anchored on {data['news'].get('source')}: {data['news'].get('title')}.")

    my_ctr = merchant.get("performance", {}).get("ctr")
    peer_ctr = category.get("peer_stats", {}).get("avg_ctr")
    if my_ctr and peer_ctr and my_ctr < peer_ctr:
        parts.append(f"Their CTR {my_ctr} is below peer {peer_ctr}.")

    if merchant.get("signals"):
        parts.append(f"Signals used: {', '.join(merchant['signals'][:2])}.")

    if data["customer"]:
        c = data["customer"]
        parts.append(f"Customer-facing: {c.get('identity', {}).get('name')} is {c.get('state')}.")

    parts.append(f"Language from merchant preference: {merchant.get('identity', {}).get('languages')}.")
    return " ".join(parts)


def pick_cta(data):
    if data["customer"]:
        return "multi_choice_slot"
    if data["trigger"].get("urgency", 2) >= 4:
        return "binary_yes_no"
    return "open_ended"


def make_message(trigger_id):
    data = store.collect(trigger_id)
    if not data:
        return None

    merchant = data["merchant"]
    merchant_id = merchant["merchant_id"]
    conversation_id = f"conv_{merchant_id}_{trigger_id}"

    if not store.get_conversation(conversation_id):
        store.start_conversation(
            conversation_id, merchant_id,
            data["trigger"].get("customer_id"), trigger_id, merchant)

    prompt = build_prompt(data, conversation_id)
    text = gemini.ask(prompt)

    if text:
        problems = check(text, data)
        if problems:
            retry = gemini.ask(prompt + f"\n\nYour last attempt had these problems: {problems}. Fix them.")
            text = retry if (retry and not check(retry, data)) else None

    if not text:
        text = backup_message(data)

    text = text.strip()

    store.add_turn(conversation_id, "vera", text)

    trigger = data["trigger"]
    who = merchant.get("identity", {})
    name = who.get("owner_first_name") or who.get("name", "")

    return {
        "conversation_id": conversation_id,
        "merchant_id": merchant_id,
        "customer_id": trigger.get("customer_id"),
        "send_as": "merchant_on_behalf" if data["customer"] else "vera",
        "trigger_id": trigger_id,
        "template_name": f"vera_{trigger.get('kind', 'generic')}_v1",
        "template_params": [name, trigger.get("kind", ""), text[:60]],
        "body": text,
        "cta": pick_cta(data),
        "suppression_key": trigger.get("suppression_key") or f"trigger:{trigger_id}",
        "rationale": build_rationale(data),
    }
