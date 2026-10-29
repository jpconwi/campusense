"""The AI provider chain: Hugging Face > Cloudflare > Groq > Google > OpenRouter."""

import pytest

from app import config
from app.model import systemAi

ORDER = ["huggingface", "cloudflare", "groq", "google", "openrouter"]


@pytest.fixture
def chain(monkeypatch):
    """All five providers configured; every call is recorded and each one can be made to fail."""
    for name, value in (("HUGGINGFACE_API_KEY", "k"), ("CLOUDFLARE_API_KEY", "k"),
                        ("CLOUDFLARE_ACCOUNT_ID", "acc"), ("GROQ_API_KEY", "k"),
                        ("GOOGLE_API_KEY", "k"), ("OPENROUTER_API_KEY", "k")):
        monkeypatch.setattr(config, name, value)
    for name in ("HUGGINGFACE_MODEL", "CLOUDFLARE_MODEL", "GROQ_MODEL", "GOOGLE_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(systemAi.time, "sleep", lambda s: None)
    systemAi.reset_cooldowns()
    state = {"calls": [], "fail": set(), "error": RuntimeError("boom")}

    def make(provider):
        def call(model, messages, timeout):
            state["calls"].append((provider, model))
            if provider in state["fail"]:
                raise state["error"]
            return f"answer from {provider}"
        return call

    monkeypatch.setattr(systemAi, "_CALLERS", {p: make(p) for p in ORDER})
    yield state
    systemAi.reset_cooldowns()


def test_order_is_exactly_the_required_one():
    assert list(systemAi.PROVIDER_ORDER) == ORDER


def test_hugging_face_is_primary(chain):
    answer, who = systemAi.ask_model_with_source("sys", "hi")
    assert (answer, who) == ("answer from huggingface", "huggingface")
    assert [p for p, _ in chain["calls"]] == ["huggingface"]          # nobody else was called


@pytest.mark.parametrize("failing,expected", [
    (["huggingface"], "cloudflare"),
    (["huggingface", "cloudflare"], "groq"),
    (["huggingface", "cloudflare", "groq"], "google"),
    (["huggingface", "cloudflare", "groq", "google"], "openrouter"),
])
def test_each_fallback_in_order(chain, failing, expected):
    chain["fail"] = set(failing)
    answer, who = systemAi.ask_model_with_source("sys", "hi")
    assert who == expected and answer == f"answer from {expected}"
    tried = []
    for p, _ in chain["calls"]:                                         # providers in the order tried
        if p not in tried:
            tried.append(p)
    assert tried == ORDER[:ORDER.index(expected) + 1]


def test_everything_down_returns_none(chain):
    chain["fail"] = set(ORDER)
    assert systemAi.ask_model("sys", "hi") is None


def test_providers_without_keys_are_skipped(chain, monkeypatch):
    monkeypatch.setattr(config, "HUGGINGFACE_API_KEY", "")
    monkeypatch.setattr(config, "CLOUDFLARE_ACCOUNT_ID", "")            # Cloudflare needs BOTH values
    assert systemAi.ask_model_with_source("sys", "hi")[1] == "groq"
    assert [s["configured"] for s in systemAi.chain_status()] == [False, False, True, True, True]


def test_models_inside_a_provider_are_tried_before_the_next_provider(chain):
    chain["fail"] = {"groq", "huggingface", "cloudflare"}
    systemAi.ask_model("sys", "hi")
    groq_models = [m for p, m in chain["calls"] if p == "groq"]
    assert groq_models == systemAi._models("groq") and len(groq_models) >= 2


def test_failed_provider_is_skipped_on_the_next_question(chain):
    chain["fail"] = {"huggingface"}
    systemAi.ask_model("sys", "one")
    chain["calls"].clear()
    assert systemAi.ask_model_with_source("sys", "two")[1] == "cloudflare"
    assert all(p != "huggingface" for p, _ in chain["calls"])           # cooling down, not retried
    systemAi.reset_cooldowns()                                          # cooldown over -> primary again
    chain["fail"] = set()
    assert systemAi.ask_model_with_source("sys", "three")[1] == "huggingface"


def test_wrong_key_skips_the_rest_of_that_provider(chain):
    class Unauthorized(Exception):
        class response:
            status_code = 401
    chain["fail"], chain["error"] = {"huggingface"}, Unauthorized()
    systemAi.ask_model("sys", "hi")
    assert [p for p, _ in chain["calls"]].count("huggingface") == 1     # no point trying other models


def test_busy_is_retried_once_then_moves_on(chain):
    chain["error"] = RuntimeError("503 Service overloaded")
    chain["fail"] = {"huggingface"}
    systemAi.ask_model("sys", "hi")
    hf = [m for p, m in chain["calls"] if p == "huggingface"]
    assert len(hf) == 2 * len(systemAi._models("huggingface"))          # each model: try + 1 retry


def test_all_cooling_down_still_gets_an_answer(chain):
    chain["fail"] = set(ORDER)
    systemAi.ask_model("sys", "one")                                    # everything now cooling down
    chain["fail"] = set()
    assert systemAi.ask_model_with_source("sys", "two")[1] == "huggingface"


def test_think_tags_are_removed(chain, monkeypatch):
    monkeypatch.setitem(systemAi._CALLERS, "huggingface", lambda m, msgs, t: "<think>x</think>Hello")
    assert systemAi.ask_model("sys", "hi") == "Hello"


def test_old_env_names_still_work_for_hugging_face(monkeypatch):
    monkeypatch.setattr(config, "HUGGINGFACE_MODEL", "my/model")
    assert systemAi._models("huggingface")[0] == "my/model"
    assert "Qwen/Qwen2.5-7B-Instruct" in systemAi._models("huggingface")


def test_request_shapes(monkeypatch):
    """Each fallback calls the right URL with the right key."""
    for name, value in (("CLOUDFLARE_API_KEY", "cf"), ("CLOUDFLARE_ACCOUNT_ID", "ACC"),
                        ("GROQ_API_KEY", "gq"), ("GOOGLE_API_KEY", "gg"), ("OPENROUTER_API_KEY", "or")):
        monkeypatch.setattr(config, name, value)
    seen = {}

    def fake_post(url, headers, payload, timeout):
        seen[url] = (headers["Authorization"], payload["model"])
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(systemAi, "_http_post", fake_post)
    msgs = [{"role": "user", "content": "hi"}]
    for provider in ("cloudflare", "groq", "google", "openrouter"):
        assert systemAi._CALLERS[provider](systemAi._models(provider)[0], msgs, 5) == "ok"
    assert seen["https://api.cloudflare.com/client/v4/accounts/ACC/ai/v1/chat/completions"][0] == "Bearer cf"
    assert seen["https://api.groq.com/openai/v1/chat/completions"][0] == "Bearer gq"
    assert seen["https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"][0] == "Bearer gg"
    assert seen["https://openrouter.ai/api/v1/chat/completions"][0] == "Bearer or"


def test_admin_can_see_the_chain_without_keys(admin, student):
    data = admin.get("/api/admin/ai-status").json()
    assert [p["provider"] for p in data["providers"]] == ORDER
    assert "api_key" not in str(data).lower()
    assert student.get("/api/admin/ai-status").status_code == 404       # admin API stays hidden


def test_real_http_layer_parses_replies_and_reports_status(monkeypatch):
    import httpx
    sent = {}

    def handler(request):
        sent["auth"] = request.headers["authorization"]
        if request.url.path.endswith("/bad"):
            return httpx.Response(401, json={"error": "nope"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(systemAi.httpx, "post",
                        lambda url, headers, json, timeout: httpx.Client(transport=transport).post(
                            url, headers=headers, json=json, timeout=timeout))
    data = systemAi._http_post("https://x.test/ok", {"Authorization": "Bearer z"}, {"a": 1}, 5)
    assert data["choices"][0]["message"]["content"] == "hello" and sent["auth"] == "Bearer z"
    with pytest.raises(httpx.HTTPStatusError) as err:
        systemAi._http_post("https://x.test/bad", {"Authorization": "Bearer z"}, {}, 5)
    assert systemAi._is_bad_key(err.value)


# ---------------------------------------------------- retired models / no credit (seen in the Render log)
class _Status(Exception):
    def __init__(self, code, text=""):
        super().__init__(text or f"HTTP {code}")
        self.response = type("R", (), {"status_code": code})()


def test_error_classes_are_not_fooled_by_request_ids():
    # a request id such as "Root=1-6ae2c188-...-502a..." must not look like a 502 / 503
    err = RuntimeError("BadRequest (Request ID: Root=1-6ae2c188-6050698e6d437cbd20ea875d-503-502) not supported")
    assert not systemAi._is_busy(err)
    assert systemAi._is_busy(_Status(503)) and not systemAi._is_busy(_Status(400))
    assert systemAi._is_no_credit(_Status(402)) and not systemAi._is_no_credit(_Status(429))
    assert systemAi._is_model_gone(_Status(404)) and systemAi._is_model_gone(_Status(410))
    assert systemAi._is_model_gone(RuntimeError("The requested model 'x' is not supported by any provider you have enabled"))
    assert systemAi._is_bad_key(_Status(401)) and not systemAi._is_bad_key(_Status(404))
    assert not systemAi._is_bad_key(_Status(403, "model license agreement not accepted"))


def test_a_retired_model_is_skipped_next_time(chain):
    gone = _Status(410, "410 Gone")
    first_model = systemAi._models("cloudflare")[0]
    chain["fail"] = {"huggingface"}

    def cf(model, messages, timeout):
        chain["calls"].append(("cloudflare", model))
        if model == first_model:
            raise gone
        return "answer from cloudflare"
    systemAi._CALLERS["cloudflare"] = cf
    assert systemAi.ask_model("sys", "one") == "answer from cloudflare"
    systemAi._cooldown_until.clear()                                    # only the dead-model memory stays
    chain["calls"].clear()
    systemAi.ask_model("sys", "two")
    assert (("cloudflare", first_model)) not in chain["calls"]          # not tried again


def test_used_up_credits_skip_the_provider_for_a_long_time(chain):
    chain["fail"], chain["error"] = {"huggingface"}, _Status(402, "402 Payment Required")
    systemAi.ask_model("sys", "one")
    assert [p for p, _ in chain["calls"]].count("huggingface") == 1     # no point trying the other models
    assert systemAi._cooldown_until["huggingface"] - systemAi.time.monotonic() > 1000


def test_vision_chain_has_cloudflare_and_the_same_order():
    assert list(systemAi.VISION_PROVIDER_ORDER) == ORDER
    assert all(systemAi.DEFAULT_VISION_MODELS[p] for p in ORDER)
    assert "qwen/qwen3.8-27b" in systemAi.DEFAULT_VISION_MODELS["groq"]            # llama-4-scout is gone
    assert not any("2.5-flash" in m for m in systemAi.DEFAULT_MODELS["google"] + systemAi.DEFAULT_VISION_MODELS["google"])
    assert "@cf/meta/llama-3.1-8b-instruct" not in systemAi.DEFAULT_MODELS["cloudflare"]     # 410 Gone


def test_google_models_are_discovered_when_the_names_are_gone(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "k")
    systemAi.reset_cooldowns()
    monkeypatch.setattr(systemAi, "_http_get", lambda u, h: {"data": [
        {"id": "models/gemini-3.6-flash"}, {"id": "models/gemini-3.8-flash"},
        {"id": "models/gemini-3.8-flash-tts"}, {"id": "models/gemini-3.1-flash-image"},
        {"id": "models/gemini-3.5-flash-lite"}, {"id": "models/gemma-4-31b-it"}]})
    found = systemAi._discover_models("google", False)
    assert found[0] == "gemini-3.8-flash" and "gemini-3.8-flash-tts" not in found
    assert "gemini-3.1-flash-image" not in found and "gemma-4-31b-it" not in found
    systemAi.reset_cooldowns()


def test_discovered_models_are_tried_after_the_defaults_are_gone(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "k")
    monkeypatch.setattr(config, "GOOGLE_MODEL", None)
    systemAi.reset_cooldowns()
    monkeypatch.setattr(systemAi, "_http_get", lambda u, h: {"data": [{"id": "models/gemini-9.9-flash"}]})
    called = []

    def google(model, messages, timeout):
        called.append(model)
        if model != "gemini-9.9-flash":
            raise _Status(404, "404 NOT_FOUND this model is no longer available")
        return "hello"
    answer, model = systemAi._try_provider("google", [{"role": "user", "content": "x"}],
                                           systemAi.time.monotonic() + 30, callers={"google": google})
    assert (answer, model) == ("hello", "gemini-9.9-flash")
    assert called[:3] == systemAi._models("google")                      # all the old names were tried first
    systemAi.reset_cooldowns()


def test_old_model_settings_cannot_block_the_defaults(monkeypatch):
    """Render still had CLOUDFLARE_MODEL=@cf/meta/llama-3.1-8b-instruct (retired, 410) set."""
    monkeypatch.setattr(config, "CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct")
    monkeypatch.setattr(config, "GOOGLE_MODEL", "gemini-2.5-flash,gemini-flash-latest")
    cf = systemAi._models("cloudflare")
    assert cf[0] == "@cf/meta/llama-3.1-8b-instruct"                       # yours first
    assert set(systemAi.DEFAULT_MODELS["cloudflare"]) <= set(cf)           # defaults still there
    google = systemAi._models("google")
    assert google[:2] == ["gemini-2.5-flash", "gemini-flash-latest"] and "gemini-3.8-flash" in google
    assert len(google) == len(set(google))                                 # no duplicates
