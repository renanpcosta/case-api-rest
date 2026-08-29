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


| Param            | Type                                         | Notas                       |
| ---------------- | -------------------------------------------- | --------------------------- |
| `category`       | `memory` | `compute` | `general` | `storage` | Categoria no catálogo       |
| `instance_types` | CSV                                          | ex. `r6.xlarge,r6.2xlarge`  |
| `min_vcpu`       | inteiro ≥ 0                                  | `vcpu` do catálogo          |
| `min_memory`     | inteiro ≥ 0                                  | `memory_gib` do catálogo    |
| `az`             | CSV                                          | ex. `us-east-1a,us-east-1c` |


Não expostos: `families`, `exclude_az`, `job_id`, `candidates`.

## Códigos de status


| Código  | Quando                                       | Corpo                                       |
| ------- | -------------------------------------------- | ------------------------------------------- |
| **200** | Há candidato                                 | só `{"pool_id": "..."}`                     |
| **422** | Query inválida (enum, não-inteiro, negativo) | `detail` do FastAPI/Pydantic                |
| **400** | Banco tem eventos, filtro zera candidatos    | `{"detail": "no candidates match filters"}` |
| **503** | `job_events` vazia                           | `{"detail": "no events in database"}`       |


Com o mesmo filtro, se vários pools estão a 0,05 do melhor Laplace, o `pool_id` pode variar (sorteio uniforme). No seed versionado (10_000 eventos em 24 h) `r6.xlarge` em `us-east-1a` lidera e `us-east-1b` entra no quase-empate: o GET sem filtro sorteia entre os dois. `argmax_pool_id` no log permanece `pool-r6.xlarge-us-east-1a`.

## Requisições e respostas

Stack no ar (`make dev`). Os JSON abaixo estão formatados; o `curl` devolve uma linha só. Headers `date` variam.

### 200 — sem filtro

```bash
curl -i http://localhost:5050/get-pools
```

```
HTTP/1.1 200 OK
content-type: application/json

{"pool_id": "pool-r6.xlarge-us-east-1a"}
```

Pode vir `…-us-east-1b` no lugar de `…-1a`. Score **não** vem no body.

Os aliases `/get-pool` e `/getpools` devolvem o mesmo contrato.

### 200 — memory + AZ (conjunto unitário)

```bash
curl -i 'http://localhost:5050/get-pool?category=memory&az=us-east-1a'
```

```
HTTP/1.1 200 OK
content-type: application/json

{"pool_id": "pool-r6.xlarge-us-east-1a"}
```

`1b` sai do filtro. Sem sorteio: sempre `…-1a`.

### 200 — tipos + min_vcpu

```bash
curl -i 'http://localhost:5050/get-pool?instance_types=r6.xlarge,r6.2xlarge&min_vcpu=8'
```

```
HTTP/1.1 200 OK
content-type: application/json

{"pool_id": "pool-r6.2xlarge-us-east-1a"}
```

`r6.xlarge` tem 4 vCPU e sai. O `pool_id` começa com `pool-r6.2xlarge-` (AZ pode variar se houver quase-empate entre AZs desse tipo).

### 200 — category compute (o id muda)

```bash
curl -i 'http://localhost:5050/get-pool?category=compute'
```

```
HTTP/1.1 200 OK
content-type: application/json

{"pool_id": "pool-c6.2xlarge-us-east-1a"}
```

Não é o default `r6.xlarge`. O filtro cortou os pools memory.

### 200 — só AZ

```bash
curl -i 'http://localhost:5050/get-pool?az=us-east-1c'
```

```
HTTP/1.1 200 OK
content-type: application/json

{"pool_id": "pool-i3.xlarge-us-east-1c"}
```

O id **termina** com `us-east-1c`. Neste seed o melhor Laplace nessa AZ foi `i3.xlarge`; se o seed for regenerado, o tipo pode mudar.

### 422 — category fora do enum

```bash
curl -i 'http://localhost:5050/get-pool?category=gpu'
```

```
HTTP/1.1 422 Unprocessable Entity
content-type: application/json
```

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["query", "category"],
      "msg": "Input should be 'memory', 'compute', 'general' or 'storage'",
      "input": "gpu",
      "ctx": {
        "expected": "'memory', 'compute', 'general' or 'storage'"
      }
    }
  ]
}
```

Não há linha `pool_selected` no log: a validação para antes do handler.

### 422 — min_vcpu negativo

```bash
curl -i 'http://localhost:5050/get-pool?min_vcpu=-1'
```

```
HTTP/1.1 422 Unprocessable Entity
content-type: application/json
```

```json
{
  "detail": [
    {
      "type": "greater_than_equal",
      "loc": ["query", "min_vcpu"],
      "msg": "Input should be greater than or equal to 0",
      "input": "-1",
      "ctx": { "ge": 0 }
    }
  ]
}
```

`min_memory=abc` também é 422 (não inteiro).

### 400 — tipo fora do catálogo

```bash
curl -i 'http://localhost:5050/get-pool?instance_types=r6.24xlarge'
```

```
HTTP/1.1 400 Bad Request
content-type: application/json

{"detail": "no candidates match filters"}
```



### 400 — AZ sem candidato no seed

```bash
curl -i 'http://localhost:5050/get-pool?az=us-west-2a'
```

```
HTTP/1.1 400 Bad Request
content-type: application/json

{"detail": "no candidates match filters"}
```

O seed só tem `us-east-1a` / `1b` / `1c`.

### 503 — banco vazio

Não aparece depois de `make dev` com seed carregado.

```json
{"detail": "no events in database"}
```

HTTP **503**. Para reproduzir: tabela `job_events` sem linhas (não use no demo com o volume `pgdata` populado).

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

Valores de `s` / `score` são do seed de 10k, não do sample de 27 linhas. Ver o log:

```bash
docker compose logs api
docker compose logs -f api
```

Cenários manuais (default, filtros, k6 e o que cada campo do log prova): [cenarios-de-teste.md](cenarios-de-teste.md).

Teste de performance (instalar k6, comandos, como ler o relatório, números medidos): [cenarios-de-teste.md](cenarios-de-teste.md#3-teste-de-performance-k6).