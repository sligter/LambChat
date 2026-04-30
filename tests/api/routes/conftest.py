from __future__ import annotations

import sys
import types


class _FakeBackendModule(types.ModuleType):
    def __getattr__(self, name: object) -> object:
        if name in ("clear_user_context", "set_user_context"):
            return lambda *a: None
        raise AttributeError(name)


if "src.infra.backend" not in sys.modules:
    sys.modules["src.infra.backend"] = _FakeBackendModule("src.infra.backend")
if "src.infra.backend.context" not in sys.modules:
    sys.modules["src.infra.backend.context"] = _FakeBackendModule("src.infra.backend.context")
