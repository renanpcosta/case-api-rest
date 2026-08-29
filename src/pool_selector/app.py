from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from enum import Enum
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from pool_selector.catalog import Filters, InstanceSpec, load_catalog, pool_matches
from pool_selector.db import connect, fetch_events, startup
from pool_selector.scoring import (
    JobEvent,
    PoolScore,
    aggregate,
    near_tie_candidates,
    rank_pools,
    select_pool,
)

logger = logging.getLogger("pool_selector")


class Category(str, Enum):
    memory = "memory"
    compute = "compute"
    general = "general"
    storage = "storage"


class PoolResponse(BaseModel):
    pool_id: str


def _csv(value: str | None) -> tuple[str, ...] | None:
    if value is None or value.strip() == "":
        return None
    items = tuple(part.strip() for part in value.split(",") if part.strip())
    return items or None


def choose_from_scores(
    score_map: dict[str, PoolScore],
    catalog: dict[str, InstanceSpec],
    filters: Filters,
) -> tuple[PoolScore, PoolScore | None, list[PoolScore], PoolScore]:
    scores = [
        score for pool_id, score in score_map.items() if pool_matches(pool_id, catalog, filters)
    ]
    ranked = rank_pools(scores)
    winner = select_pool(ranked)
    if winner is None:
        raise HTTPException(status_code=400, detail="no candidates match filters")
    runner_up = ranked[1] if len(ranked) > 1 else None
    return winner, runner_up, near_tie_candidates(ranked), ranked[0]


def _events_from_db() -> list[JobEvent]:
    with connect() as conn:
        return fetch_events(conn)


def create_app(
    *,
    use_db: bool = True,
    event_loader: Callable[[], list[JobEvent]] | None = None,
) -> FastAPI:
    catalog = load_catalog()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        if use_db:
            startup()
        yield

    app = FastAPI(title="pool-selector", lifespan=lifespan)

    def handle_get(
        score_map: dict[str, PoolScore],
        category: Category | None,
        instance_types: str | None,
        min_vcpu: int | None,
        min_memory: int | None,
        az: str | None,
    ) -> PoolResponse:
        if not score_map:
            raise HTTPException(status_code=503, detail="no events in database")
        filters = Filters(
            category=category.value if category else None,
            instance_types=_csv(instance_types),
            min_vcpu=min_vcpu,
            min_memory=min_memory,
            az=_csv(az),
        )
        winner, runner_up, near_tie, argmax = choose_from_scores(score_map, catalog, filters)
        logger.info(
            json.dumps(
                {
                    "event": "pool_selected",
                    "pool_id": winner.pool_id,
                    "score": winner.score,
                    "s": winner.s,
                    "f": winner.f,
                    "argmax_pool_id": argmax.pool_id,
                    "near_tie": [item.pool_id for item in near_tie],
                    "filters": {
                        "category": filters.category,
                        "instance_types": filters.instance_types,
                        "min_vcpu": filters.min_vcpu,
                        "min_memory": filters.min_memory,
                        "az": filters.az,
                    },
                    "runner_up": None
                    if runner_up is None
                    else {
                        "pool_id": runner_up.pool_id,
                        "score": runner_up.score,
                        "s": runner_up.s,
                        "f": runner_up.f,
                    },
                },
                default=str,
            )
        )
        return PoolResponse(pool_id=winner.pool_id)

    @app.get("/get-pool", response_model=PoolResponse)
    @app.get("/get-pools", response_model=PoolResponse)
    @app.get("/getpools", response_model=PoolResponse)
    def get_pool(
        category: Category | None = None,
        instance_types: str | None = None,
        min_vcpu: Annotated[int | None, Query(ge=0)] = None,
        min_memory: Annotated[int | None, Query(ge=0)] = None,
        az: str | None = None,
    ) -> PoolResponse:
        loader = event_loader if event_loader is not None else _events_from_db
        score_map = aggregate(loader())
        return handle_get(score_map, category, instance_types, min_vcpu, min_memory, az)

    return app


app = create_app()
