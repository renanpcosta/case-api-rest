import random
from datetime import timedelta

from pool_selector.catalog import data_dir
from pool_selector.db import parse_jsonl
from pool_selector.scoring import NEAR_TIE_MARGIN, aggregate, near_tie_candidates, select_pool

WINNER = "pool-r6.xlarge-us-east-1a"
NEAR = "pool-r6.xlarge-us-east-1b"


def test_seed_has_10000_events_within_24h():
    events = parse_jsonl(data_dir() / "events.jsonl")
    assert len(events) == 10_000
    span = max(event.finished_at for event in events) - min(event.finished_at for event in events)
    assert span <= timedelta(hours=24)


def test_seed_near_tie_includes_runner_up():
    events = parse_jsonl(data_dir() / "events.jsonl")
    scores = aggregate(events)
    ranked_ids = [item.pool_id for item in near_tie_candidates(scores.values())]
    assert ranked_ids[0] == WINNER
    assert NEAR in ranked_ids
    assert len(ranked_ids) >= 2
    gap = scores[WINNER].score - scores[NEAR].score
    assert 0 < gap <= NEAR_TIE_MARGIN


def test_seed_lottery_returns_both_near_tie_pools():
    events = parse_jsonl(data_dir() / "events.jsonl")
    scores = aggregate(events).values()
    seen: set[str] = set()
    for i in range(40):
        chosen = select_pool(scores, rng=random.Random(i))
        assert chosen is not None
        seen.add(chosen.pool_id)
    assert WINNER in seen
    assert NEAR in seen
