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
from datetime import datetime, timezone

import httpx

from app import config

# The order is fixed on purpose. Do not reorder without changing the requirement.
PROVIDER_ORDER = ("huggingface", "cloudflare", "groq", "google", "openrouter")

LABELS = {"huggingface": "Hugging Face", "cloudflare": "Cloudflare", "groq": "Groq",
          "google": "Google", "openrouter": "OpenRouter"}

# Default models, used when a *_MODEL setting is not given (all are chat models).
# Model names are retired often (checked against the providers' docs on 2026-10-29), so a model
# that answers "gone / not supported" is remembered as dead for a while and skipped (see below).
DEFAULT_MODELS = {
    "huggingface": ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen3-8B", "meta-llama/Llama-3.1-8B-Instruct"],
    "cloudflare": ["@cf/mistralai/mistral-small-3.1-24b-instruct", "@cf/google/gemma-4-26b-a4b-it",
                   "@cf/zai-org/glm-4.7-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"],
    "google": ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"],
    "openrouter": ["openrouter/free", "google/gemma-4-31b-it:free"],
}

MAX_TOKENS = 500
GOOGLE_MAX_TOKENS = 1500            # Gemini "thinking" tokens count against the limit
REQUEST_TIMEOUT = 25                # seconds for one request
TOTAL_TIMEOUT = 60                  # seconds for the whole chain, then give up
COOLDOWN_AFTER_FAILURE = 60         # skip a provider this long after all its models failed
COOLDOWN_AFTER_BAD_KEY = 600        # ...and this long after a 401 / 403 (wrong key)
COOLDOWN_AFTER_NO_CREDIT = 1800     # ...and this long after a 402 (free credits used up)
DEAD_MODEL_SECONDS = 3600           # a model that answered 404 / 410 / "not supported" is skipped this long

# ---- photo analysis: free-tier / open-source vision models, same provider order as the text chain
VISION_PROVIDER_ORDER = PROVIDER_ORDER
DEFAULT_VISION_MODELS = {
    "huggingface": ["Qwen/Qwen3-VL-8B-Instruct", "Qwen/Qwen2.5-VL-7B-Instruct"],
    "cloudflare": ["@cf/google/gemma-4-26b-a4b-it", "@cf/meta/llama-4-scout-17b-16e-instruct",
                   "@cf/mistralai/mistral-small-3.1-24b-instruct"],
    "groq": ["qwen/qwen3.8-27b", "qwen/qwen3.6-27b"],
    "google": ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"],
    "openrouter": ["openrouter/free", "google/gemma-4-31b-it:free", "nvidia/nemotron-nano-12b-v2-vl:free"],
}
VISION_MAX_TOKENS = 900
VISION_REASONING_TOKENS = 700      # Keep photo checks concise and reduce reasoning latency
VISION_TOTAL_TIMEOUT = 24          # A failed photo check should not hold the chat for a minute
VISION_PROVIDER_TIMEOUT = 8        # Preserve time for a fallback when one vision provider stalls

_cooldown_until = {}                # provider -> time.monotonic() when it may be tried again
_dead = {}                          # (provider key, model) -> until when the model is skipped
_hf_client = None
_provider_enabled = {}
_provider_health = {}


# ------------------------------------------------------------ settings
def _split(value):
    return [m.strip() for m in (value or "").split(",") if m.strip()]


def _models(provider):
    # Your *_MODEL setting goes FIRST, then the built-in defaults as backup. (Old names left in
    # Render / .env after a provider retires a model can then never block the working defaults.)
    configured = _split(getattr(config, f"{provider.upper()}_MODEL", None))
    return configured + [m for m in DEFAULT_MODELS[provider] if m not in configured]


def has_credentials(provider):
    if provider == "huggingface":
        return bool(config.HUGGINGFACE_API_KEY)
    if provider == "cloudflare":
        return bool(config.CLOUDFLARE_API_KEY and config.CLOUDFLARE_ACCOUNT_ID)
    return bool(getattr(config, f"{provider.upper()}_API_KEY", None))


def is_configured(provider):
    return _provider_enabled.get(provider, True) and has_credentials(provider)


