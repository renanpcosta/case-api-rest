## ADDED Requirements

### Requirement: Agregação S e F por pool

Para cada `pool_id` com eventos carregados, o sistema SHALL calcular `S` = contagem de `SUCCESS` e `F` = contagem de `SPOT_INSTANCE_TERMINATION` + `TIMED_OUT` (peso 1 cada). MUST usar todos os eventos do seed, sem janela temporal e sem decaimento. MUST agregar S/F **em cada GET** no Postgres (`GROUP BY pool_id`), sem cache de score na subida. Laplace, filtro e quase-empate continuam em processo sobre o mapa de pools.

#### Scenario: SUCCESS incrementa S

- **WHEN** o pool tem um evento com `status` `SUCCESS`
- **THEN** `S` aumenta em 1 e `F` não muda

#### Scenario: GET relê os eventos do banco

- **WHEN** um GET é atendido
- **THEN** a agregação S/F é calculada a partir das linhas atuais de `job_events` via `GROUP BY` (não de um mapa congelado na subida)

#### Scenario: SPOT_INSTANCE_TERMINATION incrementa F

- **WHEN** o pool tem um evento com `reason` `SPOT_INSTANCE_TERMINATION`
- **THEN** `F` aumenta em 1 e `S` não muda

#### Scenario: TIMED_OUT conta como falha

- **WHEN** o pool tem um evento com `reason` `TIMED_OUT`
- **THEN** `F` aumenta em 1 (peso 1)

### Requirement: SPARK_EXECUTION_ERROR não altera o score

`SPARK_EXECUTION_ERROR` MUST NÃO entrar em `S` nem em `F`. O evento pode existir em `job_events`.

#### Scenario: SPARK_EXECUTION_ERROR não muda S nem F

- **WHEN** um pool tem apenas eventos `SPARK_EXECUTION_ERROR` além do mesmo conjunto S/F de outro cenário
- **THEN** `S` e `F` (e portanto o score) são iguais ao cenário sem esses eventos

### Requirement: Score Laplace

O sistema SHALL calcular `score = (S + 1) / (S + F + 2)` com divisão em ponto flutuante.

#### Scenario: Sem evidência o score é 1/2

- **WHEN** um pool tem `S = 0` e `F = 0`
- **THEN** o score é `0.5`

#### Scenario: Um sucesso não vence 950/1000

- **WHEN** o pool A tem `S = 1`, `F = 0` e o pool B tem `S = 950`, `F = 50`
- **THEN** o score de B é maior que o de A

### Requirement: Quase-empate com sorteio uniforme

Entre os pools que passam no filtro, o sistema SHALL formar o conjunto de quase-empate: todo pool com `score >= melhor_score - 0,05`. Se o conjunto tiver um membro, MUST devolver esse pool. Se tiver dois ou mais, MUST escolher um membro com probabilidade uniforme. MUST NÃO usar softmax, Wilson, cooldown nem inflight.

#### Scenario: Maior score disparado vence sozinho

- **WHEN** dois pools passam no filtro e a diferença de score é maior que 0,05
- **THEN** o retornado é o de maior score em todos os requests

#### Scenario: Scores dentro da margem entram no sorteio

- **WHEN** o melhor pool tem 3 SUCCESS e o segundo tem 2 SUCCESS (Laplace 0,80 e 0,75)
- **THEN** os dois `pool_id` pertencem ao conjunto de quase-empate

#### Scenario: Empate exato espalha o HTTP

- **WHEN** dois pools passam no filtro com o mesmo score
- **THEN** requests sucessivos com o mesmo filtro devolvem os dois `pool_id`

#### Scenario: Seed 10k tem quase-empate 1a / 1b

- **WHEN** o score usa `data/events.jsonl` sem filtro
- **THEN** `pool-r6.xlarge-us-east-1a` é o argmax e `pool-r6.xlarge-us-east-1b` pertence ao conjunto de quase-empate

O ranking `(-score, pool_id)` permanece para ordenar o conjunto e o log (`argmax_pool_id`). Não substitui o sorteio quando há mais de um membro.
