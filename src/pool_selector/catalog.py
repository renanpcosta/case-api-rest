from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

VALID_CATEGORIES = frozenset({"memory", "compute", "general", "storage"})
POOL_PREFIX = "pool-"


@dataclass(frozen=True)
class InstanceSpec:
    category: str
    vcpu: int
    memory_gib: int


@dataclass(frozen=True)
class Filters:
    category: str | None = None
    instance_types: tuple[str, ...] | None = None
    min_vcpu: int | None = None
    min_memory: int | None = None
    az: tuple[str, ...] | None = None


def data_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data"


def parse_pool_id(pool_id: str) -> tuple[str, str] | None:
    if not isinstance(pool_id, str) or not pool_id.startswith(POOL_PREFIX):
        return None
    rest = pool_id[len(POOL_PREFIX) :]
    if "-" not in rest:
        return None
    instance_type, az = rest.split("-", 1)
    if not instance_type or not az:
        return None
    return instance_type, az


def load_catalog(path: Path | None = None) -> dict[str, InstanceSpec]:
    catalog_path = path or data_dir() / "catalog.json"
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog: dict[str, InstanceSpec] = {}
    for instance_type, attrs in raw.items():
        category = attrs["category"]
        if category not in VALID_CATEGORIES:
            raise ValueError(f"invalid category for {instance_type}: {category}")
        catalog[instance_type] = InstanceSpec(
            category=category,
            vcpu=int(attrs["vcpu"]),
            memory_gib=int(attrs["memory_gib"]),
        )
    return catalog


def pool_matches(
    pool_id: str,
    catalog: dict[str, InstanceSpec],
    filters: Filters,
) -> bool:
    parsed = parse_pool_id(pool_id)
    if parsed is None:
        return False
    instance_type, az = parsed
    spec = catalog.get(instance_type)
    if spec is None:
        return False
    if filters.category is not None and spec.category != filters.category:
        return False
    if filters.instance_types is not None and instance_type not in filters.instance_types:
        return False
    if filters.min_vcpu is not None and spec.vcpu < filters.min_vcpu:
        return False
    if filters.min_memory is not None and spec.memory_gib < filters.min_memory:
        return False
    if filters.az is not None and az not in filters.az:
        return False
    return True
