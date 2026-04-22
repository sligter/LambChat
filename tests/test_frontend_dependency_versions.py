import json
from pathlib import Path

FRONTEND_DIR = Path("frontend")


def test_react_and_react_dom_are_locked_to_the_same_version() -> None:
    package_json = json.loads((FRONTEND_DIR / "package.json").read_text())
    package_lock = json.loads((FRONTEND_DIR / "package-lock.json").read_text())

    dependencies = package_json["dependencies"]
    assert dependencies["react"] == dependencies["react-dom"]
    assert not dependencies["react"].startswith("^")

    packages = package_lock["packages"]
    assert (
        packages["node_modules/react"]["version"] == packages["node_modules/react-dom"]["version"]
    )
