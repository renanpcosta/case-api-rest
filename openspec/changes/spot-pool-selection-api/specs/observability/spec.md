## ADDED Requirements

### Requirement: Logs estruturados correlacionados

O sistema SHALL emitir logs em JSON estruturado com `request_id` correlacionando todos os
eventos de log de um mesmo request. O uso de `print` MUST NOT ocorrer no código de aplicação.

#### Scenario: Log de request carrega correlação

- **WHEN** um request é atendido
- **THEN** todas as linhas de log geradas por ele contêm o mesmo `request_id`

#### Scenario: Log é JSON parseável

- **WHEN** uma linha de log é emitida
- **THEN** ela é um objeto JSON válido com timestamp, nível, evento e contexto

#### Scenario: Decisão de seleção é auditável

- **WHEN** uma recomendação é emitida
- **THEN** o log registra o pool escolhido, a política aplicada, o tamanho do conjunto
  elegível e o frescor do dado

### Requirement: Métricas Prometheus do caminho de leitura

O sistema SHALL expor histograma de latência do endpoint e o contador
`pool_selection_total` rotulado por `pool_id`, que evidencia a distribuição de carga e a
ausência de efeito manada.

#### Scenario: Latência observada por request

- **WHEN** requests são atendidos
- **THEN** o histograma de latência registra as observações com os buckets configurados

#### Scenario: Distribuição de seleção observável

- **WHEN** muitos requests são atendidos sobre um conjunto elegível com múltiplos pools
- **THEN** `pool_selection_total` mostra incrementos em mais de um `pool_id`

#### Scenario: Métrica calibra a penalidade de inflight

- **WHEN** o teste de carga em rajada é executado
- **THEN** a distribuição observada em `pool_selection_total` permite avaliar o valor de
  `beta`

### Requirement: Métricas Prometheus do caminho de escrita e de degradação

O sistema SHALL expor `aggregate_staleness_seconds`, `consumer_lag`,
`malformed_events_total`, `cooldown_active` rotulado por `pool_id` e `fallback_used_total`
rotulado pelo nível da escada de degradação.

#### Scenario: Staleness cresce com o agregador parado

- **WHEN** o worker agregador para de publicar snapshots
- **THEN** `aggregate_staleness_seconds` cresce monotonicamente

#### Scenario: Malformados contabilizados por motivo

- **WHEN** eventos inválidos são descartados
- **THEN** `malformed_events_total` é incrementado com o rótulo do motivo

#### Scenario: Cooldown observável

- **WHEN** um pool entra e depois sai de cooldown
- **THEN** `cooldown_active` reflete o estado de cada transição

#### Scenario: Nível de fallback contabilizado

- **WHEN** uma resposta é servida de snapshot stale ou de prior
- **THEN** `fallback_used_total` é incrementado no rótulo correspondente ao nível usado

### Requirement: Métrica de efetividade da recomendação

O sistema SHALL persistir cada recomendação emitida com `request_id`, `job_id`, `pool_id`,
score, política e instante, de modo a permitir medir ao longo do tempo a taxa de falha por
terminação spot dos jobs que rodaram nos pools recomendados. Esta é a métrica que atesta se o
sistema funciona.

#### Scenario: Recomendação persistida

- **WHEN** uma recomendação é emitida com `job_id` informado
- **THEN** um registro é gravado com todos os campos do contrato de telemetria

#### Scenario: Fechamento do loop por junção com eventos

- **WHEN** eventos de término são ingeridos após recomendações registradas
- **THEN** é possível calcular por consulta a taxa de terminação spot dos jobs recomendados

#### Scenario: Persistência de telemetria não bloqueia a resposta

- **WHEN** a gravação da recomendação falha
- **THEN** a resposta ao cliente é emitida normalmente e a falha é logada

### Requirement: Avaliação offline do algoritmo

O sistema SHALL permitir replay de um dataset de eventos contra configurações alternativas de
score e de política, produzindo comparação entre elas, sem necessidade de reler o object
storage.

#### Scenario: Comparação de valores de alpha

- **WHEN** o replay é executado com `alpha` em 0.0, 0.3 e 0.5 sobre o mesmo dataset
- **THEN** uma tabela comparativa das métricas resultantes é produzida por configuração

#### Scenario: Replay é determinístico

- **WHEN** o replay é executado duas vezes com a mesma seed e o mesmo dataset
- **THEN** os resultados são idênticos

### Requirement: Objetivos de nível de serviço declarados

O sistema SHALL declarar e verificar por medição os objetivos de latência p50 abaixo de 5 ms
e p99 abaixo de 25 ms a 1000 requisições por segundo por réplica, vazão alvo de 2000
requisições por segundo por réplica, disponibilidade de 99,9% e frescor do dado com p95
abaixo de 30 segundos entre a chegada do evento e seu reflexo no ranking.

#### Scenario: Cenário estável

- **WHEN** o perfil de carga estável a 500 requisições por segundo é executado
- **THEN** as latências medidas p50 e p99 são registradas e comparadas aos objetivos

#### Scenario: Cenário de rajada

- **WHEN** a carga sobe de 0 a 3000 requisições por segundo em 10 segundos
- **THEN** o sistema continua respondendo sem erro e os números medidos são registrados

#### Scenario: Cenário de soak

- **WHEN** o perfil de carga é sustentado por 30 minutos
- **THEN** o consumo de memória é registrado e não apresenta crescimento contínuo

#### Scenario: Relatório com números medidos

- **WHEN** o relatório de carga é escrito
- **THEN** ele contém valores medidos de p50, p99 e vazão, e não estimativas
