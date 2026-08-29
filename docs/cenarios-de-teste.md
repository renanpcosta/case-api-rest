# Cenários de teste

Como verificar a API à mão: unitário default, filtros e teste de performance com k6. Contrato e pares request/response: [api.md](api.md). Score: [ADR 3](adr/003-score.md).

## Pré-requisitos

1. `make setup` (uma vez na máquina)
2. `make dev` — API em [http://localhost:5050/get-pools](http://localhost:5050/get-pools)
3. Para carga: [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) (`brew install k6`). Não entra no `make setup`.

Parar: `make down`. Resetar seed: `docker compose down -v`, depois `make dev`.

Abrir o log **antes** dos curls de 200 (terminal 2):

```bash
docker compose logs -f api
```

Só GET **200** grava o JSON `pool_selected`. 422/400/503 **não** emitem essa linha.

## O que o log prova

Cada 200 vira uma linha JSON (não vai no body HTTP). Campos:


| Campo            | Significado                        | O que conferir                                |
| ---------------- | ---------------------------------- | --------------------------------------------- |
| `event`          | Sempre `pool_selected`             | A linha é escolha de pool, não erro de subida |
| `pool_id`        | Id devolvido no HTTP               | Igual ao `curl`                               |
| `score`          | Laplace `(S+1)/(S+F+2)`            | Entre 0 e 1; no seed default ~0,9 no vencedor |
| `s`              | Contagem SUCCESS do pool           | Inteiro ≥ 0                                   |
| `f`              | SPOT + TIMED_OUT                   | SPARK **não** entra aqui                      |
| `argmax_pool_id` | Melhor score (desempate lex)       | Sempre `…-1a` no seed sem filtro              |
| `near_tie`       | Pools com `score >= melhor - 0,05` | Seed sem filtro: **dois** ids (`1a` e `1b`)   |
| `filters`        | Query params normalizados          | `null` se o param não veio                    |
| `runner_up`      | Segundo no ranking                 | Sem filtro: `pool-r6.xlarge-us-east-1b`       |


Exemplo (valores de `s`/`score` no seed de 10k **não** são os do sample de 27 linhas):

```json
{
  "event": "pool_selected",
  "pool_id": "pool-r6.xlarge-us-east-1b",
  "score": 0.9013,
  "s": 474,
  "f": 51,
  "argmax_pool_id": "pool-r6.xlarge-us-east-1a",
  "near_tie": ["pool-r6.xlarge-us-east-1a", "pool-r6.xlarge-us-east-1b"],
  "filters": {
    "category": null,
    "instance_types": null,
    "min_vcpu": null,
    "min_memory": null,
    "az": null
  },
  "runner_up": { "pool_id": "pool-r6.xlarge-us-east-1b", "score": 0.9013, "s": 474, "f": 51 }
}
```

Neste exemplo o HTTP sorteou `1b`, mas `argmax_pool_id` continua `1a`. Gap Laplace `1a`–`1b` ≈ 0,042 (< 0,05).

Por que o HTTP é só `{"pool_id"}`: o case pede um id para o job. Score e evidência ficam no log de plataforma.

---



## 1. Unitário default

**O que prova:** parse, Laplace, quase-empate no seed 10k/24 h, contrato HTTP sem filtro. `r6.xlarge` em `1a` lidera; `1b` fica na margem 0,05 → o GET **sorteia**.

### 1.1 pytest (sem Docker)

```bash
make lint
make test
```

Esperado: ruff limpo, **32 passed**. Cobre `tests/test_parse.py`, `test_scoring.py`, `test_catalog.py`, `test_api.py` (usa `events.sample.jsonl`, não o 10k) e `test_seed.py` (10k + janela 24 h + quase-empate `1a`/`1b`).

### 1.2 GET sem filtro

```bash
curl -s http://localhost:5050/get-pools
```


| Verificar            | Esperado                                                  |
| -------------------- | --------------------------------------------------------- |
| HTTP / body          | 200, só a chave `pool_id` (`…-1a` **ou** `…-1b`)          |
| Log `near_tie`       | os **dois** ids (prova o quase-empate sem repetir o curl) |
| Log `argmax_pool_id` | `pool-r6.xlarge-us-east-1a` (mesmo se o body for `1b`)    |
| Log `filters`        | Todos `null`                                              |


Aliases `/get-pool` e `/getpools`: mesmo contrato. O sorteio em massa fica no k6 (§3).

Prova de **um** membro (sem sorteio):

```bash
curl -s 'http://localhost:5050/get-pool?az=us-east-1a'
```

`1b` sai do filtro. Esperado: sempre `pool-r6.xlarge-us-east-1a`; log `near_tie` com um id.

Swagger: [http://localhost:5050/docs](http://localhost:5050/docs) → `/get-pools` → Execute, sem params.

**Se** `near_tie` **tiver só** `1a`**:** volume `pgdata` ainda tem seed antigo. `docker compose down -v` e `make dev`.

---



## 2. Unitário com filtros

**O que prova:** catálogo + interseção de query params; 422/400 sem inventar pool.

Rodar com `docker compose logs -f api` aberto. Em 200, `filters` no log **tem** de espelhar a query.

### 2.1 memory + AZ (200)

```bash
curl -s 'http://localhost:5050/get-pool?category=memory&az=us-east-1a'
```


| Verificar              | Esperado                                                                                     |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| HTTP / body            | 200, `pool_id` de categoria memory na AZ `us-east-1a` (no seed: `pool-r6.xlarge-us-east-1a`) |
| Log `filters.category` | `"memory"`                                                                                   |
| Log `filters.az`       | `["us-east-1a"]`                                                                             |
| Log `pool_id`          | Contém `r6` (memory) e `us-east-1a`                                                          |




### 2.2 tipos + min_vcpu (200)

```bash
curl -s 'http://localhost:5050/get-pool?instance_types=r6.xlarge,r6.2xlarge&min_vcpu=8'
```

`r6.xlarge` tem 4 vCPU — **sai**. Sobram `r6.2xlarge` nas AZs do seed.


| Verificar                    | Esperado                      |
| ---------------------------- | ----------------------------- |
| HTTP                         | 200                           |
| Body `pool_id`               | Começa com `pool-r6.2xlarge-` |
| Log `filters.instance_types` | `["r6.xlarge", "r6.2xlarge"]` |
| Log `filters.min_vcpu`       | `8`                           |




### 2.3 compute (200, pool **muda**)

```bash
curl -s 'http://localhost:5050/get-pool?category=compute'
```


| Verificar              | Esperado                                     |
| ---------------------- | -------------------------------------------- |
| Body                   | `pool-c6.…` — **não** `r6.xlarge-us-east-1a` |
| Log `filters.category` | `"compute"`                                  |


O filtro cortou os memory. O GET default não é “sempre o mesmo id”.

### 2.4 AZ só (200)

```bash
curl -s 'http://localhost:5050/get-pool?az=us-east-1c'
```


| Verificar        | Esperado                 |
| ---------------- | ------------------------ |
| Body `pool_id`   | Termina com `us-east-1c` |
| Log `filters.az` | `["us-east-1c"]`         |




### 2.5 category inválida (422)

```bash
curl -i 'http://localhost:5050/get-pool?category=gpu'
```


| Verificar | Esperado                                                |
| --------- | ------------------------------------------------------- |
| HTTP      | **422**                                                 |
| Body      | erro FastAPI/Pydantic (`gpu` fora do enum)              |
| Log       | **não** aparece `pool_selected` (nem chegou no handler) |




### 2.6 tipo fora do catálogo (400)

```bash
curl -i 'http://localhost:5050/get-pool?instance_types=r6.24xlarge'
```


| Verificar | Esperado                        |
| --------- | ------------------------------- |
| HTTP      | **400**                         |
| Body      | `no candidates match filters`   |
| Log       | **não** aparece `pool_selected` |




### 2.7 AZ sem candidato (400)

```bash
curl -i 'http://localhost:5050/get-pool?az=us-west-2a'
```

Mesmo 400: o seed só tem `us-east-1a/b/c`.

**503** (`no events in database`) só com `job_events` vazia — não use no demo com seed carregado.

---



## 3. Teste de performance (k6)

**O que prova:** R4 é pico de GET. k6 inventa clientes HTTP contra `localhost:5050`. Não entra no `make setup`, no Compose nem no CI.

Script: [load.js](../load.js). O GET pede S/F ao Postgres (`GROUP BY pool_id`, ~18 linhas) e aplica Laplace/quase-empate em memória. Sem cache de score.

### 3.1 Instalar

```bash
brew install k6
k6 version
```

[Instalação em outros SOs](https://grafana.com/docs/k6/latest/set-up/install/).

### 3.2 O que o script faz

Cada iteração é um `GET` igual ao `curl`. Variáveis (`-e NOME=valor`):


| Variável   | Default                 | Uso                                                                                |
| ---------- | ----------------------- | ---------------------------------------------------------------------------------- |
| `BASE_URL` | `http://localhost:5050` | Host da API                                                                        |
| `ROUTE`    | `/get-pools`            | Caminho. **Não** use `PATH` — no macOS `PATH` é o das ferramentas e a URL vira 404 |
| `QUERY`    | vazio                   | Query string sem `?` (ex. `category=memory`)                                       |
| `RPS`      | `20`                    | Requests **novas por segundo** (não o total)                                       |
| `DURATION` | `15s`                   | Quanto tempo manter essa taxa                                                      |


Executor: `constant-arrival-rate` — tenta `RPS` GETs novos a cada segundo, como um pico constante.

### 3.3 Como rodar

1. API no ar: `make dev` e `curl -sf http://localhost:5050/get-pools`.
2. Baseline (20 RPS / 15 s ≈ 300 GETs):

```bash
k6 run load.js
```

3. Pico do briefing (200 RPS / 15 s). A taxa deve ser atingida (~3000 GETs):

```bash
k6 run -e RPS=200 -e DURATION=15s load.js
```

Filtro (manada no mesmo recorte):

```bash
k6 run -e RPS=20 -e QUERY='category=memory' load.js
k6 run -e RPS=20 -e QUERY='az=us-east-1a' load.js
```

Com `az=us-east-1a` o HTTP deve ficar só em `…-1a`. Sem filtro, `pool_id` mistura `1a` e `1b` (quase-empate).

### 3.4 Como ler o relatório


| Linha                        | Significado                                                                           |
| ---------------------------- | ------------------------------------------------------------------------------------- |
| `checks_succeeded`           | Fração que passou nos dois checks: HTTP 200 **e** body com `pool_id`                  |
| `status is 200`              | Contagem de checks de status (2 checks × N requests)                                  |
| `http_req_failed`            | Rede, timeout, status de erro segundo o k6                                            |
| `http_reqs` / `iterations`   | GETs que **completararam**                                                            |
| `http_req_duration` `p(95)`  | 95% dos GETs mais rápidos que esse valor                                              |
| `dropped_iterations`         | O k6 **desistiu** de disparar porque não havia VU livre — a API não acompanhou a taxa |
| `Insufficient VUs` (warning) | Mesma coisa: latência alta → cada cliente fica ocupado → a taxa alvo não é atingida   |
| `pool_selected`              | Counter: quantos bodies tinham `pool_id`                                              |


Não há SLO numérico no MVP. Anote p95 e se a taxa pedida foi atingida (`http_reqs` ≈ `RPS × duração`).

### 3.5 Exemplos de resultado (seed 10k, medidos neste repo)

Máquina local, Compose `api` + `postgres`.

#### Antes — GET trazia 10k linhas e agregava em Python

| Rodada | Requests | Taxa | checks | p95 | `dropped_iterations` |
|---|---|---|---|---|---|
| 20 RPS / 15 s | 300 | ~20/s | 100% | **33,5 ms** | não |
| 200 RPS / 15 s | **845** | **~49/s** | 100% nos que completaram | **5,46 s** | **2156** + Insufficient VUs |

Um `curl` isolado: ~28–46 ms. O Postgres sozinho no `SELECT` das 10k: **~1,0 ms**.

#### Depois — GET usa `GROUP BY` (~18 linhas)

| Rodada | Requests | Taxa | checks | p95 | `dropped_iterations` |
|---|---|---|---|---|---|
| 20 RPS / 15 s | 301 | ~20/s | 100% | **10,3 ms** | não |
| 200 RPS / 15 s | **3001** | **~199/s** | **100%** | **164 ms** | não |

Um `curl` isolado: ~11–14 ms. O `GROUP BY` no Postgres: **~2,5 ms**, 18 grupos, 24 kB.

A 200 RPS a taxa do briefing **é atingida**. p95 sobe com a fila (max ~288 ms), sem 5xx e sem iterações descartadas.

Trecho típico do pico depois:

```
checks_succeeded...: 100.00% 6002 out of 6002
http_req_duration..............: avg=37.61ms ... p(95)=164.49ms
http_req_failed................: 0.00%  0 out of 3001
http_reqs......................: 3001   199.18/s
```

#### Quase-empate no pico

No log (`docker compose logs -f api`), GET sem filtro: `near_tie` com **dois** ids; `argmax_pool_id` sempre `…-1a`; `pool_id` HTTP alterna `1a`/`1b`. Com `-e QUERY='az=us-east-1a'`, um só membro.

### 3.6 Testes com outras massas


| Rodada                                            | O que aconteceu                                                          |
| ------------------------------------------------- | ------------------------------------------------------------------------ |
| Seed pequeno (~dezenas de linhas), 200 RPS / 30 s | 6000/6000 HTTP 200, falhas 0%, p95 **14,1 ms**                           |
| 1M de linhas, GET relê tudo                       | Docker `Exited (137)` (OOM). k6: `EOF` / `connection refused`, p95 ~10 s |
| 1M + mapa de ~18 scores na subida                 | 100% 200, p95 **2,4 ms** — fora deste MVP (sem cache de score)           |


---



## Ordem sugerida (~15 min)

1. `make lint` e `make test`
2. Terminal 2: `docker compose logs -f api`
3. Um curl sem filtro; no log, `near_tie` com dois ids
4. Filtros 2.1–2.6 (pares request/response em [api.md](api.md))
5. k6 baseline (`k6 run load.js`) e pico (`RPS=200`)
6. `make down` se terminar o demo

