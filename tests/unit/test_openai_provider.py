from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai import OpenAI

from tendergraph.rag.openai_provider import (
    OpenAIProvider,
    OpenAIProviderConfig,
)


class FakeResponses:
    def __init__(
        self,
        output_text: str,
    ) -> None:
        self.output_text = output_text
        self.calls: list[
            dict[str, object]
        ] = []

    def create(
        self,
        **kwargs: object,
    ) -> SimpleNamespace:
        self.calls.append(kwargs)

        return SimpleNamespace(
            output_text=self.output_text
        )


class FakeClient:
    def __init__(
        self,
        output_text: str,
    ) -> None:
        self.responses = FakeResponses(
            output_text
        )


def as_openai(
    client: FakeClient,
) -> OpenAI:
    return cast(
        OpenAI,
        cast(Any, client),
    )


def test_openai_provider_generates_text() -> None:
    fake = FakeClient(
        "Grounded answer [T1]."
    )

    provider = OpenAIProvider(
        OpenAIProviderConfig(
            model="test-model",
            max_output_tokens=321,
        ),
        client=as_openai(fake),
    )

    result = provider.generate(
        system_prompt="System",
        user_prompt="Evidence",
    )

    assert result == (
        "Grounded answer [T1]."
    )

    assert fake.responses.calls == [
        {
            "model": "test-model",
            "instructions": "System",
            "input": "Evidence",
            "max_output_tokens": 321,
        }
    ]


def test_openai_provider_rejects_empty_output() -> None:
    provider = OpenAIProvider(
        client=as_openai(
            FakeClient("   ")
        )
    )

    with pytest.raises(
        RuntimeError,
        match="empty response",
    ):
        provider.generate(
            system_prompt="System",
            user_prompt="Evidence",
        )


def test_openai_provider_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="OPENAI_API_KEY",
    ):
        OpenAIProvider()
