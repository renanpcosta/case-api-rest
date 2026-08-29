# Contexto do projeto

## Objetivo

API REST que devolve o `pool_id` de instâncias EC2 spot com maior chance de o job não
falhar por indisponibilidade, respeitando filtros de tipo de instância. Case: "Desafio 02 —
API REST para seleção de pools de instâncias".

Um comando de bootstrap: `make setup`. Aceite da API: `make dev` → `curl http://localhost:5050/get-pools` devolve JSON com
`pool_id`.

## Glossário

- **POOL**: instâncias de um mesmo tipo na mesma AZ. Id: `pool-<instance-type>-<az>`
  (ex. `pool-r6.xlarge-us-east-1c`).
- **AZ**: zona de disponibilidade AWS.
- **SPOT**: instância interruptível.
- **SCORE**: Laplace `(S+1)/(S+F+2)` sobre todos os 10_000 eventos do seed (janela de 24 h no arquivo; sem recorte no GET). Quase-empate: margem 0,05. Seed: `r6…1a` lidera, `r6…1b` na margem. Agregação **por GET**.

## Dado de entrada

Arquivo JSONL no repo (`data/events.jsonl`), 10_000 eventos com `finished_at` numa janela de 24 h. Substitui S3 no dev. Regenerar: `make seed` (`tools/generate_events.py`).

```json
{"finished_at": "2024-08-07T00:04:52.767830", "job_id": "my-job",
 "pool_id": "pool-r6.xlarge-us-east-1c", "status": "FAILED",
 "reason": "SPOT_INSTANCE_TERMINATION"}
```

Campos: `finished_at` (UTC ISO), `job_id`, `pool_id`, `status`, `reason`
(`SPOT_INSTANCE_TERMINATION` | `TIMED_OUT` | `SPARK_EXECUTION_ERROR`).

Premissas do parser:

1. `finished_at` é UTC mesmo sem sufixo; anexar UTC explicitamente.
2. `pool_id`: prefixo `pool-`; instance type até o próximo hífen (tipo tem ponto, não hífen);
   o resto é a AZ (tem hífen). Split ingênuo por hífen quebra.
3. Linha malformada / reason desconhecido / `pool_id` fora do padrão: descartar e seguir.

Três superfícies, não misturar: JSONL = dado; GET = query params; 200 = só `{"pool_id"}`.
Payload rico só no log.

## Requisitos (R1–R7)

- **R1**: Python > 3.9; GET devolve um pool; filtros de tipo de instância.
- **R2**: FastAPI + uvicorn; racional no ADR 1 (OpenAPI nativo).
- **R3**: Postgres apenas. JSONL local no lugar de S3. Sem Redis, MinIO ou worker.
- **R4**: API sem estado + Postgres compartilhado. Escalabilidade documentada (réplicas). k6 só como verificação local em `docs/cenarios-de-teste.md`, não no CI nem no runtime. Sem HPA.
- **R5**: README, 3 ADRs, `docs/api.md` (request/response), `docs/cenarios-de-teste.md` (incl. k6 local), testes unitários, CI (ruff + pytest). CD só no README.
- **R6**: `make setup` na máquina; `make dev` → compose (api + postgres) → `http://localhost:5050/get-pools`.
- **R7**: repo no GitHub.

Aliases: `/get-pool`, `/get-pools`, `/getpools`. Porta: 5050.

## Stack técnico (travado)

| Tema | Decisão |
|---|---|
| Python | `>=3.10` |
| Framework | FastAPI + uvicorn |
| Persistência | um Postgres; schema na subida, sem Alembic |
| Seed | `data/events.jsonl` (10k, 24 h, versionado) se a tabela estiver vazia |
| Catálogo | `data/catalog.json` |
| Qualidade | ruff + pytest |
| Infra | Docker Compose: api + postgres; `make setup` no host |
| CI | GitHub Actions: ruff + pytest |

## Score (travado)

- `S` = SUCCESS
- `F` = SPOT_INSTANCE_TERMINATION + TIMED_OUT (peso 1)
- SPARK_EXECUTION_ERROR persistido, fora de S e F
- `score = (S+1)/(S+F+2)`
- quase-empate: entram pools com `score >= melhor - 0,05`; um membro → esse pool; dois ou mais → sorteio uniforme
- seed: `pool-r6.xlarge-us-east-1a` lidera; `pool-r6.xlarge-us-east-1b` fica na margem (GET sem filtro espalha)
- todos os 10_000 eventos do seed; timestamps numa janela de 24 h; sem recorte e sem decaimento no GET
- agregação S/F **em cada GET** no SQL (`GROUP BY pool_id`); Laplace/quase-empate em processo (sem cache de score)

## Filtros (todos opcionais)

`category` (memory|compute|general|storage), `instance_types`, `min_vcpu`, `min_memory`, `az`.

Erros: 422 parâmetro inválido; 400 filtro sem candidato; 503 banco sem eventos.
Sem 200 inventado. Sem escada de degradação.

## Convenções

- Layout: `src/pool_selector/{app,scoring,catalog,db}.py`. Sem hexagonal.
- Logs estruturados para a escolha do pool. Sem `print` no caminho de request.
- Docs permitidos: README, 3 ADRs, `docs/api.md`, `docs/cenarios-de-teste.md`.

## Anti-objetivos

Wilson, softmax, UCB, cooldown, inflight, meia-vida, buckets, Redis, MinIO, worker, SQS,
Alembic, hexagonal, `.cursor/` neste produto, k6 no CI/runtime, Prometheus, `/metrics`, `/version`,
payload HTTP explicável, families/exclude_az/job_id/candidates, 12 ADRs, HPA, OIDC, GHCR.
