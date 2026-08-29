## Contexto

Repositório greenfield (README inicial). O case pede um GET que escolhe o pool spot com menor risco de indisponibilidade, filtros de tipo de instância, e `make dev` respondendo em `http://localhost:5050/get-pools`.

O dado de entrada é o JSONL do enunciado (um evento por linha). No MVP o arquivo versionado `data/events.jsonl` tem 10_000 eventos com `finished_at` numa janela de 24 h. É carregado no Postgres na subida se a tabela estiver vazia. O GET pede S/F por `pool_id` ao Postgres (`GROUP BY`) e aplica Laplace/quase-empate em processo.

Três superfícies distintas, não misturadas:

1. Evento JSONL = dado (não é body HTTP).
2. Request HTTP = GET com query params de filtro.
3. Response HTTP 200 = somente `{"pool_id": "..."}`. Payload rico só no log.

## Objetivos / Fora de escopo

**Objetivos:**

- GET `/get-pool` (aliases `/get-pools`, `/getpools`) devolve um `pool_id` que passa nos filtros e está no conjunto de quase-empate do melhor Laplace (margem 0,05).
- FastAPI + uvicorn + um Postgres. JSONL local no lugar de S3.
- Parser fiel ao enunciado: UTC em `finished_at` naive; `pool_id` com tipo contendo ponto e AZ contendo hífen; descarte de linha inválida sem derrubar a carga.
- Score sobre todos os eventos do seed. SPARK_EXECUTION_ERROR persistido e fora de S e F. TIMED_OUT conta como falha (peso 1). Quase-empate: sorteio uniforme se `score >= melhor - 0,05`; senão o melhor sozinho.
- Um comando: `make dev`. Aceite: `curl http://localhost:5050/get-pools` devolve JSON com `pool_id`.
- README, 3 ADRs, `docs/api.md`, `docs/cenarios-de-teste.md`, testes unitários, CI (ruff + pytest). CD só no README. Repo no GitHub.

**Fora de escopo:**

- Wilson, softmax, UCB, cooldown, inflight, meia-vida, janela de 4h, buckets.
- Redis, MinIO, worker, SQS, Alembic, hexagonal, ports/adapters, `.cursor/`.
- Payload HTTP explicável, `/metrics`, `/version`, readiness em escada, k6, Prometheus, HPA.
- families, exclude_az, job_id, candidates como filtros.

## Decisões

### 1. FastAPI + uvicorn (ADR 1)

Escolha: FastAPI + uvicorn. Python `>=3.10` (satisfaz R1 > 3.9).

Racional: OpenAPI/Swagger nativo cobre parte de R5; Pydantic valida os query params (422).

Alternativas: Flask (OpenAPI extra), Django (pesado para um GET).

### 2. Postgres apenas; JSONL no repo substitui S3 (ADR 2)

Escolha: um Postgres. Tabela `job_events`. Seed `data/events.jsonl` carregado na subida se a tabela estiver vazia. Schema criado na subida, sem Alembic.

Racional: R3 pede uma escolha documentada, não dois stores. Eventos precisam de persistência para o score. Ranking de N pools cabe em query + memória. Redis/MinIO/worker ficam fora.

Produção (só texto no ADR/README): réplicas stateless da API + um Postgres compartilhado. Escalabilidade documentada, não implementada com k6/HPA.

Alternativas: só arquivo (R4/estado compartilhado pior); Redis (cache prematuro).

### 3. Score Laplace em processo (ADR 3)

Por pool, com todos os eventos do seed, **agregado em cada GET** no SQL (`GROUP BY pool_id`):

- `S` = contagem de SUCCESS
- `F` = SPOT_INSTANCE_TERMINATION + TIMED_OUT (peso 1 cada)
- SPARK_EXECUTION_ERROR não entra em S nem em F (pode ser gravado)
- `score = (S + 1) / (S + F + 2)`
- entre os pools que passam no filtro: conjunto de quase-empate `score >= melhor - 0,05`
- um membro no conjunto → esse pool; dois ou mais → sorteio uniforme (`random.choice`)
- ranking lexicográfico (`-score`, `pool_id`) só ordena o conjunto e o log (`argmax_pool_id`); não decide sozinho o HTTP quando há quase-empate

Candidatos = `pool_id` distintos em `job_events` cujo `instance_type` existe no catálogo e passa nos filtros informados.

Por que SPARK_EXECUTION_ERROR fica fora: não mede o pool (falha da aplicação). Contar como F empurra o próximo job para outro pool à toa; contar como S infla saúde com execução que falhou. Contraexemplo: job com bug em us-east-1a não pode fazer a API parar de recomendar 1a.

