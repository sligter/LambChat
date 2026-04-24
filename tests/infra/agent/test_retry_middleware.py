from __future__ import annotations

from langchain_core.messages import AIMessage

from src.infra.agent.middleware.retry import ModelFallbackMiddleware


class _Request:
    def __init__(self, model) -> None:
        self.model = model

    def override(self, **kwargs):
        return _Request(kwargs.get("model", self.model))


async def test_fallback_runs_when_primary_raises_non_retryable_error() -> None:
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            raise ValueError("bad request payload")
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"


async def test_fallback_runs_when_primary_returns_empty_content() -> None:
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            return AIMessage(content="")
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"


async def test_fallback_runs_when_primary_returns_truncated_content() -> None:
    primary_model = object()
    fallback_model = object()
    middleware = ModelFallbackMiddleware(fallback_model="openai/fallback-model")
    middleware._fallback_llm = fallback_model

    async def handler(request):
        if request.model is primary_model:
            return AIMessage(
                content="Here is the result:",
                response_metadata={"stop_reason": "max_tokens"},
            )
        return AIMessage(content="fallback answer")

    result = await middleware.awrap_model_call(_Request(primary_model), handler)

    assert result.content == "fallback answer"
