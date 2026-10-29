"""
model/systemAi.py - the "brain": every connection to a language model lives here.

Everything else (faculty availability, forms, reports, admin data) is normal code.
Only questions that really need a language model reach this file.

PROVIDER FALLBACK CHAIN - always tried in exactly this order:

    1. Hugging Face   primary provider
    2. Cloudflare     first fallback   (Workers AI)
    3. Groq           second fallback
    4. Google         third fallback   (Gemini API)
    5. OpenRouter     final fallback

A provider whose key is missing in backend/.env is skipped silently. If a provider
(or every model inside it) fails - rate limit, outage, timeout, bad key - the next
one is tried automatically, so the person asking never notices. A provider that has
just failed is "cooled down" for a short while so the next questions do not wait
for it again. Each provider may list several models (comma separated); they are
tried in order inside that provider before moving on.
"""

import re
import time

import httpx

from app import config

# The order is fixed on purpose. Do not reorder without changing the requirement.
PROVIDER_ORDER = ("huggingface", "cloudflare", "groq", "google", "openrouter")

LABELS = {"huggingface": "Hugging Face", "cloudflare": "Cloudflare", "groq": "Groq",
          "google": "Google", "openrouter": "OpenRouter"}

# Default models, used when a *_MODEL setting is not given (all are chat models).
DEFAULT_MODELS = {
    "huggingface": ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen3-8B", "meta-llama/Llama-3.1-8B-Instruct"],
    "cloudflare": ["@cf/meta/llama-3.1-8b-instruct", "@cf/mistralai/mistral-small-3.1-24b-instruct"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "google": ["gemini-2.5-flash", "gemini-flash-latest"],
    "openrouter": ["meta-llama/llama-3.3-70b-instruct:free", "openai/gpt-oss-20b:free"],
}

MAX_TOKENS = 500
GOOGLE_MAX_TOKENS = 1500            # Gemini "thinking" tokens count against the limit
REQUEST_TIMEOUT = 25                # seconds for one request
TOTAL_TIMEOUT = 60                  # seconds for the whole chain, then give up
COOLDOWN_AFTER_FAILURE = 60         # skip a provider this long after all its models failed
COOLDOWN_AFTER_BAD_KEY = 600        # ...and this long after a 401 / 403 (wrong key)

# ---- photo analysis: only free-tier / open-source vision models, tried in this order
VISION_PROVIDER_ORDER = ("huggingface", "openrouter", "groq", "google")
DEFAULT_VISION_MODELS = {
    "huggingface": ["Qwen/Qwen2.5-VL-7B-Instruct", "Qwen/Qwen2.5-VL-32B-Instruct", "google/gemma-3-27b-it"],
    "openrouter": ["qwen/qwen2.5-vl-72b-instruct:free", "google/gemma-3-27b-it:free"],
    "groq": ["meta-llama/llama-4-scout-17b-16e-instruct"],
    "google": ["gemini-2.5-flash"],
}
VISION_MAX_TOKENS = 700
VISION_GOOGLE_MAX_TOKENS = 2000

_cooldown_until = {}                # provider -> time.monotonic() when it may be tried again
_hf_client = None


# ------------------------------------------------------------ settings
def _split(value):
    return [m.strip() for m in (value or "").split(",") if m.strip()]


def _models(provider):
    configured = _split(getattr(config, f"{provider.upper()}_MODEL", None))
    if provider == "huggingface":      # keep the old behaviour: your models first, then the defaults
        return configured + [m for m in DEFAULT_MODELS[provider] if m not in configured]
    return configured or list(DEFAULT_MODELS[provider])


def is_configured(provider):
    if provider == "huggingface":
        return bool(config.HUGGINGFACE_API_KEY)
    if provider == "cloudflare":
        return bool(config.CLOUDFLARE_API_KEY and config.CLOUDFLARE_ACCOUNT_ID)
    return bool(getattr(config, f"{provider.upper()}_API_KEY", None))


def chain_status():
    """For the admin page / start-up log. Never contains a key."""
    now = time.monotonic()
    return [{"order": i + 1, "provider": p, "name": LABELS[p], "configured": is_configured(p),
             "models": _models(p),
             "cooling_down": _cooldown_until.get(p, 0) > now}
            for i, p in enumerate(PROVIDER_ORDER)]


def describe_chain():
    return " -> ".join(f"{s['name']}{'' if s['configured'] else ' (no key, skipped)'}"
                       for s in chain_status())


def reset_cooldowns():
    _cooldown_until.clear()


# ------------------------------------------------------------ helpers
def _clean(text):
    # Qwen3 / reasoning models may include <think>...</think>; never show that to users
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    return text.strip()


def _status_of(error):
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def _is_bad_key(error):
    text = repr(error).lower()
    return _status_of(error) in (401, 403) or " 401" in text or " 403" in text or "unauthorized" in text


def _is_busy(error):
    """Short-lived trouble worth ONE quick retry on the same model."""
    if _status_of(error) in (502, 503, 504):
        return True
    text = repr(error).lower()
    return any(k in text for k in ("503", "502", "overloaded", "busy", "timed out", "timeout"))


# ------------------------------------------------------ the five providers
def _hf_chat(model, messages, timeout):
    global _hf_client
    if _hf_client is None:
        from huggingface_hub import InferenceClient
        _hf_client = InferenceClient(api_key=config.HUGGINGFACE_API_KEY, provider="auto", timeout=REQUEST_TIMEOUT)
    response = _hf_client.chat.completions.create(model=model, messages=messages, max_tokens=MAX_TOKENS)
    return response.choices[0].message.content


def _http_post(url, headers, payload, timeout):
    """One OpenAI-style chat request. Raises for any HTTP error. (Tests replace this.)"""
    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _openai_style(url, key, model, messages, timeout, max_tokens=MAX_TOKENS, headers=None):
    all_headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    all_headers.update(headers or {})
    data = _http_post(url, all_headers,
                      {"model": model, "messages": messages, "max_tokens": max_tokens}, timeout)
    return data["choices"][0]["message"]["content"]


def _cloudflare_chat(model, messages, timeout):
    url = (f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}"
           "/ai/v1/chat/completions")
    return _openai_style(url, config.CLOUDFLARE_API_KEY, model, messages, timeout)


