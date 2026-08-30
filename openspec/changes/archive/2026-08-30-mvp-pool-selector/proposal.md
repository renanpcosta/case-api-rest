## Por quê

Jobs Apache Spark em pools EC2 spot falham quando a AWS retoma capacidade. Este case pede um GET que devolva o `pool_id` com maior chance de o job não falhar por indisponibilidade spot, respeitando filtros de tipo de instância, e um único comando que suba tudo em `http://localhost:5050`.

## O que muda

- **GET de seleção**: `/get-pool`, `/get-pools` e `/getpools` devolvem `{"pool_id": "..."}`. Filtros opcionais e combináveis: `category`, `instance_types`, `min_vcpu`, `min_memory`, `az`. Payload rico (score, evidência, política) só no log.
- **Parser do JSONL do enunciado**: um evento por linha; `finished_at` naive vira UTC; `pool_id` no formato `pool-<instance-type>-<az>` (tipo com ponto, AZ com hífen); linha malformada / `reason` desconhecido / `pool_id` fora do padrão é descartada sem derrubar a carga.
- **Score Laplace** sobre todos os eventos do seed (10_000 linhas numa janela de 24 h; sem recorte no GET, sem decaimento): `S` = SUCCESS; `F` = SPOT_INSTANCE_TERMINATION + TIMED_OUT; SPARK_EXECUTION_ERROR persistido e ignorado no score; `score = (S+1)/(S+F+2)`. A agregação S/F corre **em cada GET** no SQL (`GROUP BY pool_id`).
- **Quase-empate (efeito manada):** entre os que passam no filtro, entram no sorteio os pools com `score >= melhor - 0,05`. Um candidato → esse pool. Dois ou mais → escolha uniforme. Sem softmax. No seed, `r6.xlarge` `us-east-1a` lidera e `us-east-1b` fica na margem (GET sem filtro espalha).
- **Stack do MVP**: FastAPI + uvicorn + Postgres. JSONL no repo substitui S3 no dev. Schema criado na subida. Sem Redis, MinIO, worker, SQS, Alembic, hexagonal.
- **Um comando**: `make dev` instala o venv se as libs não atenderem o `pyproject.toml`, sobe compose (api + postgres), espera o Postgres, carrega o seed se a tabela estiver vazia, responde em `http://localhost:5050/get-pools`.
- **Docs e qualidade**: README, 3 ADRs (FastAPI, Postgres, score), `docs/api.md` (pares request/response), `docs/cenarios-de-teste.md` (pytest, filtros, k6), testes unitários, CI com ruff + pytest. CD só descrito no README. Repo no GitHub.

Nenhuma mudança é breaking: o repositório é greenfield.

## Capacidades

### Capacidades novas

- `event-ingestion`: parse do JSONL do enunciado, normalização de timezone e `pool_id`, descarte de linhas inválidas, carga do seed versionado (`data/events.jsonl`, 10_000 eventos em 24 h) em Postgres na subida se a tabela estiver vazia.
- `instance-catalog`: catálogo estático `data/catalog.json` (`instance_type` → category, vcpu, memory_gib) e semântica dos filtros combináveis.
- `pool-scoring`: agregação S/F, Laplace, exclusão de SPARK_EXECUTION_ERROR do score, TIMED_OUT como falha, quase-empate (margem 0,05) com sorteio uniforme.
- `pool-api`: contrato HTTP dos três aliases, query params, 200/400/422/503, corpo 200 só com `pool_id`, log rico para debug de plataforma.
- `dev-environment`: `make dev`, compose api+postgres na porta 5050, schema na subida, README/ADRs/CI.

### Capacidades modificadas

- Nenhuma. Não há specs em `openspec/specs/`.

## Impacto

Greenfield. Arquivos previstos: `src/pool_selector/` (`app.py`, `scoring.py`, `catalog.py`, `db.py`), `data/events.jsonl` (10k, versionado), `tools/generate_events.py`, `data/catalog.json`, `tests/`, `docs/adr/001-fastapi.md`, `docs/adr/002-postgres.md`, `docs/adr/003-score.md`, `docs/api.md`, `docs/cenarios-de-teste.md`, `compose.yaml`, `Makefile`, `Dockerfile`, `pyproject.toml`, `.github/workflows/ci.yml`, `README.md`.

Fora deste change: Wilson, softmax, cooldown, Redis, MinIO, worker, k6, hexagonal, `.cursor/`, 12 ADRs, HPA, Alembic.
