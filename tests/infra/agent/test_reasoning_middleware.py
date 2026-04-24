from __future__ import annotations

from langchain_core.messages import AIMessage

from src.infra.agent.middleware import (
    EmptyContentRetryMiddleware,
    _is_empty_content,
)


def test_reasoning_only_message_is_still_empty_without_text_or_tool_calls() -> None:
    message = AIMessage(content="", additional_kwargs={"reasoning_content": "thinking"})

    assert _is_empty_content(message) is True


async def test_empty_content_retry_retries_reasoning_only_response() -> None:
    middleware = EmptyContentRetryMiddleware(max_retries=1, retry_delay=0)
    responses = iter(
        [
            AIMessage(content="", additional_kwargs={"reasoning_content": "thinking"}),
            AIMessage(content="final answer"),
        ]
    )
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return next(responses)

    result = await middleware.awrap_model_call(None, handler)

    assert result.content == "final answer"
    assert calls == 2
