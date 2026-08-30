# Event Ingestion Specification

## Purpose
Parse the JSONL seed, persist valid job events, and load them into Postgres once on empty startup.

## Requirements

### Requirement: Parse de evento JSONL do enunciado

O sistema SHALL ler um arquivo JSONL com um evento por linha. Cada linha válida MUST ter `finished_at` (ISO), `job_id`, `pool_id` e `status`. Quando `status` é `FAILED`, MUST ter `reason` ∈ {`SPOT_INSTANCE_TERMINATION`, `TIMED_OUT`, `SPARK_EXECUTION_ERROR`}.

#### Scenario: Evento válido é aceito

- **WHEN** a linha é um JSON com os campos do enunciado e `reason` conhecido
- **THEN** o evento é persistido em `job_events`

#### Scenario: Linha malformada é descartada

- **WHEN** a linha não é JSON válido ou falta campo obrigatório
- **THEN** a linha é descartada e a carga continua com as demais

#### Scenario: Reason desconhecido é descartado

- **WHEN** `reason` não é um dos três valores do enunciado
- **THEN** a linha é descartada e a carga continua

### Requirement: finished_at naive é UTC

O parser SHALL tratar `finished_at` sem sufixo de timezone como UTC e MUST anexar timezone UTC explicitamente antes de persistir.

#### Scenario: Timestamp sem timezone vira UTC

- **WHEN** `finished_at` é `2024-08-07T00:04:52.767830`
- **THEN** o valor persistido é esse instante em UTC, não naive

### Requirement: Parse de pool_id sem split ingênuo

O parser SHALL extrair instance type e AZ de `pool_id` no formato `pool-<instance-type>-<az>`. O instance type MUST ser o token após o prefixo `pool-` até o próximo hífen (tipos contêm ponto, não hífen). O restante MUST ser a AZ (que contém hífens).

#### Scenario: Tipo com ponto e AZ com hífen

- **WHEN** `pool_id` é `pool-r6.xlarge-us-east-1c`
- **THEN** instance type é `r6.xlarge` e AZ é `us-east-1c`

#### Scenario: pool_id fora do padrão é descartado

- **WHEN** `pool_id` não começa com `pool-` ou não tem instance type e AZ separáveis por hífen após o prefixo
- **THEN** a linha é descartada e a carga continua

### Requirement: Carga do seed na subida

Na subida, se `job_events` estiver vazia, o sistema SHALL carregar `data/events.jsonl` (10_000 eventos com `finished_at` numa janela de 24 h, versionado no repositório). Se a tabela já tiver linhas, MUST NÃO recarregar o seed. SPARK_EXECUTION_ERROR MUST ser persistido quando a linha é válida.

#### Scenario: Tabela vazia recebe o seed

- **WHEN** a API sobe e `job_events` não tem linhas
- **THEN** as linhas válidas de `data/events.jsonl` são inseridas

#### Scenario: Tabela já populada não é reseedada

- **WHEN** a API sobe e `job_events` já tem linhas
- **THEN** o arquivo JSONL não é recarregado

#### Scenario: SPARK_EXECUTION_ERROR é persistido

- **WHEN** uma linha válida tem `reason` `SPARK_EXECUTION_ERROR`
- **THEN** o evento é gravado em `job_events`

### Requirement: Seed versionado de 10_000 eventos em 24 h

`data/events.jsonl` MUST ter 10_000 linhas válidas. O intervalo entre o menor e o maior `finished_at` MUST ser de no máximo 24 horas. O score MUST usar todos esses eventos (sem recortar por hora no GET).

#### Scenario: Arquivo de seed cabe em 24 h

- **WHEN** o parser lê `data/events.jsonl`
- **THEN** há 10_000 eventos e `max(finished_at) - min(finished_at) ≤ 24h`
