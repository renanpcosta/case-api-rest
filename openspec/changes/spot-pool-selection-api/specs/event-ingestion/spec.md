## ADDED Requirements

### Requirement: Ingestão fora do caminho do request

O sistema SHALL ingerir eventos por meio de um worker assíncrono desacoplado da API. O
caminho de atendimento de um request HTTP MUST NOT executar leitura no S3, na fila de
notificações ou qualquer varredura de eventos brutos.

#### Scenario: Request não toca o object storage

- **WHEN** um request chega no endpoint de recomendação
- **THEN** nenhuma chamada ao adapter de S3/SQS é executada durante o atendimento
- **AND** a resposta é montada exclusivamente a partir do snapshot de ranking e dos
  contadores de serving

#### Scenario: Worker é o único produtor de agregados

- **WHEN** o worker agregador está parado
- **THEN** a API continua respondendo a partir do último snapshot disponível
- **AND** apenas o frescor do dado degrada, sem erro no request

### Requirement: Origem dos eventos por ambiente

O sistema SHALL suportar duas origens de eventos atrás de um mesmo port: em produção, S3
Event Notifications entregando em SQS; em desenvolvimento, polling do bucket. A troca de
origem MUST ser configuração, não alteração de código de domínio ou de aplicação.

#### Scenario: Origem SQS em produção

- **WHEN** a configuração define a origem como SQS
- **THEN** o worker consome mensagens de notificação, extrai as chaves de objeto e processa
  cada objeto uma única vez
- **AND** a mensagem só é confirmada (deletada) após o commit do lote no store durável

#### Scenario: Origem por polling em dev

- **WHEN** a configuração define a origem como polling
- **THEN** o worker lista periodicamente o bucket e processa apenas as chaves ainda não
  registradas como ingeridas

### Requirement: Parsing de timestamp sem timezone

O sistema SHALL interpretar `finished_at` como UTC e anexar timezone UTC explicitamente no
parsing. Nenhum `datetime` naive MUST alcançar o cálculo de score, o cálculo de decaimento
ou a persistência.

#### Scenario: Timestamp sem sufixo de timezone

- **WHEN** um evento traz `finished_at` igual a `2024-08-07T00:04:52.767830`
- **THEN** o evento parseado carrega um datetime aware com `tzinfo` igual a UTC
- **AND** o instante representado é o mesmo valor numérico interpretado como UTC

#### Scenario: Timestamp com timezone explícito

- **WHEN** um evento traz `finished_at` já com sufixo de timezone (por exemplo `+00:00` ou `Z`)
- **THEN** o parser preserva o instante e normaliza a representação para UTC

#### Scenario: Datetime naive é rejeitado nas fronteiras internas

- **WHEN** um datetime naive é passado a uma função de decaimento ou de score
- **THEN** a função levanta erro em vez de assumir um timezone implícito

### Requirement: Parsing de pool_id

O sistema SHALL extrair `instance_type` e `availability_zone` de um `pool_id` removendo o
prefixo `pool-`, tomando como `instance_type` o primeiro token até o próximo hífen e como
`availability_zone` todo o restante. Split ingênuo por hífen MUST NOT ser usado.

#### Scenario: Pool id canônico

- **WHEN** o `pool_id` é `pool-r6.xlarge-us-east-1c`
- **THEN** o `instance_type` extraído é `r6.xlarge`
- **AND** a `availability_zone` extraída é `us-east-1c`

#### Scenario: AZ com múltiplos hífens

- **WHEN** o `pool_id` é `pool-m5.4xlarge-ap-southeast-2b`
- **THEN** o `instance_type` extraído é `m5.4xlarge`
- **AND** a `availability_zone` extraída é `ap-southeast-2b`

#### Scenario: Pool id fora do padrão

- **WHEN** o `pool_id` não começa com `pool-`, ou não tem hífen após o prefixo, ou tem
  `instance_type` ou AZ vazios
- **THEN** o parser sinaliza o valor como inválido em vez de produzir um pool parcial

### Requirement: Eventos malformados são descartados com contabilidade

O sistema SHALL descartar eventos inválidos sem falhar o processamento do objeto e SHALL
incrementar `malformed_events_total` rotulado pelo motivo do descarte, registrando log
estruturado. Descarte silencioso MUST NOT ocorrer.

#### Scenario: Linha que não é JSON válido

