import logging
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from pool_selector.app import create_app
from pool_selector.catalog import data_dir
from pool_selector.db import parse_jsonl
from pool_selector.scoring import SUCCESS, JobEvent

SEED_EVENTS = parse_jsonl(data_dir() / "events.sample.jsonl")


def _client(events=SEED_EVENTS) -> TestClient:
    return TestClient(create_app(use_db=False, event_loader=lambda ev=events: ev))


def test_three_aliases_return_pool_id_only():
    client = _client()
    for path in ("/get-pool", "/get-pools", "/getpools"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert list(body.keys()) == ["pool_id"]
        assert body["pool_id"] == "pool-r6.xlarge-us-east-1a"


def test_invalid_param_is_422():
    client = _client()
    assert client.get("/get-pool", params={"category": "gpu"}).status_code == 422
    assert client.get("/get-pool", params={"min_vcpu": -1}).status_code == 422
    assert client.get("/get-pool", params={"min_memory": "abc"}).status_code == 422


def test_filter_without_candidates_is_400():
    client = _client()
    response = client.get("/get-pool", params={"az": "us-west-2a"})
    assert response.status_code == 400


def test_empty_database_is_503():
    client = _client(events=[])
    assert client.get("/get-pool").status_code == 503


def test_rich_log_is_not_in_http_body(caplog):
    client = _client()
    with caplog.at_level(logging.INFO, logger="pool_selector"):
        response = client.get("/get-pool")
    assert response.status_code == 200
    assert response.json() == {"pool_id": "pool-r6.xlarge-us-east-1a"}
    assert "score" not in response.json()
    assert "pool_selected" in caplog.text
    assert '"s":' in caplog.text
    assert '"f":' in caplog.text
    assert "argmax_pool_id" in caplog.text
    assert "near_tie" in caplog.text


def test_near_tie_spreads_http_choices():
    def event(pool_id: str) -> JobEvent:
        return JobEvent(
            finished_at=datetime(2024, 8, 7, tzinfo=timezone.utc),
            job_id="j",
            pool_id=pool_id,
            status=SUCCESS,
            reason=None,
        )

    events = [
        event("pool-r6.xlarge-us-east-1a"),
        event("pool-r6.xlarge-us-east-1c"),
    ]
    client = _client(events=events)
    seen = {client.get("/get-pool").json()["pool_id"] for _ in range(40)}
    assert seen == {"pool-r6.xlarge-us-east-1a", "pool-r6.xlarge-us-east-1c"}
