"""DuckDB 连接与建表。单文件库，应用内使用一个带锁的连接。"""
import threading
from contextlib import contextmanager

import duckdb

from .config import DB_PATH

_lock = threading.RLock()
_conn: duckdb.DuckDBPyConnection | None = None

SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS seq_meter START 1;
CREATE SEQUENCE IF NOT EXISTS seq_reading START 1;
CREATE SEQUENCE IF NOT EXISTS seq_tariff START 1;
CREATE SEQUENCE IF NOT EXISTS seq_period START 1;

CREATE TABLE IF NOT EXISTS meters (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_meter'),
    code        VARCHAR NOT NULL UNIQUE,
    name        VARCHAR NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_reading'),
    meter_id    INTEGER NOT NULL REFERENCES meters(id),
    read_at     TIMESTAMP NOT NULL,           -- 北京时间 naive
    reading_kwh DECIMAL(18, 6) NOT NULL,      -- 单向电表累计读数
    flag        VARCHAR NOT NULL DEFAULT 'normal', -- normal | reset | replacement
    note        VARCHAR NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE(meter_id, read_at)
);

CREATE TABLE IF NOT EXISTS tariffs (
    id             INTEGER PRIMARY KEY DEFAULT nextval('seq_tariff'),
    name           VARCHAR NOT NULL,
    effective_date DATE NOT NULL,             -- 生效日期
    day_type       VARCHAR NOT NULL,          -- workday | holiday
    note           VARCHAR NOT NULL DEFAULT '',
    created_at     TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE(effective_date, day_type)
);

CREATE TABLE IF NOT EXISTS tariff_periods (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_period'),
    tariff_id   INTEGER NOT NULL REFERENCES tariffs(id),
    label       VARCHAR NOT NULL,             -- 尖/峰/平/谷...
    start_min   INTEGER NOT NULL,             -- 自零点起的分钟，含
    end_min     INTEGER NOT NULL,             -- 自零点起的分钟，不含；1440=24:00
    price_yuan  DECIMAL(12, 6) NOT NULL,
    CHECK (start_min >= 0 AND end_min <= 1440 AND start_min < end_min)
);

CREATE TABLE IF NOT EXISTS holidays (
    date        DATE PRIMARY KEY,
    name        VARCHAR NOT NULL DEFAULT '',
    kind        VARCHAR NOT NULL DEFAULT 'holiday' -- holiday | workday（调休补班）
);
"""


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DB_PATH))
        _conn.execute(SCHEMA)
    return _conn


@contextmanager
def tx():
    """串行化所有写操作与需要一致性视图的读操作。"""
    with _lock:
        conn = get_conn()
        yield conn
