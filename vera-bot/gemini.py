import os

import requests

import store

API_KEY = os.environ.get("GEMINI_API_KEY", "")

MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def ask(prompt, timeout=8):
    if not API_KEY:
        return None

    for model in MODELS:
        if store.is_quota_over(model):
            continue
        text = _call_one(model, prompt, timeout)
        if text:
            return text

    return None


def _call_one(model, prompt, timeout):
    try:
        response = requests.post(
            f"{BASE}/{model}:generateContent",
            headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 4000},
            },
            timeout=timeout,
        )
    except Exception:
        return None

    if response.status_code == 429:
        store.mark_quota_over(model)
        return None
    if response.status_code != 200:
        return None

    answer = response.json()["candidates"][0]
    if answer.get("finishReason") == "MAX_TOKENS":
        return None

    parts = answer.get("content", {}).get("parts", [])
    text = "\n".join(p["text"] for p in parts if p.get("text") and not p.get("thought"))

    return text.strip() or None
