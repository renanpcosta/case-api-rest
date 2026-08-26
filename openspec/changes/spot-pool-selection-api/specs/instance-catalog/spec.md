## ADDED Requirements

### Requirement: Catálogo estático versionado

O sistema SHALL manter um catálogo de tipos de instância como arquivo estático versionado no
repositório, mapeando `instance_type` para família, categoria, vCPU e memória em GiB. O
catálogo MUST ser carregado na inicialização e MUST NOT exigir chamada externa em runtime.

#### Scenario: Carga na inicialização

- **WHEN** a aplicação inicia
- **THEN** o catálogo é carregado do arquivo versionado e validado
- **AND** nenhuma chamada de rede é feita para obter metadados de instância

#### Scenario: Catálogo inválido impede subida

- **WHEN** o arquivo de catálogo tem entrada sem categoria, vCPU ou memória
- **THEN** a inicialização falha com erro explícito em vez de subir com catálogo parcial

#### Scenario: Tipo desconhecido em evento

- **WHEN** um evento chega com tipo de instância ausente do catálogo
- **THEN** o evento é ingerido normalmente e o pool recebe a categoria indefinida, sem
  quebrar a agregação

### Requirement: Classificação por categoria e família

O sistema SHALL derivar a categoria do tipo de instância a partir da família, classificando
famílias `r`, `x` e `z` como memória, `c` como computação, `m` e `t` como uso geral, e `i` e
`d` como armazenamento.

#### Scenario: Família de memória

- **WHEN** o tipo de instância é `r6.xlarge`
- **THEN** a família é `r6` e a categoria é memória

#### Scenario: Família de computação

- **WHEN** o tipo de instância é `c5.2xlarge`
- **THEN** a família é `c5` e a categoria é computação

#### Scenario: Família de uso geral

- **WHEN** o tipo de instância é `m5.large`
- **THEN** a família é `m5` e a categoria é uso geral

### Requirement: Filtro por restrição de tipo de instância

O sistema SHALL permitir restringir os candidatos por categoria, lista de famílias, lista de
tipos de instância, mínimo de vCPU, mínimo de memória em GiB, lista de AZs permitidas e lista
de AZs excluídas. Todos os filtros SHALL ser opcionais e combináveis por conjunção.

#### Scenario: Job memory-bound

- **WHEN** o request restringe a categoria a memória
- **THEN** apenas pools de tipos de instância de categoria memória são candidatos

#### Scenario: Job cpu-bound

- **WHEN** o request restringe a categoria a computação
- **THEN** apenas pools de tipos de instância de categoria computação são candidatos

#### Scenario: Combinação de filtros

- **WHEN** o request restringe categoria a memória e mínimo de memória a 64 GiB
- **THEN** apenas pools que satisfazem as duas condições simultaneamente são candidatos

#### Scenario: Exclusão de AZ

- **WHEN** o request exclui uma AZ
- **THEN** nenhum pool daquela AZ é candidato, ainda que tenha o melhor score

#### Scenario: Precedência entre AZ permitida e excluída

- **WHEN** a mesma AZ aparece na lista de permitidas e na de excluídas
- **THEN** a exclusão prevalece e a AZ não é considerada

#### Scenario: Ausência de filtro considera todos os pools

- **WHEN** o request não informa nenhum filtro
- **THEN** todos os pools conhecidos são candidatos

### Requirement: Distinção entre filtro inválido e filtro vazio

O sistema SHALL rejeitar com erro de validação um parâmetro sintaticamente ou
semanticamente inválido, e SHALL rejeitar com erro de requisição um filtro válido que não
casa nenhum pool conhecido, deixando claro na mensagem qual restrição zerou o conjunto.

#### Scenario: Categoria inexistente

- **WHEN** o request informa uma categoria fora do domínio permitido
- **THEN** a resposta é erro de validação de parâmetro

#### Scenario: Mínimo de vCPU negativo

- **WHEN** o request informa mínimo de vCPU negativo
- **THEN** a resposta é erro de validação de parâmetro

#### Scenario: Tipo de instância ausente do catálogo

- **WHEN** o request restringe a um tipo de instância que não existe no catálogo
- **THEN** a resposta é erro de requisição indicando filtro logicamente vazio

#### Scenario: Combinação impossível

- **WHEN** o request combina categoria de memória com mínimo de vCPU maior que o maior tipo
  de memória do catálogo
- **THEN** a resposta é erro de requisição indicando filtro logicamente vazio

#### Scenario: Filtro casa o catálogo mas nenhum pool tem evidência

- **WHEN** o filtro casa tipos de instância do catálogo mas nenhum pool correspondente tem
  evidência
- **THEN** a resposta é bem-sucedida com prior e confiança baixa, e não erro
