## ADDED Requirements

### Requirement: Endpoint de recomendação e seus aliases

O sistema SHALL expor `GET /get-pool` como rota canônica, `GET /get-pools` como alias
visível na documentação e `GET /getpools` como alias oculto do schema. As três rotas SHALL
ter comportamento idêntico.

#### Scenario: Rota canônica responde

- **WHEN** um cliente chama `GET /get-pool`
- **THEN** a resposta é 200 com o payload de recomendação

#### Scenario: Alias visível responde e aparece no schema

- **WHEN** um cliente chama `GET /get-pools`
- **THEN** a resposta tem o mesmo formato da rota canônica
- **AND** a rota consta no documento OpenAPI

#### Scenario: Alias oculto responde sem poluir o schema

- **WHEN** um cliente chama `GET /getpools`
- **THEN** a resposta tem o mesmo formato da rota canônica
- **AND** a rota não consta no documento OpenAPI

### Requirement: Parâmetros de consulta do endpoint

O endpoint SHALL aceitar, todos opcionais e combináveis, os parâmetros `category`,
`families`, `instance_types`, `min_vcpu`, `min_memory_gib`, `az`, `exclude_az`, `job_id` e
`candidates`, validados por schema com mensagens e exemplos documentados no OpenAPI.

#### Scenario: Parâmetros de lista aceitam múltiplos valores

- **WHEN** o request informa múltiplas famílias
- **THEN** todas as famílias informadas são consideradas no filtro

#### Scenario: Tipo incorreto em parâmetro numérico

- **WHEN** o request informa um valor não inteiro em `min_vcpu`
- **THEN** a resposta é 422 no envelope de erro padrão

#### Scenario: Candidatos acima do máximo permitido

- **WHEN** o request pede um número de candidatos acima do limite configurado
- **THEN** a resposta é 422 no envelope de erro padrão

#### Scenario: job_id é registrado para telemetria

- **WHEN** o request informa `job_id`
- **THEN** a recomendação é persistida associada a esse `job_id` para fechamento do loop de
  efetividade

### Requirement: Resposta com explicabilidade

A resposta 200 SHALL conter `pool_id`, `instance_type`, `availability_zone`, `score`,
`confidence` entre alto, médio e baixo, `evidence` com minutos da janela, sucessos,
terminações spot e timeouts, `data_freshness_seconds`, `alternatives`, `policy` e `warnings`.
O modelo de resposta SHALL ser declarado explicitamente na rota.

#### Scenario: Payload completo

- **WHEN** uma recomendação é retornada com dado fresco
- **THEN** todos os campos do contrato estão presentes e tipados conforme o schema

#### Scenario: Consistência entre pool e seus atributos

- **WHEN** uma recomendação é retornada
- **THEN** `instance_type` e `availability_zone` correspondem ao `pool_id` retornado

#### Scenario: Frescor reportado

- **WHEN** o snapshot foi gerado há um intervalo conhecido
- **THEN** `data_freshness_seconds` reflete a idade do snapshot usado

#### Scenario: Estabilidade do schema

- **WHEN** o schema da resposta é comparado ao contrato versionado
- **THEN** nenhum campo obrigatório foi removido ou renomeado

### Requirement: Headers da resposta

O sistema SHALL responder com `Cache-Control: no-store`, dado que a resposta é estocástica, e
SHALL propagar ou gerar `X-Request-Id` em toda resposta.

#### Scenario: Resposta não é cacheável

- **WHEN** qualquer resposta do endpoint de recomendação é emitida
- **THEN** o header `Cache-Control` tem valor `no-store`

#### Scenario: Request id propagado

- **WHEN** o cliente envia `X-Request-Id`
- **THEN** a resposta devolve o mesmo valor

#### Scenario: Request id gerado

- **WHEN** o cliente não envia `X-Request-Id`
- **THEN** a API gera um identificador e o devolve no header

### Requirement: Envelope de erro único

Todos os erros SHALL usar um único envelope documentado contendo código, mensagem, detalhes e
o identificador do request. O endpoint MUST NOT responder 404 nem 5xx por ausência de dado.

#### Scenario: Erro de validação

- **WHEN** um parâmetro é inválido
- **THEN** a resposta é 422 no envelope padrão com o campo ofensor nos detalhes

#### Scenario: Filtro logicamente vazio

- **WHEN** o filtro é válido mas não casa nenhum pool do catálogo
- **THEN** a resposta é 400 no envelope padrão

#### Scenario: Ausência de dado não gera erro

