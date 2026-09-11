"""
run_judge.py — magicpin ka judge_simulator.py chalata hai, Gemini ke saath.

Kyun alag file? Kyunki judge_simulator.py mein key seedha likhni padti hai
(galat aadat), aur usme purana model + chhota token budget set hai
jisse naya Gemini 3 ka jawab beech mein kat jaata hai.

Chalao:   set -a; source .env; set +a; ./venv/bin/python run_judge.py
"""

import json
import os
import sys
from urllib import request as urlrequest

import judge_simulator as J

# ---- config (key .env se aayegi, file mein nahi likhi) ----
J.LLM_PROVIDER = "gemini"
J.LLM_API_KEY = os.environ.get("GEMINI_API_KEY", "")
J.LLM_MODEL = os.environ.get("JUDGE_MODEL", "gemini-3.5-flash-lite")
J.BOT_URL = os.environ.get("BOT_URL", "http://localhost:8080")
J.TEST_SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "all"


# ---- Gemini 3 ke liye fix: bada token budget + sahi text nikalna ----
def _complete(self, prompt, system=None):
    full = f"{system}\n\n{prompt}" if system else prompt
    body = json.dumps({
        "contents": [{"parts": [{"text": full}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8000},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
    req = urlrequest.Request(url, data=body, headers={"Content-Type": "application/json"})
    resp = urlrequest.urlopen(req, timeout=90)
    data = json.loads(resp.read().decode("utf-8"))
    parts = data["candidates"][0].get("content", {}).get("parts", []) or []
    return "\n".join(p["text"] for p in parts if p.get("text") and not p.get("thought"))


J.GeminiProvider.complete = _complete

if __name__ == "__main__":
    J.main()
