from __future__ import annotations

import deepagents.middleware.summarization as summarization

from src.infra.llm.deepagents_patch import apply_deepagents_patches
from src.kernel.config import settings


class _ModelWithoutProfile:
    profile = None


def test_deepagents_patch_uses_configured_fallback_window(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DEEPAGENT_DEFAULT_MAX_INPUT_TOKENS", 64000, raising=False)
    apply_deepagents_patches()

    defaults = summarization.compute_summarization_defaults(_ModelWithoutProfile())

    assert defaults["trigger"] == ("tokens", 54400)
    assert defaults["keep"] == ("tokens", 6400)
    assert defaults["truncate_args_settings"]["trigger"] == ("tokens", 54400)
    assert defaults["truncate_args_settings"]["keep"] == ("tokens", 6400)