- **WHEN** uma linha do objeto não é JSON parseável
- **THEN** a linha é descartada, a métrica de malformados é incrementada com motivo de
  parse e as demais linhas do objeto continuam sendo processadas

#### Scenario: Campo obrigatório ausente

- **WHEN** um evento não tem `pool_id`, `job_id`, `finished_at` ou `status`
- **THEN** o evento é descartado e contabilizado como malformado

#### Scenario: Reason desconhecido

- **WHEN** um evento falho traz um `reason` fora do conjunto conhecido
- **THEN** o evento é descartado para fins de score e contabilizado como malformado
- **AND** o lote conclui com sucesso

#### Scenario: Objeto inteiro inválido não derruba o worker

- **WHEN** todas as linhas de um objeto são malformadas
- **THEN** o objeto é marcado como ingerido, as métricas refletem os descartes e o worker
  prossegue para o próximo objeto

### Requirement: Idempotência de ingestão em dois níveis

O sistema SHALL garantir que reprocessar o mesmo objeto ou o mesmo evento não altere os
agregados. A chave de idempotência de evento é `(job_id, finished_at, pool_id)` e a chave de
idempotência de objeto é a chave do objeto no bucket.

#### Scenario: Reprocessamento do mesmo objeto

- **WHEN** o mesmo objeto S3 é entregue duas vezes pela entrega at-least-once
- **THEN** os contadores agregados após o segundo processamento são idênticos aos de após o
  primeiro

#### Scenario: Evento duplicado dentro do mesmo objeto

- **WHEN** um objeto contém duas linhas com a mesma chave `(job_id, finished_at, pool_id)`
- **THEN** apenas uma ocorrência é persistida e contabilizada

#### Scenario: Duplicata entre objetos distintos

- **WHEN** o mesmo evento aparece em dois objetos diferentes
- **THEN** o upsert por chave de idempotência impede dupla contagem nos agregados

### Requirement: Agregação por bucket de tempo tolerante a desordem

O sistema SHALL agregar eventos em contadores por `(pool_id, bucket_start)` com bucket de
duração configurável (5 min por padrão), mantendo contadores por `reason` e contadores
adicionais por `(pool_id, bucket_start, job_id)` para viabilizar o cap por job. A agregação
MUST NOT depender da ordem de chegada dos eventos.

#### Scenario: Independência de ordem

- **WHEN** o mesmo conjunto de eventos é ingerido em duas ordens diferentes
- **THEN** os contadores agregados finais são idênticos

#### Scenario: Evento atrasado cai no bucket correto

- **WHEN** um evento com `finished_at` de 40 minutos atrás é ingerido agora
- **THEN** ele incrementa o bucket correspondente ao seu `finished_at`, não o bucket atual

#### Scenario: Contadores por reason

- **WHEN** um lote contém sucessos, terminações spot, timeouts e erros de execução do Spark
- **THEN** o agregado do bucket registra cada categoria em seu próprio contador

### Requirement: Publicação periódica do snapshot de ranking

O sistema SHALL recomputar o ranking completo de pools em intervalo configurável
(10–30 s) a partir dos agregados e SHALL publicar o resultado como um único blob serializado
no store de serving, carregando o instante de geração.

#### Scenario: Snapshot publicado após ciclo de recomputação

- **WHEN** um ciclo de recomputação termina
- **THEN** o snapshot no store de serving é substituído atomicamente por um novo blob
- **AND** o blob contém, para cada pool, score, bounds do intervalo de confiança, evidência
  da janela e o instante de geração

#### Scenario: Snapshot é derivado e reconstruível

- **WHEN** o store de serving é esvaziado
- **THEN** o ciclo seguinte de recomputação reconstrói o snapshot a partir dos agregados do
  store durável, sem reler o object storage

### Requirement: Retenção por particionamento

O sistema SHALL expurgar dados por DROP de partição diária, nunca por DELETE em massa,
respeitando as retenções configuradas: eventos 7 dias, agregados 30 dias, recomendações
30 dias, registro de objetos ingeridos 7 dias.

#### Scenario: Expurgo de partição vencida

- **WHEN** o worker executa a rotina de expurgo e existe partição mais antiga que a retenção
- **THEN** a partição é removida por DROP
- **AND** nenhuma instrução DELETE em massa é emitida

#### Scenario: Criação antecipada de partição

- **WHEN** a rotina de manutenção roda antes da virada do dia
- **THEN** a partição do dia seguinte já existe quando o primeiro evento dele é ingerido