- **WHEN** não existe nenhum agregado nem snapshot no sistema
- **THEN** a resposta é 200 com prior e confiança baixa, e não 404 nem 5xx

#### Scenario: Falha interna preserva o envelope

- **WHEN** ocorre uma exceção não tratada
- **THEN** a resposta segue o envelope padrão e o erro é logado com o `request_id`

### Requirement: Escada de degradação graciosa no caminho de leitura

O sistema SHALL atender o request a partir do snapshot no store de serving; na
indisponibilidade dele, a partir do último snapshot mantido em memória mesmo que velho; e na
ausência de ambos, a partir do prior estático por tipo de instância com alternância entre as
AZs conhecidas. Toda resposta SHALL declarar o nível de confiança e o frescor.

#### Scenario: Store de serving disponível

- **WHEN** o snapshot está disponível e fresco
- **THEN** a resposta usa o snapshot e reporta confiança conforme a evidência

#### Scenario: Store de serving indisponível

- **WHEN** o store de serving está fora do ar e existe snapshot em memória
- **THEN** a resposta é 200 servida do snapshot stale, com aviso e frescor refletindo a idade
  real

#### Scenario: Store durável indisponível

- **WHEN** o store durável está fora do ar
- **THEN** a API continua respondendo normalmente e apenas a atualização de agregados para

#### Scenario: Nenhum snapshot disponível

- **WHEN** não há snapshot no store de serving nem em memória
- **THEN** a resposta é 200 com política de prior de fallback, confiança baixa e aviso

#### Scenario: Prior alterna entre AZs

- **WHEN** múltiplos requests são atendidos pelo prior de fallback
- **THEN** as respostas alternam entre as AZs conhecidas do tipo de instância

### Requirement: Cache em processo no caminho de leitura

O sistema SHALL manter o snapshot em cache no processo com TTL curto configurável (1–5 s),
de modo que a maioria dos requests seja atendida sem I/O de rede.

#### Scenario: Requests consecutivos reutilizam o cache

- **WHEN** múltiplos requests chegam dentro da janela de TTL do cache
- **THEN** apenas a primeira leitura consulta o store de serving

#### Scenario: Expiração do TTL renova o snapshot

- **WHEN** o TTL do cache expira
- **THEN** o próximo request relê o snapshot do store de serving

### Requirement: Endpoints auxiliares de operação

O sistema SHALL expor `/health/live`, `/health/ready`, `/metrics` e `/version`. A prontidão
SHALL ficar verde apenas quando existir um snapshot utilizável.

#### Scenario: Liveness independe de dependências

- **WHEN** o processo está em execução mas o store de serving está fora
- **THEN** `/health/live` responde saudável

#### Scenario: Readiness exige snapshot utilizável

- **WHEN** nenhum snapshot utilizável existe ainda
- **THEN** `/health/ready` responde não pronto

#### Scenario: Readiness verde após primeiro snapshot

- **WHEN** o primeiro snapshot é publicado e lido pela API
- **THEN** `/health/ready` responde pronto

#### Scenario: Métricas e versão expostas

- **WHEN** `/metrics` e `/version` são chamados
- **THEN** o primeiro devolve as métricas em formato Prometheus e o segundo a versão e o
  identificador de build

### Requirement: Autenticação opcional desligada por padrão

O sistema SHALL manter a autenticação desligada por padrão, para não quebrar a validação por
`curl` do ambiente de comando único, e SHALL suportar exigência de header `X-API-Key`
habilitada por variável de ambiente.

#### Scenario: Padrão sem autenticação

- **WHEN** nenhuma chave é configurada
- **THEN** o request sem credencial é atendido normalmente

#### Scenario: Autenticação habilitada rejeita chave ausente

- **WHEN** a chave é configurada e o request não envia o header
- **THEN** a resposta é erro no envelope padrão sem revelar a chave esperada

#### Scenario: Autenticação habilitada aceita chave correta

- **WHEN** a chave é configurada e o request envia o header com o valor correto
- **THEN** o request é atendido normalmente

### Requirement: Documentação OpenAPI publicável

O sistema SHALL gerar documento OpenAPI com descrições e exemplos para todos os parâmetros e
respostas, e o documento SHALL ser exportável como artefato para publicação.

#### Scenario: Exportação do documento

- **WHEN** o comando de exportação do OpenAPI é executado
- **THEN** um documento JSON válido é produzido contendo o endpoint canônico, o alias visível
  e os endpoints auxiliares

#### Scenario: Exemplos presentes

- **WHEN** o documento OpenAPI é inspecionado
- **THEN** o endpoint de recomendação tem exemplo de request e de resposta
