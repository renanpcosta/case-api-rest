## ADDED Requirements

### Requirement: Três aliases GET devolvem só pool_id

O sistema SHALL expor `GET /get-pool`, `GET /get-pools` e `GET /getpools` com o mesmo comportamento. Resposta 200 MUST ser exatamente um JSON com a chave `pool_id`. MUST NÃO incluir score, evidence, policy nem warnings no corpo HTTP.

#### Scenario: Alias /get-pool responde 200

- **WHEN** o banco tem eventos e existe ao menos um candidato
- **THEN** `GET /get-pool` responde 200 com `{"pool_id": "<id>"}`

#### Scenario: Alias /get-pools responde 200

- **WHEN** o banco tem eventos e existe ao menos um candidato
- **THEN** `GET /get-pools` responde 200 com `{"pool_id": "<id>"}`

#### Scenario: Alias /getpools responde 200

- **WHEN** o banco tem eventos e existe ao menos um candidato
- **THEN** `GET /getpools` responde 200 com `{"pool_id": "<id>"}`

### Requirement: Erros 422, 400 e 503 sem degradação

Parâmetro inválido MUST responder 422. Filtro que deixa zero candidatos MUST responder 400. `job_events` sem linhas MUST responder 503. MUST NÃO inventar 200 quando não há dado. MUST NÃO usar escada de degradação.

#### Scenario: Parâmetro inválido é 422

- **WHEN** `category` não é um de memory|compute|general|storage, ou `min_vcpu`/`min_memory` não é inteiro ≥ 0
- **THEN** a resposta é 422

#### Scenario: Filtro sem candidato é 400

- **WHEN** o banco tem eventos mas nenhum pool passa nos filtros
- **THEN** a resposta é 400

#### Scenario: Banco sem eventos é 503

- **WHEN** `job_events` não tem linhas
- **THEN** a resposta é 503

### Requirement: Log rico fora do HTTP

O sistema SHALL emitir um log estruturado da escolha (pool, score, S, F, `argmax_pool_id`, `near_tie`, filtros, runner-up se houver) para o time de plataforma debugar "por que esse pool?". Esse conteúdo MUST NÃO aparecer no corpo HTTP.

#### Scenario: Log contém evidência e a resposta não

- **WHEN** um GET retorna 200
- **THEN** o log da request contém score, S/F, `argmax_pool_id` e `near_tie` do conjunto de quase-empate
- **AND** o corpo HTTP contém somente `pool_id`
