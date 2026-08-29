from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from pool_selector.catalog import data_dir, parse_pool_id
from pool_selector.scoring import FAILED, KNOWN_REASONS, SUCCESS, JobEvent

logger = logging.getLogger("pool_selector")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS job_events (
    id BIGSERIAL PRIMARY KEY,
    finished_at TIMESTAMPTZ NOT NULL,
    job_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT
);
"""


def parse_finished_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_event_line(line: str) -> JobEvent | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    finished_at_raw = payload.get("finished_at")
    job_id = payload.get("job_id")
    pool_id = payload.get("pool_id")
    status = payload.get("status")
    if not isinstance(finished_at_raw, str) or not isinstance(job_id, str):
        return None
    if not isinstance(pool_id, str) or not isinstance(status, str):
        return None
    if parse_pool_id(pool_id) is None:
        return None
    try:
        finished_at = parse_finished_at(finished_at_raw)
    except ValueError:
        return None
    if status == SUCCESS:
        return JobEvent(
            finished_at=finished_at,
            job_id=job_id,
            pool_id=pool_id,
            status=SUCCESS,
            reason=None,
        )
    if status != FAILED:
        return None
    reason = payload.get("reason")
    if reason not in KNOWN_REASONS:
        return None
    return JobEvent(
        finished_at=finished_at,
        job_id=job_id,
        pool_id=pool_id,
        status=FAILED,
        reason=reason,
    )


def parse_jsonl(path: Path) -> list[JobEvent]:
    events: list[JobEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            event = parse_event_line(stripped)
            if event is None:
                logger.warning("discarding malformed event line")
                continue
            events.append(event)
    return events


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://pool:pool@localhost:5432/pool")


def connect(retries: int = 30) -> psycopg.Connection:
    url = database_url()
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return psycopg.connect(url)
        except Exception as exc:  # noqa: BLE001 — retry loop on startup
            last_error = exc
            time.sleep(1)
    raise RuntimeError("could not connect to postgres") from last_error


def init_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def event_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM job_events")
        row = cur.fetchone()
    return int(row[0]) if row else 0


def insert_events(conn: psycopg.Connection, events: list[JobEvent]) -> None:
    if not events:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO job_events (finished_at, job_id, pool_id, status, reason)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (event.finished_at, event.job_id, event.pool_id, event.status, event.reason)
                for event in events
            ],
        )
    conn.commit()


def default_seed_path() -> Path:
    jsonl = data_dir() / "events.jsonl"
    if jsonl.exists():
        return jsonl
    return data_dir() / "events.sample.jsonl"


def seed_if_empty(conn: psycopg.Connection, seed_path: Path | None = None) -> None:
    if event_count(conn) > 0:
        return
    path = seed_path or default_seed_path()
    events = parse_jsonl(path)
    insert_events(conn, events)
    logger.info("seeded job_events with %s valid rows", len(events))


def fetch_events(conn: psycopg.Connection) -> list[JobEvent]:
    with conn.cursor() as cur:
        cur.execute("SELECT finished_at, job_id, pool_id, status, reason FROM job_events")
        rows = cur.fetchall()
    events: list[JobEvent] = []
    for finished_at, job_id, pool_id, status, reason in rows:
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)
        events.append(
            JobEvent(
                finished_at=finished_at,
                job_id=job_id,
                pool_id=pool_id,
                status=status,
                reason=reason,
            )
        )
    return events


def startup(seed_path: Path | None = None) -> None:
    with connect() as conn:
        init_schema(conn)
        seed_if_empty(conn, seed_path=seed_path)
