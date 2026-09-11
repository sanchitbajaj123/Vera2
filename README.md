# Vera 2.0 — magicpin AI Challenge submission

A WhatsApp merchant-engagement bot. It joins four context layers, composes one
grounded message, and routes merchant replies with rules before it reaches for an LLM.

## Approach

**1. Deterministic context join, then a fact-grounded prompt.**
`store.bundle(trigger_id)` walks `trigger → merchant → category → customer` and resolves
`payload.top_item_id` against the category digest. `composer.nikalo_facts()` flattens that
into a flat fact sheet, and the prompt states one hard rule: every number, date, price and
citation in the message must come from the fact sheet. The LLM writes prose; it never
supplies data. This is what keeps the hallucination penalty at zero when the judge injects
context the bot has never seen.

**2. Rules before the LLM on the reply path.**
`conversation.py` checks, in order: explicit refusal → end; canned auto-reply → one human-reach
attempt, then end; verbatim repeat → end; explicit commitment → a fixed action message with no
further qualifying question. Only what survives all four reaches the LLM. The commitment reply
is deliberately hardcoded — that path must never regress into asking another question, which the
brief names as production Vera's biggest miss.

**3. Restraint at tick time.**
`_kya_bhejna_chahiye()` sorts by urgency, drops anything whose `suppression_key` has already
fired, allows one message per merchant per tick, and holds a 3-tick cooldown per merchant.
Four actions max per tick keeps the call inside the 30s budget; composition runs in a thread pool.

**4. Output validation with one retry.**
`check_karo()` rejects taboo vocabulary, over-length bodies, truncated output, and repeats of
anything already sent. A failure re-prompts once with the specific problems; a message still
carrying a taboo word is dropped in favour of a deterministic template rather than sent.

## Tradeoffs

- **In-memory store, no Redis.** The brief permits it and the test never restarts the process.
  A restart mid-test would lose everything — the honest cost of the simpler choice.
- **Hardcoded commitment reply.** Less expressive than an LLM turn, but it can never drift back
  into qualifying, and it costs no latency.
- **Four actions per tick.** Below the cap of 20. With ~5s per composition, more actions would
  risk the 30s timeout, and the brief rewards restraint over volume.
- **Gemini at temperature 0, with a model fallback chain.** The strongest free-tier model allows only ~20 requests/day, so `logic.MODELS` tries it first and drops to progressively lighter models on a 429. Determinism is a stated requirement.
  Thinking tokens consume the output budget, so `maxOutputTokens` is held at 4000 and any
  `MAX_TOKENS` finish is discarded rather than sent truncated.

## What additional context would have helped most

1. **Slot availability.** Customer-facing recall messages want real open slots. Without them the
   message has to ask an open question where a two-option booking ask would convert better.
2. **Per-merchant reply history with outcomes.** `conversation_history` carries engagement tags
   but not what actually worked. Knowing which lever moved this merchant before would let the
   composer pick a lever instead of inferring one.
3. **Merchant's own taboo list.** Category voice rules are shared; individual merchants differ on
   how clinical or how promotional they want to sound.

## Layout

```
vera-bot/
├── main.py           routes only — no logic
├── schemas.py        request body shapes
├── store.py          five containers + the trigger→merchant→category join
├── trigger.py        first message: prompt, validation, retry
├── reply.py          reply routing: rules first, LLM last
├── gemini.py         one LLM call, with a model fallback chain
└── requirements.txt
```

| File | Purpose |
|---|---|
| `main.py` | The five endpoints, plus trigger selection and parallel composition at tick time |
| `schemas.py` | Pydantic models for the three POST bodies |
| `store.py` | `CATEGORIES/MERCHANTS/CUSTOMERS/TRIGGERS` keyed by context id, plus `CONVERSATIONS` keyed by conversation id; `collect()` joins all four layers from one trigger id |
| `trigger.py` | The composition prompt, output validation, one retry, deterministic fallback |
| `reply.py` | Refusal / auto-reply / repeat / commitment rules, then the conversation prompt |
| `gemini.py` | Temperature 0; a 429 retires that model and moves to the next |

Conversation history lives in `store.CONVERSATIONS`, not on the merchant. The merchant's
`conversation_history` seeds a new conversation; every turn after that is appended to the
conversation container, so both prompts read from one place.

## Running it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r vera-bot/requirements.txt

export GEMINI_API_KEY="your-key-from-aistudio.google.com/apikey"

cd vera-bot
uvicorn main:app --host 0.0.0.0 --port 8080
```

Then, from the project root in a second terminal:

```bash
python push_dataset.py            # load the base dataset
python run_judge.py all           # conversation scenarios
python run_judge.py phase2_short  # scored composition
```

## Local results

`phase2_short`: **43/50 (86%)** — specificity 9, category fit 9, merchant fit 9,
decision quality 8, engagement 8. Tick latency 7.3s, inside the 10s budget.
`all`: warmup, auto-reply, intent transition and hostile handling all pass. The auto-reply
path runs send → wait(24h) → end, matching the replay-test expectation.
