"""Verify the installed project and the development environment contract."""

from importlib import metadata
from pathlib import Path

import marketlens


def test_installed_distribution_imports_src_package():
    assert metadata.version("marketlens-ai") == "0.1.0"
    assert Path(marketlens.__file__).resolve().parent.name == "marketlens"
    requirements = metadata.requires("marketlens-ai") or []
    assert any(requirement.startswith("pydantic") for requirement in requirements)


def test_pytest_excludes_external_checks_by_default(pytestconfig):
    assert "not model_smoke" in pytestconfig.option.markexpr
    assert "not live_api" in pytestconfig.option.markexpr
    assert any(marker.startswith("model_smoke:") for marker in pytestconfig.getini("markers"))
    assert any(marker.startswith("live_api:") for marker in pytestconfig.getini("markers"))
