from contextlib import ExitStack

from tendergraph.rag.ollama_provider import OllamaProvider
from tendergraph.rag.openai_provider import OpenAIProvider, OpenAIProviderConfig
from tendergraph.rag.pipeline import (
    EvidenceBackend,
    EvidenceReranker,
    SearchBackend,
    TenderAnswerService,
)
from tendergraph.rag.service import GroundedRAGService
from tendergraph.rag.settings import RAGSettings


def build_answer_service(
    search: SearchBackend,
    repository: EvidenceBackend,
    settings: RAGSettings,
    resources: ExitStack,
) -> TenderAnswerService:
    generator = None
    if settings.provider == "ollama":
        local = OllamaProvider(settings)
        resources.callback(local.close)
        generator = GroundedRAGService(local)
    elif settings.provider == "openai":
        remote = OpenAIProvider(
            OpenAIProviderConfig(
                model=settings.model,
                max_output_tokens=settings.max_output_tokens,
                timeout_seconds=settings.timeout_seconds,
            ),
            api_key=(
                settings.openai_api_key.get_secret_value()
                if settings.openai_api_key
                else None
            ),
        )
        resources.callback(remote.close)
        generator = GroundedRAGService(remote)

    reranker: EvidenceReranker | None = None
    if settings.rerank:
        from tendergraph.search.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()
    return TenderAnswerService(
        search,
        repository,
        mode=settings.provider,
        generator=generator,
        reranker=reranker,
        max_context_chars=settings.max_context_chars,
    )