def _groq_chat(model, messages, timeout):
    return _openai_style("https://api.groq.com/openai/v1/chat/completions",
                         config.GROQ_API_KEY, model, messages, timeout)


def _google_chat(model, messages, timeout):
    return _openai_style("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                         config.GOOGLE_API_KEY, model, messages, timeout, max_tokens=GOOGLE_MAX_TOKENS)


def _openrouter_chat(model, messages, timeout):
    return _openai_style("https://openrouter.ai/api/v1/chat/completions",
                         config.OPENROUTER_API_KEY, model, messages, timeout,
                         headers={"X-Title": "NEMSAI"})


_CALLERS = {"huggingface": _hf_chat, "cloudflare": _cloudflare_chat, "groq": _groq_chat,
            "google": _google_chat, "openrouter": _openrouter_chat}


# ------------------------------------------------------------ the chain
def _try_provider(provider, messages, deadline, models=None, callers=None, key=None):
    """Try every model of one provider. Returns (answer, model) or (None, None).
    `models` / `callers` / `key` let the photo chain reuse this with its own models and cooldown."""
    bad_key = False
    callers = callers or _CALLERS
    key = key or provider
    for model in (models or _models(provider)):
        for attempt in (1, 2):
            if time.monotonic() >= deadline:
                return None, None
            timeout = max(3, min(REQUEST_TIMEOUT, deadline - time.monotonic()))
            try:
                answer = _clean(callers[provider](model, messages, timeout))
                if answer:
                    return answer, model
                break                                   # empty answer -> next model
            except Exception as error:
                print(f"AI ERROR ({LABELS[provider]} / {model}, try {attempt}):", repr(error)[:300])
                if _is_bad_key(error):
                    bad_key = True
                    break
                if attempt == 1 and _is_busy(error):
                    time.sleep(1.0)                     # one short retry on the same model
                    continue
                break                                   # other error / 2nd failure -> next model
        if bad_key:
            break                                       # a wrong key fails for every model
    _cooldown_until[key] = time.monotonic() + (
        COOLDOWN_AFTER_BAD_KEY if bad_key else COOLDOWN_AFTER_FAILURE)
    return None, None


def ask_model_with_source(system_prompt, question):
    """Returns (answer, provider_name). (None, None) if every provider failed."""
    if not any(is_configured(p) for p in PROVIDER_ORDER):
        print("AI ERROR: no AI provider key is set in backend/.env "
              "(HF_API_KEY / API_KEY, CLOUDFLARE_*, GROQ_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY)")
        return None, None

    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": question}]
    deadline = time.monotonic() + TOTAL_TIMEOUT

    for _round in (1, 2):
        attempted = False
        for provider in PROVIDER_ORDER:                 # Hugging Face first ... OpenRouter last
            if not is_configured(provider):
                continue
            if _cooldown_until.get(provider, 0) > time.monotonic():
                continue                                # failed a moment ago, do not wait for it again
            attempted = True
            answer, model = _try_provider(provider, messages, deadline)
            if answer:
                if provider != PROVIDER_ORDER[0]:
                    print(f"AI: answered by fallback {LABELS[provider]} ({model})")
                return answer, provider
        if attempted:
            break
        reset_cooldowns()          # every provider was cooling down: try them all again right now
    return None, None


def ask_model(system_prompt, question):
    """Return the model's answer text, or None if every provider failed."""
    return ask_model_with_source(system_prompt, question)[0]



# ------------------------------------------------------------ photo (vision) chain
def _vision_models(provider):
    configured = _split(getattr(config, {"huggingface": "HF_VISION_MODEL",
                                         "openrouter": "OPENROUTER_VISION_MODEL",
                                         "groq": "GROQ_VISION_MODEL",
                                         "google": "GOOGLE_VISION_MODEL"}[provider], None))
    return configured or list(DEFAULT_VISION_MODELS[provider])


def _vision_callers():
    def hf(model, messages, timeout):
        global _hf_client
        if _hf_client is None:
            from huggingface_hub import InferenceClient
            _hf_client = InferenceClient(api_key=config.HUGGINGFACE_API_KEY, provider="auto",
                                         timeout=REQUEST_TIMEOUT)
        return _hf_client.chat.completions.create(
            model=model, messages=messages, max_tokens=VISION_MAX_TOKENS,
            temperature=0.1).choices[0].message.content

    def openai_style(url, key_name, extra=None, tokens=VISION_MAX_TOKENS):
        return lambda model, messages, timeout: _openai_style(
            url, getattr(config, key_name), model, messages, timeout, max_tokens=tokens, headers=extra)

    return {
        "huggingface": hf,
        "openrouter": openai_style("https://openrouter.ai/api/v1/chat/completions",
                                   "OPENROUTER_API_KEY", {"X-Title": "NEMSAI"}),
        "groq": openai_style("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
        "google": openai_style("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                               "GOOGLE_API_KEY", tokens=VISION_GOOGLE_MAX_TOKENS),
    }


def vision_available():
    return any(is_configured(p) for p in VISION_PROVIDER_ORDER)


def ask_vision(system_prompt, user_text, image_b64, mime="image/jpeg"):
    """Ask a vision-language model about ONE image. Returns (answer, provider, model);
    (None, None, None) when no provider could answer (the caller then falls back to manual review)."""
    if not vision_available():
        print("AI ERROR: no vision provider key is set (HF_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY or GOOGLE_API_KEY)")
        return None, None, None
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]},
    ]
    callers = _vision_callers()
    deadline = time.monotonic() + TOTAL_TIMEOUT
    for provider in VISION_PROVIDER_ORDER:
        key = provider + ":vision"
        if not is_configured(provider) or _cooldown_until.get(key, 0) > time.monotonic():
            continue
        answer, model = _try_provider(provider, messages, deadline, models=_vision_models(provider),
                                      callers=callers, key=key)
        if answer:
            return answer, provider, model
    return None, None, None
