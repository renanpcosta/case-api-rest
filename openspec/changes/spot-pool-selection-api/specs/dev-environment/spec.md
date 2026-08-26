## ADDED Requirements

### Requirement: Ambiente completo em um único comando

O sistema SHALL subir o ambiente de desenvolvimento completo — API, worker agregador, store
durável, store de serving, object storage local e seeder de dados — com a execução de um
único comando, sem passos manuais intermediários.

#### Scenario: Subida em máquina limpa

- **WHEN** o comando único é executado em uma máquina sem estado prévio do projeto
- **THEN** todos os serviços sobem e ficam saudáveis sem intervenção manual

#### Scenario: Endpoint responde na porta acordada

- **WHEN** o ambiente está de pé
- **THEN** uma requisição a `http://localhost:5050/get-pools` responde 200 com payload válido

#### Scenario: Rota canônica também responde localmente

- **WHEN** o ambiente está de pé
- **THEN** uma requisição a `http://localhost:5050/get-pool` responde 200

#### Scenario: Segunda execução é idempotente

- **WHEN** o comando único é executado novamente com o ambiente já de pé
- **THEN** o comando conclui com sucesso e o endpoint continua respondendo

### Requirement: Dependências isoladas e reprodutíveis

O sistema SHALL instalar dependências de forma isolada do Python do sistema, com versões
travadas em arquivo de lock versionado no repositório.

#### Scenario: Instalação isolada

- **WHEN** as dependências são instaladas
- **THEN** elas ficam em ambiente virtual próprio do projeto e não no interpretador do sistema

#### Scenario: Lock respeitado

- **WHEN** a instalação é feita a partir do lock
- **THEN** as versões resolvidas são exatamente as travadas

#### Scenario: Piso de versão do Python respeitado

- **WHEN** a instalação é tentada em um interpretador abaixo do piso declarado
- **THEN** a instalação falha com mensagem explícita sobre a versão exigida

### Requirement: Ordem de subida por healthcheck

O sistema SHALL declarar dependências entre serviços por condição de saúde, de modo que a API
e o worker só iniciem após os stores estarem prontos, e o seeder só rode após o object
storage estar pronto.

#### Scenario: API aguarda os stores

- **WHEN** os stores ainda não estão saudáveis
- **THEN** a API não é iniciada antes deles

#### Scenario: Prontidão só após dado disponível

- **WHEN** o ambiente termina de subir e o seeder concluiu
- **THEN** a prontidão da API fica verde por existir snapshot utilizável

#### Scenario: Falha de healthcheck é visível

- **WHEN** um serviço não fica saudável dentro do tempo limite
- **THEN** o comando único falha com indicação de qual serviço não subiu

### Requirement: Gerador de eventos sintéticos

O sistema SHALL fornecer um gerador de dataset sintético capaz de produzir cenários
controlados — inclusive degradação de uma AZ em uma faixa horária e rajada de pico — com seed
fixa para reprodutibilidade.

#### Scenario: Cenário de degradação de AZ

- **WHEN** o gerador recebe a instrução de degradar uma AZ em uma faixa de horas
- **THEN** o dataset produzido concentra terminações spot nos pools daquela AZ dentro da faixa

#### Scenario: Reprodutibilidade

- **WHEN** o gerador é executado duas vezes com a mesma seed e os mesmos parâmetros
- **THEN** os datasets produzidos são idênticos

#### Scenario: Formato compatível com a ingestão

- **WHEN** o dataset gerado é carregado no object storage local
- **THEN** o worker o ingere sem eventos malformados

### Requirement: Teste de aceitação de replay de 24 horas

O sistema SHALL comprovar o comportamento do produto por um teste de aceitação que faz
replay de 24 horas sintéticas com degradação de uma AZ em uma faixa conhecida, com seed fixa.

#### Scenario: API para de recomendar a AZ degradada

- **WHEN** o replay atinge a faixa de degradação da AZ
- **THEN** a fração de recomendações para pools daquela AZ cai abaixo do limiar acordado

#### Scenario: API volta a considerar a AZ recuperada

- **WHEN** o replay avança além da faixa de degradação
- **THEN** pools daquela AZ voltam a ser recomendados

#### Scenario: Determinismo do teste

- **WHEN** o teste de aceitação é executado repetidamente com a mesma seed
- **THEN** o resultado é o mesmo

### Requirement: Verificação automatizada do ambiente de comando único

O sistema SHALL validar automaticamente na integração contínua que o ambiente sobe pelo
comando único e que o endpoint responde no endereço acordado com payload válido.

#### Scenario: Smoke test na integração contínua

- **WHEN** o pipeline executa o alvo de smoke
- **THEN** o ambiente é levantado, a requisição ao endereço acordado é feita e o payload é
  validado contra o contrato

#### Scenario: Falha do smoke bloqueia o pipeline

- **WHEN** o endpoint não responde ou o payload não casa o contrato
- **THEN** o pipeline falha com log dos serviços

### Requirement: Alvos de qualidade executáveis localmente

O sistema SHALL oferecer alvos de comando para lint, formatação, verificação de tipos, testes
e o próprio ambiente de dev, executando localmente na mesma ordem da integração contínua.

#### Scenario: Repositório sem código de negócio já passa nos alvos

- **WHEN** os alvos de lint e teste são executados sobre o scaffolding inicial
- **THEN** ambos concluem com sucesso

#### Scenario: Paridade com a integração contínua

- **WHEN** o alvo local de verificação é executado
- **THEN** ele roda as mesmas etapas, na mesma ordem, que o pipeline remoto

#### Scenario: Gates de cobertura aplicados

- **WHEN** a suíte de testes é executada com os gates habilitados
- **THEN** a execução falha se a cobertura global, a do domínio ou a do diff ficarem abaixo
  dos limiares acordados
