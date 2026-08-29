#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="${VENV:-.venv}"

fail() {
	echo "$1" >&2
	exit 1
}

echo "==> checando Python >= 3.10"
command -v python3 >/dev/null || fail "Instale Python 3.10+: https://www.python.org/downloads/"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
	|| fail "Python >= 3.10 necessário. Atual: $(python3 --version)"

echo "==> checando make, curl, Docker"
command -v make >/dev/null || fail "Instale make. macOS: xcode-select --install"
command -v curl >/dev/null || fail "Instale curl (o make dev usa curl no healthcheck)."
command -v docker >/dev/null || fail "Instale Docker Desktop: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Abra o Docker Desktop e espere ficar verde (docker info)."
docker compose version >/dev/null 2>&1 \
	|| fail "Instale Compose v2: https://docs.docker.com/compose/install/ (comando: docker compose)"

echo "==> venv + dependências (FastAPI, pytest, ruff)"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -U pip setuptools wheel
"$VENV/bin/pip" install -e ".[dev]"

if [[ ! -f data/events.jsonl ]]; then
	echo "==> gerando data/events.jsonl (10k / 24 h)"
	python3 tools/generate_events.py
fi

echo "==> imagens Docker (api + postgres:16)"
docker compose build

echo
echo "Pronto. Próximo:"
echo "  make dev     # API em http://localhost:5050/get-pools"
echo "  make lint && make test"
