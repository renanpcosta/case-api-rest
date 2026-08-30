#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="${VENV:-.venv}"

fail() {
	echo "$1" >&2
	exit 1
}

command -v curl >/dev/null || fail "Instale curl (o make dev usa curl no healthcheck)."
command -v docker >/dev/null || fail "Instale Docker Desktop: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Abra o Docker Desktop e espere ficar verde (docker info)."
docker compose version >/dev/null 2>&1 \
	|| fail "Instale Compose v2: https://docs.docker.com/compose/install/ (comando: docker compose)"

deps_ok() {
	[[ -x "$VENV/bin/python" ]] || return 1
	[[ -f data/events.jsonl ]] || return 1
	"$VENV/bin/python" - <<'PY'
from importlib.metadata import PackageNotFoundError, version

need = (
    ("fastapi", (0, 115)),
    ("uvicorn", (0, 32)),
    ("psycopg", (3, 2)),
    ("httpx2", (2, 0)),
    ("pytest", (8,)),
    ("ruff", (0, 8)),
)


def ver_tuple(name: str) -> tuple[int, ...]:
    nums: list[int] = []
    for part in version(name).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits or 0))
    return tuple(nums)


try:
    for name, minimum in need:
        have = ver_tuple(name) + (0,) * len(minimum)
        if have[: len(minimum)] < minimum:
            raise SystemExit(1)
except PackageNotFoundError:
    raise SystemExit(1)
PY
}

if deps_ok; then
	echo "==> dependências ok, pulando setup"
else
	echo "==> dependências ausentes ou abaixo do pyproject, rodando setup"
	bash "$ROOT/scripts/setup.sh" --from-ensure
fi

# shellcheck source=scripts/k6.sh
source "$ROOT/scripts/k6.sh"
install_k6_if_needed
