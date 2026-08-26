## ADDED Requirements

### Requirement: Seleção estocástica com RNG injetável

A política de seleção SHALL ser estocástica e MUST NOT ser um argmax do score. A fonte de
aleatoriedade SHALL ser injetada na política, nunca obtida de estado global, permitindo seed
fixa em teste.

#### Scenario: Seed fixa produz sequência reprodutível

- **WHEN** a política é executada duas vezes com a mesma seed e o mesmo snapshot
- **THEN** a sequência de pools escolhidos é idêntica

#### Scenario: Distribuição entre pools estatisticamente empatados

- **WHEN** múltiplos pools estão empatados estatisticamente e a política é executada muitas
  vezes
- **THEN** mais de um pool distinto é retornado ao longo das execuções

#### Scenario: Ausência de aleatoriedade global

- **WHEN** o módulo de política é inspecionado
- **THEN** não há uso de funções aleatórias de módulo global

### Requirement: Cooldown de pools com evidência aguda de terminação

O sistema SHALL colocar em cooldown um pool que apresente 3 ou mais terminações spot em uma
janela de 5 minutos, OU taxa de terminação maior ou igual a 50% nos últimos 5 minutos com no
mínimo 2 eventos. A duração base SHALL ser 10 minutos.

#### Scenario: Gatilho por contagem absoluta

- **WHEN** um pool acumula 3 terminações spot em 5 minutos
- **THEN** o pool entra em cooldown

#### Scenario: Gatilho por taxa em pool de baixo tráfego

- **WHEN** um pool registra 2 eventos em 5 minutos, sendo 1 terminação spot
- **THEN** o pool entra em cooldown por atingir a taxa mínima com o número mínimo de eventos

#### Scenario: Abaixo do gatilho não entra em cooldown

- **WHEN** um pool registra 2 terminações spot em 5 minutos entre 20 eventos
- **THEN** o pool não entra em cooldown

#### Scenario: Pool em cooldown é removido dos candidatos

- **WHEN** um pool está em cooldown e existem outros candidatos elegíveis
- **THEN** o pool em cooldown não é retornado nem listado como alternativa selecionável

### Requirement: Backoff exponencial e reset do cooldown

O sistema SHALL aplicar backoff exponencial na duração do cooldown em caso de reincidência,
seguindo 10, 20 e 40 minutos com teto de 60 minutos, e SHALL resetar o contador de
reincidência após um período limpo de 1 hora.

#### Scenario: Primeira reincidência dobra a duração

- **WHEN** um pool que já cumpriu cooldown dispara o gatilho novamente antes do reset
- **THEN** a nova duração é 20 minutos

#### Scenario: Duração respeita o teto

- **WHEN** as reincidências levariam a duração acima de 60 minutos
- **THEN** a duração aplicada é 60 minutos

#### Scenario: Reset após período limpo

- **WHEN** um pool passa 1 hora sem disparar o gatilho
- **THEN** o próximo cooldown volta a durar 10 minutos

### Requirement: Regra de segurança quando o cooldown esvazia os candidatos

Se a remoção de pools em cooldown esvaziar o conjunto de candidatos, o cooldown MUST ser
ignorado e o sistema SHALL retornar o pool de melhor score com confiança baixa, política
identificada como bypass de cooldown e um aviso na resposta. O sistema MUST NOT transformar
degradação em indisponibilidade.

#### Scenario: Todos os candidatos em cooldown

- **WHEN** todos os pools que passam o filtro de tipo de instância estão em cooldown
- **THEN** a resposta é bem-sucedida e devolve o pool de melhor score
- **AND** a confiança reportada é baixa, a política é bypass de cooldown e há aviso explícito

#### Scenario: Bypass não é acionado com candidato disponível

- **WHEN** existe ao menos um candidato fora de cooldown
- **THEN** a política não usa bypass

### Requirement: Conjunto elegível por sobreposição de intervalo de confiança

O sistema SHALL formar o conjunto elegível com os pools cujo Wilson upper bound é maior ou
igual ao Wilson lower bound do melhor pool, ordenados por score e limitados a um teto `K`
configurável (5 por padrão). Pools estatisticamente distinguíveis do melhor MUST NOT entrar
no conjunto.

#### Scenario: Evidência forte colapsa o conjunto

- **WHEN** um pool tem intervalo estreito e score claramente superior a todos os demais
- **THEN** o conjunto elegível contém apenas esse pool

#### Scenario: Evidência fraca abre o conjunto

- **WHEN** vários pools têm intervalos largos e sobrepostos
- **THEN** o conjunto elegível contém múltiplos pools

#### Scenario: Pool pior é excluído

- **WHEN** um pool tem upper bound abaixo do lower bound do melhor pool
- **THEN** esse pool não entra no conjunto elegível

#### Scenario: Teto K respeitado

