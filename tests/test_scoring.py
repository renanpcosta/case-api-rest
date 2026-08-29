import random
from datetime import datetime, timezone

from pool_selector.scoring import (
    SPARK,
    SPOT,
    SUCCESS,
    TIMED_OUT,
    JobEvent,
    aggregate,
    laplace_score,
    near_tie_candidates,
    rank_pools,
    scores_from_counts,
    select_pool,
)


def _event(pool_id: str, status: str, reason: str | None = None) -> JobEvent:
    return JobEvent(
        finished_at=datetime(2024, 8, 7, tzinfo=timezone.utc),
        job_id="j",
        pool_id=pool_id,
        status=status,
        reason=reason,
    )


def test_success_increments_s():
    scores = aggregate([_event("pool-a", SUCCESS)])
    assert scores["pool-a"].s == 1
    assert scores["pool-a"].f == 0


def test_spot_and_timeout_increment_f():
    scores = aggregate(
        [
            _event("pool-a", "FAILED", SPOT),
            _event("pool-a", "FAILED", TIMED_OUT),
        ]
    )
    assert scores["pool-a"].s == 0
    assert scores["pool-a"].f == 2


def test_spark_execution_error_does_not_change_score():
    pool = "pool-r6.xlarge-us-east-1a"
    base = [_event(pool, SUCCESS), _event(pool, "FAILED", SPOT)]
    with_spark = base + [_event(pool, "FAILED", SPARK), _event(pool, "FAILED", SPARK)]
    assert aggregate(base)[pool].s == aggregate(with_spark)[pool].s
    assert aggregate(base)[pool].f == aggregate(with_spark)[pool].f
    assert aggregate(base)[pool].score == aggregate(with_spark)[pool].score


def test_timed_out_counts_as_failure():
    scores = aggregate([_event("pool-a", "FAILED", TIMED_OUT)])
    assert scores["pool-a"].f == 1
    assert scores["pool-a"].s == 0


def test_laplace_empty_is_half():
    assert laplace_score(0, 0) == 0.5


def test_one_success_does_not_beat_950_of_1000():
    pool_a = "pool-r6.xlarge-us-east-1a"
    pool_b = "pool-r6.xlarge-us-east-1c"
    events = [_event(pool_a, SUCCESS)]
    events.extend(_event(pool_b, SUCCESS) for _ in range(950))
    events.extend(_event(pool_b, "FAILED", SPOT) for _ in range(50))
    ranked = rank_pools(aggregate(events).values())
    assert ranked[0].pool_id == pool_b
    assert laplace_score(950, 50) > laplace_score(1, 0)


def test_tie_is_lexicographic():
    events = [
        _event("pool-r6.xlarge-us-east-1c", SUCCESS),
        _event("pool-r6.xlarge-us-east-1a", SUCCESS),
    ]
    ranked = rank_pools(aggregate(events).values())
    assert ranked[0].pool_id == "pool-r6.xlarge-us-east-1a"


def test_clear_winner_is_the_only_near_tie_candidate():
    pool_a = "pool-r6.xlarge-us-east-1a"
    pool_b = "pool-m6.xlarge-us-east-1b"
    events = [_event(pool_a, SUCCESS) for _ in range(10)]
    events.extend(_event(pool_b, SUCCESS) for _ in range(2))
    candidates = near_tie_candidates(aggregate(events).values())
    assert [item.pool_id for item in candidates] == [pool_a]
    chosen = select_pool(aggregate(events).values())
    assert chosen is not None
    assert chosen.pool_id == pool_a


def test_near_tie_includes_scores_within_margin():
    pool_a = "pool-r6.xlarge-us-east-1a"
    pool_b = "pool-r6.xlarge-us-east-1c"
    events = [_event(pool_a, SUCCESS) for _ in range(3)]
    events.extend(_event(pool_b, SUCCESS) for _ in range(2))
    candidates = {item.pool_id for item in near_tie_candidates(aggregate(events).values())}
    assert candidates == {pool_a, pool_b}


def test_near_tie_picks_with_injected_rng():
    pool_a = "pool-r6.xlarge-us-east-1a"
    pool_b = "pool-r6.xlarge-us-east-1c"
    events = [_event(pool_a, SUCCESS), _event(pool_b, SUCCESS)]
    scores = aggregate(events).values()
    seen: set[str] = set()
    for i in range(40):
        chosen = select_pool(scores, rng=random.Random(i))
        assert chosen is not None
        seen.add(chosen.pool_id)
    assert seen == {pool_a, pool_b}


def test_scores_from_counts_matches_aggregate():
    events = [
        _event("pool-a", SUCCESS),
        _event("pool-a", SUCCESS),
        _event("pool-a", "FAILED", SPOT),
        _event("pool-a", "FAILED", SPARK),
        _event("pool-b", "FAILED", TIMED_OUT),
    ]
    from_events = aggregate(events)
    from_sql_shape = scores_from_counts(
        [
            ("pool-a", 2, 1),
            ("pool-b", 0, 1),
        ]
    )
    assert from_events == from_sql_shape
