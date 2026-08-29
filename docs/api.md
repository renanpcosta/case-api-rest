# HTTP API

Base: `http://localhost:5050`

Swagger (gerado pelo FastAPI): [http://localhost:5050/docs](http://localhost:5050/docs) — só com o stack no ar (`make dev`).

## Rotas

O mesmo handler nas três:

- `GET /get-pool`
- `GET /get-pools`
- `GET /getpools`

O body do request é vazio. Eventos **não** são enviados por HTTP. Filtros são query params.

## Query params (todos opcionais, combináveis)

| Param | Type | Notas |
|---|---|---|
| `category` | `memory` \| `compute` \| `general` \| `storage` | Categoria no catálogo |
| `instance_types` | CSV | ex. `r6.xlarge,r6.2xlarge` |
| `min_vcpu` | inteiro ≥ 0 | `vcpu` do catálogo |
| `min_memory` | inteiro ≥ 0 | `memory_gib` do catálogo |
| `az` | CSV | ex. `us-east-1a,us-east-1c` |

Não expostos: `families`, `exclude_az`, `job_id`, `candidates`.

## Códigos de status

### 200

```json
{"pool_id": "pool-r6.xlarge-us-east-1a"}
```

Só `pool_id`. Sem score, evidence, policy ou warnings no body.

Com o mesmo filtro, se vários pools estão a 0,05 do melhor Laplace, o `pool_id` pode variar entre requests (sorteio uniforme). No seed versionado (10_000 eventos em 24 h) `r6.xlarge` em `us-east-1a` lidera e `us-east-1b` entra no quase-empate: o GET sem filtro sorteia entre os dois. `argmax_pool_id` no log permanece `pool-r6.xlarge-us-east-1a`.

### 422

Parâmetro inválido (`category` desconhecido, `min_vcpu` / `min_memory` não inteiro ou negativo). Erro de validação FastAPI/Pydantic.

### 400

O banco tem eventos, mas nenhum pool passa nos filtros (ou o instance type não está em `data/catalog.json`).

### 503

`job_events` não tem linhas. Sem 200 inventado. Sem escada de degradação.

## Exemplos

```bash
curl http://localhost:5050/get-pools
curl 'http://localhost:5050/get-pool?category=memory&az=us-east-1a'
curl 'http://localhost:5050/get-pool?instance_types=r6.xlarge,r6.2xlarge&min_vcpu=8'
curl -i 'http://localhost:5050/get-pool?category=gpu'
curl -i 'http://localhost:5050/get-pool?instance_types=r6.24xlarge'
```

Os dois últimos esperam **422** (`category` inválida) e **400** (filtro sem candidato). **503** só aparece com `job_events` vazia.

## Log rico (não HTTP)

Em 200 a API registra uma linha JSON para debug de plataforma:

```json
{
  "event": "pool_selected",
  "pool_id": "pool-r6.xlarge-us-east-1a",
  "score": 0.9435,
  "s": 500,
  "f": 29,
  "argmax_pool_id": "pool-r6.xlarge-us-east-1a",
  "near_tie": ["pool-r6.xlarge-us-east-1a", "pool-r6.xlarge-us-east-1b"],
  "filters": {
    "category": null,
    "instance_types": null,
    "min_vcpu": null,
    "min_memory": null,
    "az": null
  },
  "runner_up": {
    "pool_id": "pool-r6.xlarge-us-east-1b",
    "score": 0.9013,
    "s": 474,
    "f": 51
  }
}
```

Ver o log:

```bash
docker compose logs api
docker compose logs -f api
```

Cenários manuais (default, filtros, 200 RPS e o que cada campo do log prova): [cenarios-de-teste.md](cenarios-de-teste.md).
