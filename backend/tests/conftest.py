import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """每个测试使用独立 DuckDB 文件。"""
    from app import config, db as db_mod

    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "_conn", None)
    yield db_mod.get_conn()
    db_mod.get_conn().close()
    monkeypatch.setattr(db_mod, "_conn", None)
