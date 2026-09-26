import json

import httpx
import pytest

from tendergraph.rag.errors import GenerationUnavailable
from tendergraph.rag.ollama_provider import OllamaProvider
from tendergraph.rag.settings import RAGSettings


def settings(**kwargs):
    return RAGSettings(_env_file=None, provider="ollama", model="local-test", **kwargs)


def test_ollama_request_is_local_bounded_and_non_streaming():
    def respond(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/generate"
        body = json.loads(request.content)
        assert body == {
            "model": "local-test",
            "system": "rules",
            "prompt": "evidence",
            "stream": False,
            "options": {"temperature": 0, "num_predict": 800},
        }
        return httpx.Response(200, json={"done": True, "response": " Fact [T1]. "})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = OllamaProvider(settings(), client=client)
        assert (
            provider.generate(system_prompt="rules", user_prompt="evidence")
            == "Fact [T1]."
        )
        provider.close()
        assert not client.is_closed


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"done": True, "response": " "},
        {"done": False, "response": "partial [T1]"},
        {"done": True, "response": "partial [T1]", "done_reason": "length"},
        {"done": True, "response": "text", "error": "failed"},
    ],
)
def test_invalid_ollama_responses(payload):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(GenerationUnavailable),
    ):
        OllamaProvider(settings(), client=client).generate(
            system_prompt="s", user_prompt="u"
        )


@pytest.mark.parametrize("status", [302, 404, 500])
def test_ollama_http_failures(status):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": "x"})
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(GenerationUnavailable),
    ):
        OllamaProvider(settings(), client=client).generate(
            system_prompt="s", user_prompt="u"
        )


def test_ollama_timeout_has_no_retry():
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(GenerationUnavailable),
    ):
        OllamaProvider(settings(), client=client).generate(
            system_prompt="s", user_prompt="u"
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost.evil.example",
        "http://user@localhost:11434",
        "http://127.0.0.1:11434/path",
        "http://127.0.0.1:11434?redirect=x",
    ],
)
def test_ollama_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(ValueError, match="local HTTP origin"):
        settings(ollama_url=url)


def test_generation_requires_explicit_model():
    with pytest.raises(ValueError, match="RAG_MODEL"):
        RAGSettings(_env_file=None, provider="openai", model="")


def test_api_key_is_not_in_settings_repr():
    config = RAGSettings(
        _env_file=None, provider="evidence", OPENAI_API_KEY="secret-test"
    )
    assert "secret-test" not in repr(config)
