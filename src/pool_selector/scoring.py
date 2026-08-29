from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

SUCCESS = "SUCCESS"
FAILED = "FAILED"
SPOT = "SPOT_INSTANCE_TERMINATION"
TIMED_OUT = "TIMED_OUT"
SPARK = "SPARK_EXECUTION_ERROR"
KNOWN_REASONS = frozenset({SPOT, TIMED_OUT, SPARK})
NEAR_TIE_MARGIN = 0.05


@dataclass(frozen=True)
class JobEvent:
    finished_at: datetime
    job_id: str
    pool_id: str
    status: str
    reason: str | None


@dataclass(frozen=True)
class PoolScore:
    pool_id: str
    s: int
    f: int
    score: float


def laplace_score(s: int, f: int) -> float:
    return (s + 1) / (s + f + 2)


def aggregate(events: Iterable[JobEvent]) -> dict[str, PoolScore]:
    counts: dict[str, list[int]] = {}
    for event in events:
        bucket = counts.setdefault(event.pool_id, [0, 0])
        if event.status == SUCCESS:
            bucket[0] += 1
            continue
        if event.status == FAILED and event.reason in {SPOT, TIMED_OUT}:
            bucket[1] += 1
    return {
        pool_id: PoolScore(
            pool_id=pool_id,
            s=s,
            f=f,
            score=laplace_score(s, f),
        )
        for pool_id, (s, f) in counts.items()
    }


def rank_pools(scores: Iterable[PoolScore]) -> list[PoolScore]:
    return sorted(scores, key=lambda item: (-item.score, item.pool_id))


def select_best(scores: Iterable[PoolScore]) -> PoolScore | None:
    ranked = rank_pools(scores)
    if not ranked:
        return None
    return ranked[0]


def near_tie_candidates(
    scores: Iterable[PoolScore],
    margin: float = NEAR_TIE_MARGIN,
) -> list[PoolScore]:
    ranked = rank_pools(scores)
    if not ranked:
        return []
    threshold = ranked[0].score - margin
    return [item for item in ranked if item.score >= threshold]


def select_pool(
    scores: Iterable[PoolScore],
    *,
    rng: random.Random | None = None,
    margin: float = NEAR_TIE_MARGIN,
) -> PoolScore | None:
    candidates = near_tie_candidates(scores, margin=margin)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if rng is None:
        return random.choice(candidates)
    return rng.choice(candidates)
