"""Tests for the optional-Opik guards in `utils.tracing`.

opik is an optional extra (the `tracing` extra): present in local dev, absent in CI and the
production image. These tests exercise both the "opik installed" and "opik absent" paths
deterministically by manipulating `sys.modules`, so they give the same result regardless of
whether opik is actually installed in the running environment. The lazy (function-local)
imports in `tracing.py` are what let a test patch `sys.modules` before the import runs.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

from dial_deep_research.utils import tracing


def _install_fake_opik(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tracer_cls: object | None = None,
    configure: object | None = None,
) -> None:
    """Inject a fake `opik` package tree so the lazy imports resolve without the real
    dependency — lets us exercise the "opik installed" paths even in CI."""
    opik = types.ModuleType("opik")
    integrations = types.ModuleType("opik.integrations")
    langchain = types.ModuleType("opik.integrations.langchain")
    if configure is not None:
        opik.configure = configure  # type: ignore[attr-defined]
    if tracer_cls is not None:
        langchain.OpikTracer = tracer_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opik", opik)
    monkeypatch.setitem(sys.modules, "opik.integrations", integrations)
    monkeypatch.setitem(sys.modules, "opik.integrations.langchain", langchain)


def _hide_opik(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force `import opik` to raise ImportError regardless of whether it is installed —
    reproduces the production image, where the `tracing` extra is omitted."""
    for name in ("opik", "opik.integrations", "opik.integrations.langchain"):
        monkeypatch.setitem(sys.modules, name, None)


# --- build_opik_tracer ---------------------------------------------------------------


def test_build_opik_tracer_disabled_returns_none() -> None:
    assert tracing.build_opik_tracer(tracing_enabled=False) is None


def test_build_opik_tracer_present_builds_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer_cls = MagicMock(name="OpikTracer")
    _install_fake_opik(monkeypatch, tracer_cls=tracer_cls)

    result = tracing.build_opik_tracer(tracing_enabled=True, thread_id="thread-1")

    tracer_cls.assert_called_once_with(thread_id="thread-1")
    assert result is tracer_cls.return_value


def test_build_opik_tracer_absent_degrades_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_opik(monkeypatch)
    assert tracing.build_opik_tracer(tracing_enabled=True, thread_id="thread-1") is None


# --- configure_opik ------------------------------------------------------------------


def test_configure_opik_disabled_does_not_touch_opik(monkeypatch: pytest.MonkeyPatch) -> None:
    configure = MagicMock()
    _install_fake_opik(monkeypatch, configure=configure)
    tracing.configure_opik(tracing_enabled=False, project_name="proj")
    configure.assert_not_called()


def test_configure_opik_present_configures(monkeypatch: pytest.MonkeyPatch) -> None:
    configure = MagicMock()
    _install_fake_opik(monkeypatch, configure=configure)
    tracing.configure_opik(tracing_enabled=True, project_name="proj")
    configure.assert_called_once_with(use_local=True, project_name="proj")


def test_configure_opik_absent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fail fast: enabling tracing without the extra must abort startup, not run untraced.
    _hide_opik(monkeypatch)
    with pytest.raises(RuntimeError) as excinfo:
        tracing.configure_opik(tracing_enabled=True, project_name="proj")
    assert isinstance(excinfo.value.__cause__, ImportError)  # preserved via `raise ... from e`
