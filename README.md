# Seletor de pools

GET que devolve o `pool_id` de instâncias EC2 spot com maior chance de um job Spark não falhar por falta de capacidade.

## Como subir

Na máquina (uma vez): 

- Python 3.10+
- [Docker Desktop](https://docs.docker.com/get-docker/) aberto
- `make`
- `curl`

Depois:

```bash
make setup   # opcional para só subir a API; obrigatório uma vez para make lint / make test
make dev
curl http://localhost:5050/get-pools
```

`make setup` cria `.venv`, instala FastAPI/pytest/ruff e constrói as imagens. `make dev` sobe Postgres + API e já faz `--build` das imagens, então você pode pular o setup se só quer o curl de aceite. Stack: [compose.yaml](compose.yaml) ([Compose](https://docs.docker.com/compose/), [Compose file](https://docs.docker.com/reference/compose-file/)).


| Serviço  | Host                                                               | Uso                       |
| -------- | ------------------------------------------------------------------ | ------------------------- |
| API      | [http://localhost:5050/get-pools](http://localhost:5050/get-pools) | GET do case               |
| Swagger  | [http://localhost:5050/docs](http://localhost:5050/docs)           | Tentar filtros no browser |
| Postgres | `localhost:5432`                                                   | IDE (DBeaver) ou `psql`   |


Corpo esperado do curl:

```json
{"pool_id": "pool-r6.xlarge-us-east-1a"}
```

Sem filtro o seed tem quase-empate `1a` / `1b`: o `pool_id` pode ser `us-east-1a` ou `us-east-1b`. `argmax_pool_id` no log continua `…-1a`.

Parar: `make down`. Resetar o seed (apaga o volume `pgdata`): `docker compose down -v`, depois `make dev` (o seed só carrega quando `job_events` está vazia).

Se o Compose já estava no ar **antes** de publicar a 5432: `make down` e `make dev` de novo.

## Postgres

Credenciais (dev): user `pool`, password `pool`, database `pool`.

### IDE (DBeaver, TablePlus, DataGrip)

1. Instalar o cliente ([DBeaver](https://dbeaver.io/download/))
2. Nova conexão PostgreSQL ([docs DBeaver](https://dbeaver.com/docs/dbeaver/Database-driver-PostgreSQL/))
3. Preencher:


| Campo    | Valor       |
| -------- | ----------- |
| Host     | `localhost` |
| Port     | `5432`      |
| Database | `pool`      |
| Username | `pool`      |
| Password | `pool`      |


JDBC: `jdbc:postgresql://localhost:5432/pool`

O stack precisa estar no ar (`make dev`). Se a conexão recusar, a porta 5432 está ocupada por outro Postgres no host.

### Terminal (dentro do container)

```bash
docker compose exec postgres psql -U pool -d pool
```

No `psql`:

```sql
SELECT COUNT(*) FROM job_events;
SELECT pool_id, status, reason FROM job_events LIMIT 10;
\q
```

`psql` no host (sem entrar no container), com [Postgres client](https://www.postgresql.org/docs/16/app-psql.html) instalado:

```bash
psql postgresql://pool:pool@localhost:5432/pool
```



## Premissas

- A entrada é JSONL versionado em `data/events.jsonl` (10_000 eventos, `finished_at` numa janela de 24 h; substitui o S3 no desenvolvimento). Regenerar: `make seed`. O request não lê o arquivo.
- `finished_at` sem sufixo de timezone é UTC.
- `pool_id` é `pool-<instance-type>-<az>`. O tipo contém ponto (`r6.xlarge`); a AZ contém hífens (`us-east-1c`).
- O score usa **todos** os 10_000 eventos do seed: `score = (S+1)/(S+F+2)`. `S` = SUCCESS. `F` = SPOT_INSTANCE_TERMINATION + TIMED_OUT. SPARK_EXECUTION_ERROR é persistido e ignorado pelo score. A agregação S/F corre em cada GET no Postgres (`GROUP BY pool_id`).
- Quase-empate: entram pools com `score >= melhor - 0,05`. Um candidato → esse pool. Dois ou mais → sorteio uniforme. No seed, `r6.xlarge` em `us-east-1a` lidera e `us-east-1b` fica na margem: `curl` sem filtro pode devolver os dois.
- O corpo HTTP 200 contém só `pool_id`.
- Aliases: `/get-pool`, `/get-pools`, `/getpools`.
- Erros: 422 parâmetro inválido, 400 filtro sem candidatos, 503 banco vazio.

Detalhes: [docs/api.md](docs/api.md) (pares request/response). Testes manuais e performance: [docs/cenarios-de-teste.md](docs/cenarios-de-teste.md). Decisões: [ADR 1 FastAPI](docs/adr/001-fastapi.md), [ADR 2 Postgres](docs/adr/002-postgres.md), [ADR 3 Score](docs/adr/003-score.md).

## Testes

Passo a passo (pytest, filtros, o que olhar no log): [docs/cenarios-de-teste.md](docs/cenarios-de-teste.md).

Pares request/response (200, 422, 400, 503): [docs/api.md](docs/api.md#requisições-e-respostas).

Performance (k6, como rodar, como ler o relatório, números medidos no seed 10k): [docs/cenarios-de-teste.md](docs/cenarios-de-teste.md#3-teste-de-performance-k6). k6 não entra no `make setup` nem no CI (`brew install k6`).

```bash
make setup   # obrigatório uma vez (venv para lint e test)
make lint
make test
make dev
```

`make lint` e `make test` usam `.venv`. Não precisa ativar o venv.

Swagger: [http://localhost:5050/docs](http://localhost:5050/docs). Contrato: [docs/api.md](docs/api.md).

CI em cada PR: `[.github/workflows/ci.yml](.github/workflows/ci.yml)` (ruff + pytest).

## CD

Construir a imagem da API a partir do `Dockerfile`, enviá-la ao registry que o host usa e subir réplicas stateless que compartilham um Postgres (`DATABASE_URL`). Não há pipeline disso neste repositório; as réplicas leem o mesmo `job_events` via `GROUP BY` no GET. Com quase-empate podem devolver `pool_id` diferentes no mesmo filtro.