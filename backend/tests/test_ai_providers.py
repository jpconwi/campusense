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
    assert groq_models == systemAi._models("groq") and len(groq_models) == 2


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
