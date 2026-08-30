import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).parents[1]


def test_compose_security_contract() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    assert "ports:" not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "target: /config" in compose
    assert "--enable-get" not in compose
    assert "--enable-set" not in compose
    assert "--allow-origin" not in compose
    assert "--no-stateless" in compose
    assert "name: fhem-mcp" in compose
    assert "/status" in compose


def test_deployment_versions_are_synchronized() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    manifest = (ROOT / "server" / "fhem-mcp.yaml").read_text()
    compose = (ROOT / "compose.yaml").read_text()
    stdio_server = (ROOT / "src" / "fhem_mcp" / "stdio_server.py").read_text()
    assert f"version: {version}" in manifest
    assert f"ghcr.io/sidey79/fhem-mcp:{version}" in manifest
    assert f"image: ghcr.io/sidey79/fhem-mcp:{version}" in compose
    assert f'"version": "{version}"' in stdio_server


def test_proxy_dependency_is_exactly_pinned_and_managed_by_renovate() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    proxy_deps = pyproject["project"]["optional-dependencies"]["proxy"]
    pin = re.fullmatch(r"mcp-proxy==(?P<version>\d+(?:\.\d+)+)", proxy_deps[0])
    assert pin is not None

    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "[proxy]" in dockerfile

    renovate = json.loads((ROOT / "renovate.json").read_text())
    assert "customManagers:dockerfileVersions" in renovate["extends"]
    package_rules = renovate["packageRules"]
    assert any(
        rule.get("matchManagers") == ["pep621"] and rule.get("bumpVersion") == "patch"
        for rule in package_rules
    )