def chain_status():
    """For the admin page / start-up log. Never contains a key."""
    now = time.monotonic()
    rows = []
    for i, provider in enumerate(PROVIDER_ORDER):
        health = _provider_health.get(provider, {})
        rows.append({"order": i + 1, "provider": provider, "name": LABELS[provider],
                     "enabled": _provider_enabled.get(provider, True),
                     "configured": is_configured(provider), "has_credentials": has_credentials(provider),
                     "models": _models(provider), "cooling_down": _cooldown_until.get(provider, 0) > now,
                     "health": health.get("health", "not_checked"),
                     "last_outcome": health.get("last_outcome"), "last_issue": health.get("last_issue"),
                     "last_model": health.get("last_model"), "last_mode": health.get("last_mode"),
                     "last_checked_at": health.get("last_checked_at"),
                     "last_http_status": health.get("last_http_status"),
                     "checks": health.get("checks", 0), "successes": health.get("successes", 0),
                     "failures": health.get("failures", 0),
                     "billing_signal": health.get("billing_signal", "not_reported")})
    return rows


def _record_provider_health(provider, outcome, *, model=None, vision=False, error=None):
    state = _provider_health.setdefault(provider, {"checks": 0, "successes": 0, "failures": 0})
    state["checks"] += 1
    state["last_outcome"] = outcome
    state["health"] = "healthy" if outcome == "success" else outcome
    state["last_model"] = model
    state["last_mode"] = "photo" if vision else "chat"
    state["last_checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["last_http_status"] = _status_of(error) if error else None
    if outcome == "success":
        state["successes"] += 1
        state["last_issue"] = None
        state["billing_signal"] = "not_reported"
    else:
        state["failures"] += 1
        state["last_issue"] = outcome
        if outcome == "payment_required":
            state["billing_signal"] = "payment_or_credits_required"
        elif outcome == "rate_limited":
            state["billing_signal"] = "rate_or_quota_limit"
        elif outcome == "invalid_credentials":
            state["billing_signal"] = "credentials_rejected"


def _failure_category(error):
    status = _status_of(error)
    text = _text_of(error)
    if _is_no_credit(error):
        return "payment_required"
    if status == 429 or any(term in text for term in ("rate limit", "quota exceeded", "resource exhausted", "too many requests")):
        return "rate_limited"
    if _is_bad_key(error):
        return "invalid_credentials"
    if _is_model_gone(error):
        return "model_unavailable"
    if _is_busy(error):
        return "temporary_outage"
    return "request_failed"


def check_provider_health(provider):
    """Send one tiny live chat request to a provider's first configured model."""
    if provider not in PROVIDER_ORDER:
        return {"success": False, "health": "unknown_provider", "model": None}
    if not has_credentials(provider):
        return {"success": False, "health": "not_configured", "model": None}
    model = _models(provider)[0]
    messages = [{"role": "system", "content": "This is a brief service health check. Reply with OK only."},
                {"role": "user", "content": "OK"}]
    try:
        answer = _clean(_CALLERS[provider](model, messages, min(REQUEST_TIMEOUT, 12)))
        if not answer:
            raise RuntimeError("Provider returned an empty response")
    except Exception as error:
        outcome = _failure_category(error)
        _record_provider_health(provider, outcome, model=model, error=error)
        return {"success": False, "health": outcome, "model": model,
                "last_http_status": _status_of(error)}
    _record_provider_health(provider, "success", model=model)
    return {"success": True, "health": "healthy", "model": model}


def set_provider_enabled(provider, enabled):
    if provider not in PROVIDER_ORDER:
        return False
    _provider_enabled[provider] = bool(enabled)
    return True


def describe_chain():
    return " -> ".join(f"{s['name']}{'' if s['configured'] else ' (no key, skipped)'}"
                       for s in chain_status())


def reset_cooldowns():
    _cooldown_until.clear()
    _dead.clear()
    _discovered.clear()


# ------------------------------------------------------------ helpers
def _clean(text):
    # Qwen3 / reasoning models may include <think>...</think>; never show that to users
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    text = re.sub(r"^\s*<think>.*$", "", text, flags=re.DOTALL)      # thinking cut off by the token limit
    return text.strip()


def _status_of(error):
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def _text_of(error):
    return repr(error).lower()


def _is_bad_key(error):
    status = _status_of(error)
    text = _text_of(error)
    if status in (401, 403):
        # 403 can also mean "accept this model's license first": that is not a wrong key
        return not any(k in text for k in ("agreement", "license", "licence"))
    return status is None and any(k in text for k in ("unauthorized", "invalid api key", "invalid_api_key",
                                                      "api key not valid", "forbidden"))


def _is_no_credit(error):
    """Hugging Face answers 402 when the free monthly credits are used up."""
    status = _status_of(error)
    text = _text_of(error)
    return status == 402 or (status is None and any(
        k in text for k in ("payment required", "insufficient credits", "depleted your monthly")))


def _is_model_gone(error):
    """The model was retired / renamed / is not offered to this account. It will not work on a retry."""
    status = _status_of(error)
    if status in (404, 410):
        return True
    text = _text_of(error)
    return any(k in text for k in ("not supported by any provider", "model_not_found", "no longer available",
                                   "does not exist", "decommissioned", "has been deprecated", "model not found"))


def _is_busy(error):
    """Short-lived trouble worth ONE quick retry on the same model. (Only real statuses or words:
    request ids contain digits like 502 / 503 and must not count.)"""
    status = _status_of(error)
    if status is not None:
        return status in (502, 503, 504)
    return any(k in _text_of(error) for k in ("overloaded", "busy", "timed out", "timeout",
                                                "temporarily unavailable", "service unavailable"))


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
def _try_provider(provider, messages, deadline, models=None, callers=None, key=None, vision=False):
    """Try every model of one provider. Returns (answer, model) or (None, None).
    `models` / `callers` / `key` let the photo chain reuse this with its own models and cooldown.

    * a wrong key (401/403) or used-up credits (402) fail for every model -> stop at once
    * a model that is gone (404/410/"not supported") is remembered and skipped for an hour
    * if models were gone, the provider is asked which models it offers now and those are tried
    """
    callers = callers or _CALLERS
    key = key or provider
    stop = {"why": None}
    tried = []
    seen_gone = {"yes": False}
    last_error = {"value": None}

    def attempt(model):
        tried.append(model)
        if _dead.get((key, model), 0) > time.monotonic():
            seen_gone["yes"] = True
            return None
        for attempt_no in (1, 2):
            if time.monotonic() >= deadline:
                stop["why"] = "deadline"
                return None
            timeout = max(0.5, min(REQUEST_TIMEOUT, deadline - time.monotonic()))
            try:
                answer = _clean(callers[provider](model, messages, timeout)) or None
                if answer:
                    _record_provider_health(provider, "success", model=model, vision=vision)
                return answer
            except Exception as error:
                last_error["value"] = error
                print(f"AI ERROR ({LABELS[provider]} / {model}, try {attempt_no}):", repr(error)[:300])
                if _is_bad_key(error):
                    stop["why"] = "bad_key"
                    return None
                if _is_no_credit(error):
                    stop["why"] = "no_credit"
                    return None
                if _is_model_gone(error):
                    _dead[(key, model)] = time.monotonic() + DEAD_MODEL_SECONDS
                    seen_gone["yes"] = True
                    return None
                if attempt_no == 1 and _is_busy(error):
                    time.sleep(1.0)                     # one short retry on the same model
                    continue
                return None
        return None

    for model in (models or _models(provider)):
        answer = attempt(model)
        if answer:
            return answer, model
        if stop["why"]:
            break
    if not stop["why"] and seen_gone["yes"]:             # names were retired: use what is offered NOW
        for model in _discover_models(provider, vision):
            if model in tried:
                continue
            answer = attempt(model)
            if answer:
                return answer, model
            if stop["why"]:
                break
    if stop["why"] == "deadline":
        _record_provider_health(provider, "temporary_outage", model=tried[-1] if tried else None,
                                vision=vision, error=last_error["value"])
        return None, None
    outcome = _failure_category(last_error["value"]) if last_error["value"] else (
        "model_unavailable" if seen_gone["yes"] else "request_failed")
    _record_provider_health(provider, outcome, model=tried[-1] if tried else None,
                            vision=vision, error=last_error["value"])
    _cooldown_until[key] = time.monotonic() + {
        "bad_key": COOLDOWN_AFTER_BAD_KEY, "no_credit": COOLDOWN_AFTER_NO_CREDIT}.get(
        stop["why"], COOLDOWN_AFTER_FAILURE)
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
_discovered = {}                    # (provider, vision) -> (time, [model ids]) so lists are fetched once an hour
DISCOVERY_SECONDS = 3600
_NOT_CHAT = ("image", "tts", "live", "audio", "transcribe", "embedding", "robotics", "omni", "banana",
             "customtools", "computer", "veo", "lyria", "imagen")


def _http_get(url, headers):
    """One GET returning JSON. (Tests replace this.)"""
    response = httpx.get(url, headers=headers, timeout=6)
    response.raise_for_status()
    return response.json()


def _gemini_rank(model_id):
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", model_id)
    return (-(float(match.group(1)) if match else 0), "lite" in model_id, model_id)


def _discover_models(provider, vision=True):
    """Ask the provider which models it offers RIGHT NOW, because names are retired and renamed
    often. Only used after a configured / default model was found to be gone. Never raises."""
    cache_key = (provider, vision)
    cached = _discovered.get(cache_key)
    if cached and time.monotonic() - cached[0] < DISCOVERY_SECONDS:
        return cached[1]
    found = []
    try:
        if provider == "huggingface" and vision:
            data = _http_get("https://router.huggingface.co/v1/models",
                             {"Authorization": f"Bearer {config.HUGGINGFACE_API_KEY}"})
            for m in data.get("data", []):
                if "image" in ((m.get("architecture") or {}).get("input_modalities") or []):
                    found.append(m["id"])
        elif provider == "openrouter" and vision:
            data = _http_get("https://openrouter.ai/api/v1/models",
                             {"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
            for m in data.get("data", []):
                price = m.get("pricing") or {}
                if ("image" in ((m.get("architecture") or {}).get("input_modalities") or [])
                        and str(price.get("prompt")) in ("0", "0.0") and str(price.get("completion")) in ("0", "0.0")):
                    found.append(m["id"])
        elif provider == "groq" and vision:
            data = _http_get("https://api.groq.com/openai/v1/models",
                             {"Authorization": f"Bearer {config.GROQ_API_KEY}"})
            found = [m["id"] for m in data.get("data", [])
                     if any(k in m.get("id", "").lower()
                            for k in ("qwen3.", "muse-spark", "vision", "scout", "maverick", "-vl"))]
        elif provider == "google":                      # works for text AND photos: all Gemini Flash models see images
            data = _http_get("https://generativelanguage.googleapis.com/v1beta/openai/models",
                             {"Authorization": f"Bearer {config.GOOGLE_API_KEY}"})
            ids = [m.get("id", "").split("/")[-1] for m in data.get("data", [])]
            found = sorted((i for i in ids if i.startswith("gemini") and "flash" in i
                            and not any(k in i for k in _NOT_CHAT)), key=_gemini_rank)
    except Exception as error:
        print(f"AI: could not list {LABELS[provider]} models:", repr(error)[:150])
    found = found[:4]
    _discovered[cache_key] = (time.monotonic(), found)
    if found:
        print(f"AI: {LABELS[provider]} models available now:", ", ".join(found))
    return found


_discover_vision_models = lambda provider: _discover_models(provider, True)     # older name


def _vision_models(provider):
    """Your VISION_MODEL setting first, then the built-in defaults (no network involved)."""
    setting = {"huggingface": "HF_VISION_MODEL", "cloudflare": "CLOUDFLARE_VISION_MODEL",
               "groq": "GROQ_VISION_MODEL", "google": "GOOGLE_VISION_MODEL",
               "openrouter": "OPENROUTER_VISION_MODEL"}[provider]
    configured = _split(getattr(config, setting, None))
    return configured + [m for m in DEFAULT_VISION_MODELS[provider] if m not in configured]


def _vision_callers(max_tokens=None):
    def hf(model, messages, timeout):
        global _hf_client
        if max_tokens is None and timeout >= REQUEST_TIMEOUT:
            if _hf_client is None:
                from huggingface_hub import InferenceClient
                _hf_client = InferenceClient(api_key=config.HUGGINGFACE_API_KEY, provider="auto",
                                             timeout=REQUEST_TIMEOUT)
            client = _hf_client
            tokens = VISION_MAX_TOKENS
        else:
            from huggingface_hub import InferenceClient
            client = InferenceClient(api_key=config.HUGGINGFACE_API_KEY, provider="auto",
                                     timeout=timeout)
            tokens = max_tokens or VISION_MAX_TOKENS
        return client.chat.completions.create(
            model=model, messages=messages, max_tokens=tokens,
            temperature=0.1).choices[0].message.content

    cloudflare_tokens = max_tokens or VISION_MAX_TOKENS
    reasoning_tokens = max_tokens or VISION_REASONING_TOKENS
    def openai_style(url_of, key_name, extra=None, tokens=VISION_MAX_TOKENS):
        return lambda model, messages, timeout: _openai_style(
            url_of() if callable(url_of) else url_of, getattr(config, key_name), model, messages,
            timeout, max_tokens=tokens, headers=extra)

    return {
        "huggingface": hf,
        "cloudflare": openai_style(
            lambda: f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}"
                    "/ai/v1/chat/completions", "CLOUDFLARE_API_KEY", tokens=cloudflare_tokens),
        "groq": openai_style("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY",
                             tokens=reasoning_tokens),
        "google": openai_style("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                               "GOOGLE_API_KEY", tokens=reasoning_tokens),
        "openrouter": openai_style("https://openrouter.ai/api/v1/chat/completions",
                                   "OPENROUTER_API_KEY", {"X-Title": "NEMSAI"},
                                   tokens=cloudflare_tokens),
    }


def vision_available():
    return any(is_configured(p) for p in VISION_PROVIDER_ORDER)


def ask_vision(system_prompt, user_text, image_b64, mime="image/jpeg", *,
               total_timeout=None, provider_timeout=None, max_tokens=None):
    """Ask a vision-language model about one image or a list of (base64, MIME) images.
    Returns (answer, provider, model);
    (None, None, None) when no provider could answer (the caller then falls back to manual review)."""
    if not vision_available():
        print("AI ERROR: no vision provider key is set (HF_API_KEY, CLOUDFLARE_*, GROQ_API_KEY, "
              "GOOGLE_API_KEY or OPENROUTER_API_KEY)")
        return None, None, None
    images = image_b64 if isinstance(image_b64, (list, tuple)) else [(image_b64, mime)]
    content = [{"type": "text", "text": user_text}]
    content.extend({"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{encoded}"}}
                   for encoded, image_mime in images)
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": content}]
    total_timeout = VISION_TOTAL_TIMEOUT if total_timeout is None else max(1, float(total_timeout))
    provider_timeout = VISION_PROVIDER_TIMEOUT if provider_timeout is None else max(0.5, float(provider_timeout))
    callers = _vision_callers() if max_tokens is None else _vision_callers(max_tokens=max_tokens)
    deadline = time.monotonic() + total_timeout
    for provider in VISION_PROVIDER_ORDER:
        key = provider + ":vision"
        if not is_configured(provider) or _cooldown_until.get(key, 0) > time.monotonic():
            continue
        provider_deadline = min(deadline, time.monotonic() + provider_timeout)
        answer, model = _try_provider(provider, messages, provider_deadline, models=_vision_models(provider),
                                      callers=callers, key=key, vision=True)
        if answer:
            if provider != VISION_PROVIDER_ORDER[0]:
                print(f"AI: photo analysed by {LABELS[provider]} ({model})")
            return answer, provider, model
        if time.monotonic() >= provider_deadline and provider_deadline < deadline:
            _cooldown_until[key] = time.monotonic() + COOLDOWN_AFTER_FAILURE
    return None, None, None
