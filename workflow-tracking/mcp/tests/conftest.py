"""Test configuration — ensure task_tool package is importable."""

import sys
from pathlib import Path

import pytest

# Add src/ to sys.path so task_tool is importable in unit tests.
# MCP transport tests use subprocess with PYTHONPATH instead.
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


@pytest.fixture(autouse=True)
def _reset_session_state():
    """Reset the module-level session tracking between tests."""
    from task_tool.state import _reset_session
    _reset_session()
    yield
    _reset_session()