Por que Laplace: 1/1 não vence 950/1000.

Por que em processo por GET: o seed tem 10_000 linhas. N pools é pequeno. O SQL devolve ~18 pares `(s, f)`; Laplace e quase-empate ficam em memória. Sem cache de score: um INSERT novo em `job_events` entra no GET seguinte. Sem Redis. k6 a 200 RPS no seed 10k atinge a taxa depois do `GROUP BY` (antes, scan de 10k na API: ~50/s, p95 ~5 s).

Por que margem 0,05 e não softmax: concentrar quando o score distingue; espalhar só quando não distingue. Sem temperatura para calibrar.

Por que não Redis: o sorteio é por request; não há contador compartilhado.

Alternativas recusadas: Wilson, softmax, cooldown, inflight.

### 4. Layout plano, um processo

```
src/pool_selector/     app.py, scoring.py, catalog.py, db.py
data/                  events.jsonl (10k), events.sample.jsonl, catalog.json
tools/                 generate_events.py
tests/
docs/adr/              001-fastapi.md, 002-postgres.md, 003-score.md
docs/api.md
docs/cenarios-de-teste.md
compose.yaml  Makefile  Dockerfile  pyproject.toml
.github/workflows/ci.yml
README.md
```

`app.py` = rotas; GET lê scores agregados e escolhe. `catalog.py` = catálogo + filtros. `scoring.py` = S/F + Laplace + quase-empate. `db.py` = schema, seed, `GROUP BY` de S/F. `tools/generate_events.py` = regenera o JSONL de 10k.

Compose: `api` + `postgres`. Porta 5050. Sem hexagonal.

### 5. Contrato HTTP

| Código | Quando |
|---|---|
| 200 | `{"pool_id": "pool-..."}` |
| 422 | parâmetro inválido (categoria fora do enum, não-inteiro, valor negativo) |
| 400 | filtro sem nenhum candidato |
| 503 | `job_events` sem linhas |

Sem 200 inventado quando não há dado. Sem escada de degradação.

Filtros (todos opcionais, combináveis): `category` (memory \| compute \| general \| storage), `instance_types` (lista CSV), `min_vcpu`, `min_memory` (inteiros), `az` (lista CSV).

Log rico (não HTTP): `pool_id` escolhido, score, S, F, `argmax_pool_id`, `near_tie`, filtro aplicado, runner-up se houver.

### 6. Parser do seed

- `finished_at` UTC mesmo sem sufixo; anexar timezone UTC.
- `pool_id` = `pool-<instance-type>-<az>`. Tipo tem ponto (`r6.xlarge`); AZ tem hífen (`us-east-1c`). Não fazer split ingênuo por hífen: prefixo `pool-`, instance type = token até o hífen seguinte (tipos não têm hífen), resto = AZ.
- `reason` ∈ {SPOT_INSTANCE_TERMINATION, TIMED_OUT, SPARK_EXECUTION_ERROR}. Status SUCCESS conta em S; FAILED + reason mapeia F ou ignora.
- Linha malformada / reason desconhecido / pool_id fora do padrão: descartar e seguir.

## Riscos / trade-offs

- [Seed só na tabela vazia] → Reinício não relê o JSONL se já houver linhas. Mitigação: documentar; para reset, `docker compose down -v`.
- [Score sobre todo o seed, sem janela] → Eventos velhos pesam igual aos novos. Aceito no MVP (premissa travada).
- [TIMED_OUT = falha do pool] → Timeout de job saudável em AZ boa penaliza o pool. Aceito no MVP.
- [GET agrega no SQL] → `GROUP BY pool_id` por request (~18 linhas). Sem cache. k6 20 RPS p95 ~10 ms; 200 RPS atinge ~199/s, p95 ~165 ms. Scan de 10k na API não sustenta 200 RPS (p95 ~5 s). Documentado em `docs/cenarios-de-teste.md`.
- [Quase-empate] → No seed, `1a` e `1b` estão na margem: 200 RPS sem filtro se espalham. Com `?az=us-east-1a` o conjunto tem um membro. Não há teto de jobs/s por pool.
- [Catálogo estático] → Tipo novo no JSONL sem entrada em `catalog.json` não vira candidato. Mitigação: seed e catálogo versionados juntos.

## Plano de migração

Greenfield. Subir com `make dev`. Produção: push no GitHub; CD descrito em um parágrafo no README (build da imagem, deploy de réplicas stateless contra um Postgres). Sem rollback de schema (tabela criada na subida).

## Questões em aberto

Nenhuma. Premissas travadas pelo briefing do MVP.