- **WHEN** mais de `K` pools satisfazem a sobreposição
- **THEN** apenas os `K` de maior score compõem o conjunto elegível

### Requirement: Peso por softmax com temperatura

O sistema SHALL atribuir a cada pool do conjunto elegível um peso proporcional a
`exp(score / tau)`, com temperatura `tau` configurável (0.02 por padrão), de modo que
diferenças pequenas na faixa realista de scores produzam razões de peso significativas.

#### Scenario: Gap pequeno gera razão de peso relevante

- **WHEN** dois pools têm scores 0.95 e 0.90 e `tau` é 0.02
- **THEN** a razão entre seus pesos é superior a 10

#### Scenario: Empate exato gera pesos iguais

- **WHEN** dois pools têm scores idênticos
- **THEN** seus pesos são iguais

#### Scenario: Estabilidade numérica

- **WHEN** os scores levariam a exponenciais de grande magnitude
- **THEN** a implementação normaliza os expoentes e não produz overflow

#### Scenario: Temperatura é configuração

- **WHEN** `tau` é alterado por configuração
- **THEN** a concentração dos pesos muda sem alteração de código

### Requirement: Penalidade de inflight contra efeito manada

O sistema SHALL dividir o peso de cada pool por `1 + beta * excesso_de_share`, onde o excesso
é a fração de recomendações do pool nos últimos 60 segundos acima do seu share justo, com
`beta` configurável (2 por padrão). O contador de inflight SHALL viver no store de serving
com TTL.

#### Scenario: Pool sobre-recomendado é penalizado

- **WHEN** um pool detém share de recomendações acima do seu share justo na janela de 60s
- **THEN** seu peso é reduzido proporcionalmente ao excesso e a `beta`

#### Scenario: Pool dentro do share justo não é penalizado

- **WHEN** o share observado de um pool é menor ou igual ao seu share justo
- **THEN** nenhuma penalidade é aplicada ao seu peso

#### Scenario: Contador de inflight expira

- **WHEN** 60 segundos passam sem novas recomendações para um pool
- **THEN** o contador de inflight desse pool expira e a penalidade desaparece

#### Scenario: Rajada distribui carga

- **WHEN** um grande volume de requests idênticos é atendido em poucos segundos
- **THEN** as recomendações se distribuem entre os pools do conjunto elegível em vez de
  concentrar todas no melhor pool

### Requirement: Exploração direcionada

Com probabilidade `epsilon` configurável (0.02 por padrão), o sistema SHALL escolher, entre
os pools que passam o filtro e não estão em cooldown, o pool com o intervalo de confiança
mais largo — isto é, aquele com evidência mais escassa ou mais antiga — em vez de sortear
uniformemente. Pools em cooldown MUST ficar fora da exploração.

#### Scenario: Exploração escolhe o intervalo mais largo

- **WHEN** o sorteio determina exploração
- **THEN** o pool retornado é o de intervalo de confiança mais largo entre os candidatos
- **AND** a política reportada é exploração

#### Scenario: Exploração não escolhe pool em cooldown

- **WHEN** o pool de intervalo mais largo está em cooldown e há outros candidatos
- **THEN** ele não é escolhido pela exploração

#### Scenario: Frequência de exploração

- **WHEN** a política é executada muitas vezes com `epsilon` configurado
- **THEN** a fração de respostas com política de exploração aproxima `epsilon`

#### Scenario: Pool congelado volta a ser avaliado

- **WHEN** um pool deixa de receber eventos por um longo período
- **THEN** seu intervalo de confiança alarga e ele passa a ser candidato prioritário da
  exploração

### Requirement: Amostragem ponderada e política reportada

O sistema SHALL sortear o pool final no conjunto elegível por amostragem ponderada pelos
pesos ajustados e SHALL reportar qual política produziu a resposta entre seleção ponderada,
exploração, prior de fallback e bypass de cooldown.

#### Scenario: Amostragem respeita os pesos

- **WHEN** a política é executada um número grande de vezes sobre o mesmo conjunto elegível
- **THEN** a frequência empírica de cada pool aproxima seu peso normalizado

#### Scenario: Política identificada na resposta

- **WHEN** uma recomendação é produzida
- **THEN** a resposta declara exatamente uma das políticas possíveis

### Requirement: Alternativas ranqueadas

O sistema SHALL, quando solicitado, retornar as alternativas ranqueadas ao pool escolhido,
cada uma com seu score e confiança, para permitir depuração da decisão pelo time de
plataforma.

#### Scenario: Alternativas solicitadas

- **WHEN** o request pede um número de candidatos maior que zero
- **THEN** a resposta inclui até esse número de alternativas ordenadas por score
- **AND** o pool escolhido não é duplicado dentro das alternativas

#### Scenario: Alternativas não solicitadas

- **WHEN** o request não pede candidatos
- **THEN** a lista de alternativas vem vazia
