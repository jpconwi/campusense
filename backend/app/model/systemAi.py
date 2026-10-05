"""
model/systemAi.py - the Hugging Face connection.

Only this file talks to the language model. Everything else (faculty
availability, forms, reports, admin data) is handled by normal code.

If a model is busy (429 / 503 "engine_overloaded"), it is retried once after
a short pause, then the next model in the chain is tried.
MODEL in .env may hold one model or a comma-separated chain, e.g.
  MODEL=Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen3-8B,meta-llama/Llama-3.1-8B-Instruct
"""

import re
import time

from app import config

DEFAULT_CHAIN = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen3-8B",
    "meta-llama/Llama-3.1-8B-Instruct",
]

_client = None


def _get_client():
    global _client
    if _client is None:
        from huggingface_hub import InferenceClient
        _client = InferenceClient(api_key=config.API_KEY, provider="auto", timeout=30)
    return _client


def _model_chain():
    configured = [m.strip() for m in (config.MODEL or "").split(",") if m.strip()]
    chain = configured + [m for m in DEFAULT_CHAIN if m not in configured]
    return chain


def _is_busy(error):
    text = repr(error).lower()
    return any(k in text for k in ("429", "503", "502", "overloaded", "busy", "timed out", "timeout"))


def _clean(text):
    # Qwen3 may include <think>...</think>; never show that to users
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    return text.strip()


def ask_model(system_prompt, question):
    """Return the model's answer text, or None if every model failed."""
    if not config.API_KEY:
        print("AI ERROR: API_KEY is missing in backend/.env")
        return None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    for model in _model_chain():
        for attempt in (1, 2):
            try:
                response = _get_client().chat.completions.create(
                    model=model, messages=messages, max_tokens=500)
                answer = _clean(response.choices[0].message.content)
                if answer:
                    return answer
                break                      # empty answer -> try next model
            except Exception as error:
                print(f"AI ERROR ({model}, try {attempt}):", repr(error)[:300])
                if _is_busy(error) and attempt == 1:
                    time.sleep(1.5)        # short pause, retry same model once
                    continue
                break                      # other error or 2nd failure -> next model
    return None