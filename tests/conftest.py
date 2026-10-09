import os, sys, pathlib
import pytest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    """Point the store at a scratch data dir so tests never touch real data."""
    from engine import store
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    return tmp_path
