from datetime import datetime, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from pool_selector.app import create_app
from pool_selector.db import (
    connect,
    database_url,
    fetch_pool_scores,
    init_schema,
    insert_events,
)
from pool_selector.scoring import FAILED, SPARK, SPOT, SUCCESS, TIMED_OUT, JobEvent, aggregate

TEST_DB = "pool_test"


def _event(pool_id: str, status: str, reason: str | None = None) -> JobEvent:
    return JobEvent(
        finished_at=datetime(2024, 8, 7, tzinfo=timezone.utc),
        job_id="j",
        pool_id=pool_id,
        status=status,
        reason=reason,
    )


def _test_db_url(base: str) -> str:
    prefix, sep, _name = base.rpartition("/")
    if not sep:
        return f"{base}/{TEST_DB}"
    return f"{prefix}/{TEST_DB}"


def _ensure_test_database() -> str | None:
    base = database_url()
    try:
        conn = psycopg.connect(base, connect_timeout=2)
    except Exception:  # noqa: BLE001 — skip when postgres is down
        return None
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
            if cur.fetchone() is None:
                cur.execute(f"CREATE DATABASE {TEST_DB}")
    except Exception:  # noqa: BLE001
        conn.close()
        return None
    conn.close()
    return _test_db_url(base)


@pytest.fixture
def postgres(monkeypatch):
    url = _ensure_test_database()
    if url is None:
        pytest.skip("Postgres não está no ar. CI sobe o serviço; localmente: make dev.")
    monkeypatch.setenv("DATABASE_URL", url)
    with connect(retries=2) as conn:
        init_schema(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE job_events")
        conn.commit()
    return url


def test_group_by_matches_in_memory_aggregate(postgres):
    events = [
        _event("pool-r6.xlarge-us-east-1a", SUCCESS),
        _event("pool-r6.xlarge-us-east-1a", SUCCESS),
        _event("pool-r6.xlarge-us-east-1a", FAILED, SPOT),
        _event("pool-r6.xlarge-us-east-1a", FAILED, SPARK),
        _event("pool-r6.xlarge-us-east-1c", FAILED, TIMED_OUT),
    ]
    with connect(retries=2) as conn:
        insert_events(conn, events)
        sql_scores = fetch_pool_scores(conn)
    assert sql_scores == aggregate(events)
    assert sql_scores["pool-r6.xlarge-us-east-1a"].s == 2
    assert sql_scores["pool-r6.xlarge-us-east-1a"].f == 1


def test_get_pool_uses_postgres_group_by(postgres):
    events = [_event("pool-r6.xlarge-us-east-1a", SUCCESS) for _ in range(10)]
    events.append(_event("pool-c6.xlarge-us-east-1a", SUCCESS))
    with connect(retries=2) as conn:
        insert_events(conn, events)
    with TestClient(create_app(use_db=True)) as client:
        response = client.get("/get-pool")
    assert response.status_code == 200
    assert response.json() == {"pool_id": "pool-r6.xlarge-us-east-1a"}


def test_get_pool_503_when_job_events_empty(postgres):
    with connect(retries=2) as conn:
        insert_events(conn, [_event("pool-r6.xlarge-us-east-1a", SUCCESS)])
    with TestClient(create_app(use_db=True)) as client:
        with connect(retries=2) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE job_events")
            conn.commit()
        response = client.get("/get-pool")
    assert response.status_code == 503
    assert response.json() == {"detail": "no events in database"}
