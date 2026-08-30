.PHONY: setup lint test dev down seed

VENV ?= .venv

setup:
	bash scripts/setup.sh

lint:
	@test -x $(VENV)/bin/ruff || { echo "Falta o venv. Rode: make setup"; exit 1; }
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/ruff format --check src tests

test:
	@test -x $(VENV)/bin/pytest || { echo "Falta o venv. Rode: make setup"; exit 1; }
	$(VENV)/bin/pytest -q

dev:
	bash scripts/ensure.sh
	docker compose up --build -d
	@i=0; \
	while [ $$i -lt 60 ]; do \
		if curl -sf http://localhost:5050/get-pools >/dev/null; then \
			curl -s http://localhost:5050/get-pools; echo; \
			exit 0; \
		fi; \
		i=$$((i + 1)); \
		sleep 1; \
	done; \
	echo "API did not become ready on http://localhost:5050"; \
	docker compose logs api; \
	exit 1

down:
	docker compose down

seed:
	python3 tools/generate_events.py
