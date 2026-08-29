from datetime import datetime, timezone

from pool_selector.catalog import parse_pool_id
from pool_selector.db import parse_event_line, parse_finished_at, parse_jsonl
from pool_selector.scoring import SPARK, SUCCESS


def test_parse_pool_id_type_with_dot_az_with_hyphen():
    assert parse_pool_id("pool-r6.xlarge-us-east-1c") == ("r6.xlarge", "us-east-1c")


def test_parse_pool_id_rejects_malformed():
    assert parse_pool_id("r6.xlarge-us-east-1c") is None
    assert parse_pool_id("pool-r6.xlarge") is None
    assert parse_pool_id("pool-") is None
    assert parse_pool_id("") is None


def test_finished_at_naive_becomes_utc():
    parsed = parse_finished_at("2024-08-07T00:04:52.767830")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)
    assert parsed == datetime(2024, 8, 7, 0, 4, 52, 767830, tzinfo=timezone.utc)


def test_parse_event_line_discards_invalid_json_unknown_reason_bad_pool():
    assert parse_event_line("not-json") is None
    assert (
        parse_event_line(
            '{"finished_at":"2024-08-07T00:00:00","job_id":"j","pool_id":"pool-r6.xlarge-us-east-1a","status":"FAILED","reason":"UNKNOWN"}'
        )
        is None
    )
    assert (
        parse_event_line(
            '{"finished_at":"2024-08-07T00:00:00","job_id":"j","pool_id":"r6.xlarge-us-east-1a","status":"SUCCESS"}'
        )
        is None
    )


def test_parse_jsonl_skips_bad_lines_and_keeps_spark(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"finished_at":"2024-08-07T00:00:00","job_id":"ok","pool_id":"pool-r6.xlarge-us-east-1a","status":"SUCCESS"}',
                "not-json",
                '{"finished_at":"2024-08-07T00:00:01","job_id":"spark","pool_id":"pool-r6.xlarge-us-east-1a","status":"FAILED","reason":"SPARK_EXECUTION_ERROR"}',
            ]
        ),
        encoding="utf-8",
    )
    events = parse_jsonl(path)
    assert len(events) == 2
    assert events[0].status == SUCCESS
    assert events[1].reason == SPARK
    assert events[0].finished_at.tzinfo is not None
