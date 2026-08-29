## 1. Estrutura inicial

- [x] 1.1 Criar `pyproject.toml` com `requires-python ">=3.10"`, FastAPI, uvicorn, driver Postgres, ruff e pytest; layout `src/`
- [x] 1.2 Criar `src/pool_selector/{__init__,app,scoring,catalog,db}.py` vazios e `tests/`
- [x] 1.3 Criar `Makefile` (`lint`, `test`, `dev`, `down`) e `.gitignore`
- [x] 1.4 Criar `Dockerfile` da API (Python 3.12, uvicorn na 5050)

## 2. Catálogo, parser e score

- [x] 2.1 Escrever `data/catalog.json` (`instance_type` → category, vcpu, memory_gib) e `catalog.py` com os filtros combináveis
- [x] 2.2 Escrever `data/events.jsonl` de seed com SUCCESS, SPOT_INSTANCE_TERMINATION, TIMED_OUT e SPARK_EXECUTION_ERROR
- [x] 2.3 Implementar parse de `pool_id` (`pool-r6.xlarge-us-east-1c` → tipo `r6.xlarge`, AZ `us-east-1c`) e rejeição de malformado
- [x] 2.4 Implementar `finished_at` naive → UTC; descarte de JSON inválido, reason desconhecido e `pool_id` fora do padrão sem abortar a carga
- [x] 2.5 Implementar `scoring.py`: S/F, SPARK_EXECUTION_ERROR fora, TIMED_OUT em F, Laplace `(S+1)/(S+F+2)`, quase-empate (margem 0,05) e sorteio uniforme
- [x] 2.6 Testes unitários: parse de `pool_id`, UTC, SPARK não altera score, TIMED_OUT é falha, Laplace 1 sucesso não vence 950/1000, cada filtro, quase-empate vs vencedor disparado

## 3. Postgres e seed

- [x] 3.1 Implementar `db.py`: criar tabela `job_events` na subida (sem Alembic); carregar `data/events.jsonl` só se a tabela estiver vazia; persistir SPARK_EXECUTION_ERROR
- [x] 3.2 Escrever `compose.yaml` com `postgres` e `api` (porta 5050, sem Redis/MinIO/worker)

## 4. API HTTP

- [x] 4.1 Expor `GET /get-pool`, `/get-pools` e `/getpools` com o mesmo handler; 200 = `{"pool_id": "..."}` apenas
- [x] 4.2 Validar query params (422); filtro sem candidato (400); tabela vazia (503)
- [x] 4.3 Emitir log rico (score, S, F, `argmax_pool_id`, `near_tie`, filtros, runner-up) sem colocar isso no corpo HTTP
- [x] 4.4 Testes dos três aliases 200 e dos códigos 400/422/503

## 5. Dev, docs e CI

- [x] 5.1 `make dev` sobe o compose, espera o Postgres, aplica schema+seed e deixa `curl http://localhost:5050/get-pools` devolver `pool_id`
- [x] 5.2 Escrever `README.md` (comando único, curl, premissas, como testar, CD em um parágrafo)
- [x] 5.3 Escrever `docs/adr/001-fastapi.md`, `docs/adr/002-postgres.md`, `docs/adr/003-score.md` e `docs/api.md`
- [x] 5.4 Escrever `.github/workflows/ci.yml` com ruff + pytest (sem matriz, Trivy, k6, mutation, coverage-gate)
- [x] 5.5 Publicar o repositório no GitHub se ainda não houver remote (R7)

## 6. Seed 10k / 24 h e GET sem cache

- [x] 6.1 Reescrever `tools/generate_events.py` para 10_000 eventos numa janela de 24 h; enviesar `r6.xlarge` em `us-east-1a` (líder) e `us-east-1b` (quase-empate); versionar o JSONL
- [x] 6.2 Remover cache de score na subida: GET lê `job_events`, agrega e aplica quase-empate por request
- [x] 6.3 Seed via `parse_jsonl` + `insert_events` (sem COPY de 1M); Dockerfile copia `events.jsonl`
- [x] 6.4 Atualizar docs de produto e a change `mvp-pool-selector`; não alterar `spot-pool-selection-api`
- [x] 6.5 `make setup`: checagens (Python 3.10+, Docker, curl, make), venv + extras de dev, seed se faltar, `docker compose build`
- [x] 6.6 Escrever `docs/cenarios-de-teste.md` (unitário default, filtros, 200 RPS, logs)
