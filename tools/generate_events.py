#!/usr/bin/env python3
"""Gera data/events.jsonl: 10_000 eventos numa janela de 24 h. Versionar o arquivo."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "events.jsonl"
DEFAULT_N = 10_000
WINDOW = timedelta(hours=24)

INSTANCE_TYPES = (
    "r6.xlarge",
    "r6.2xlarge",
    "c6.xlarge",
    "c6.2xlarge",
    "m6.xlarge",
    "i3.xlarge",
)
AZS = ("us-east-1a", "us-east-1b", "us-east-1c")
WINNER_TYPE = "r6.xlarge"
WINNER_AZ = "us-east-1a"
NEAR_AZ = "us-east-1b"

# 1a lidera; 1b fica a ≤ 0,05 (quase-empate no GET sem filtro). Demais pools longe.
OTHER_OUTCOMES = (
    ("SUCCESS", None, 70),
    ("FAILED", "SPOT_INSTANCE_TERMINATION", 12),
    ("FAILED", "TIMED_OUT", 8),
    ("FAILED", "SPARK_EXECUTION_ERROR", 10),
)
WINNER_OUTCOMES = (
    ("SUCCESS", None, 90),
    ("FAILED", "SPOT_INSTANCE_TERMINATION", 3),
    ("FAILED", "TIMED_OUT", 2),
    ("FAILED", "SPARK_EXECUTION_ERROR", 5),
)
NEAR_OUTCOMES = (
    ("SUCCESS", None, 87),
    ("FAILED", "SPOT_INSTANCE_TERMINATION", 6),
    ("FAILED", "TIMED_OUT", 3),
    ("FAILED", "SPARK_EXECUTION_ERROR", 4),
)


OutcomeRow = tuple[str, str | None]


def _outcome_table(weights: tuple[tuple[str, str | None, int], ...]) -> list[OutcomeRow]:
    rows: list[OutcomeRow] = []
    for status, reason, weight in weights:
        rows.extend([(status, reason)] * weight)
    return rows


def generate(path: Path, n: int, seed: int) -> None:
    rng = random.Random(seed)
    other_outcomes = _outcome_table(OTHER_OUTCOMES)
    winner_outcomes = _outcome_table(WINNER_OUTCOMES)
    near_outcomes = _outcome_table(NEAR_OUTCOMES)
    start = datetime(2024, 8, 7, 0, 0, 0)
    step = WINDOW / n
    path.parent.mkdir(parents=True, exist_ok=True)
    chunk: list[str] = []
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for i in range(n):
            instance_type = INSTANCE_TYPES[rng.randrange(len(INSTANCE_TYPES))]
            az = AZS[rng.randrange(len(AZS))]
            if instance_type == WINNER_TYPE and az == WINNER_AZ:
                status, reason = winner_outcomes[rng.randrange(len(winner_outcomes))]
            elif instance_type == WINNER_TYPE and az == NEAR_AZ:
                status, reason = near_outcomes[rng.randrange(len(near_outcomes))]
            else:
                status, reason = other_outcomes[rng.randrange(len(other_outcomes))]
            finished = start + step * i
            ts = finished.strftime("%Y-%m-%dT%H:%M:%S.%f")
            pool_id = f"pool-{instance_type}-{az}"
            if reason is None:
                line = (
                    f'{{"finished_at": "{ts}", "job_id": "job-{i}", '
                    f'"pool_id": "{pool_id}", "status": "{status}"}}\n'
                )
            else:
                line = (
                    f'{{"finished_at": "{ts}", "job_id": "job-{i}", '
                    f'"pool_id": "{pool_id}", "status": "{status}", '
                    f'"reason": "{reason}"}}\n'
                )
            chunk.append(line)
            if len(chunk) >= 5_000:
                handle.writelines(chunk)
                chunk.clear()
        if chunk:
            handle.writelines(chunk)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=DEFAULT_N)
    parser.add_argument("-o", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(args.o, args.n, args.seed)
    size_kib = args.o.stat().st_size / 1024
    print(f"wrote {args.n} lines to {args.o} ({size_kib:.1f} KiB)")


if __name__ == "__main__":
    main()
