from __future__ import annotations

import builtins
import importlib
import sys


def test_oauth_module_import_does_not_eagerly_load_authlib(monkeypatch) -> None:
    module_name = "src.infra.auth.oauth"
    sys.modules.pop(module_name, None)

    authlib_imports: list[str] = []
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("authlib"):
            authlib_imports.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    oauth_module = importlib.import_module(module_name)

    assert oauth_module.OAuthService is not None
    assert authlib_imports == []
