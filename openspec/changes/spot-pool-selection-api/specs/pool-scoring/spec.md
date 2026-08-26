## ADDED Requirements

### Requirement: Score é puro e determinístico

O cálculo do score SHALL residir no domínio, sem importar framework web, ORM, cliente de
cache ou SDK de nuvem, e SHALL ser função determinística dos eventos agregados e do instante
de referência recebido como parâmetro. O domínio MUST NOT ler o relógio global.

#### Scenario: Domínio sem dependência de infraestrutura

- **WHEN** os módulos de domínio são inspecionados por seus imports
- **THEN** não há import de fastapi, sqlalchemy, redis ou boto3

#### Scenario: Instante de referência injetado

- **WHEN** o mesmo agregado é pontuado duas vezes com o mesmo instante de referência
- **THEN** o score resultante é bit-a-bit igual

### Requirement: Decaimento exponencial por meia-vida

O sistema SHALL ponderar cada evento por `w = 0.5 ^ ((agora - finished_at) / h)`, com
meia-vida `h` configurável (30 min por padrão), considerando apenas eventos dentro da janela
`W` configurável (4 h por padrão).

#### Scenario: Evento no instante de referência

- **WHEN** um evento tem `finished_at` igual ao instante de referência
- **THEN** seu peso é 1.0

#### Scenario: Evento com uma meia-vida de idade

- **WHEN** um evento tem 30 minutos de idade e a meia-vida configurada é 30 minutos
- **THEN** seu peso é 0.5

#### Scenario: Peso é monotonicamente decrescente na idade

- **WHEN** dois eventos têm idades diferentes
- **THEN** o evento mais antigo tem peso estritamente menor

#### Scenario: Evento fora da janela é ignorado

- **WHEN** um evento tem idade maior que a janela configurada
- **THEN** ele não contribui para o score

### Requirement: Tratamento por motivo de falha

O sistema SHALL compor a massa de sucesso `S_p` com o peso dos eventos de sucesso e a massa
de falha `F_p` com o peso das terminações spot somado a `alpha` vezes o peso dos timeouts.
Eventos de erro de execução do Spark MUST ser ignorados por completo, pois são atribuíveis
ao job e não ao pool.

#### Scenario: Erro de execução do Spark não afeta o pool

- **WHEN** um pool recebe apenas sucessos e eventos de erro de execução do Spark
- **THEN** o score é idêntico ao de um pool com os mesmos sucessos e nenhum evento de erro

#### Scenario: Timeout entra com peso alpha

- **WHEN** `alpha` é 0.3 e um pool tem um único timeout de peso 1.0 na janela
- **THEN** a contribuição desse evento para a massa de falha é 0.3

#### Scenario: Terminação spot entra com peso integral

- **WHEN** um pool tem uma única terminação spot de peso 1.0 na janela
- **THEN** a contribuição desse evento para a massa de falha é 1.0

#### Scenario: Alpha é configuração

- **WHEN** `alpha` é alterado por configuração
- **THEN** o score reflete o novo valor sem alteração de código

### Requirement: Cap de contribuição de falha por job

O sistema SHALL limitar a contribuição de um único `job_id` a uma fração configurável (25%
por padrão) da massa de falha do pool na janela, de modo que um job cronicamente lento ou
quebrado não degrade o pool que a API mais recomenda.

#### Scenario: Job único concentrando falhas

- **WHEN** todas as falhas de um pool na janela vêm do mesmo `job_id`
- **THEN** a massa de falha considerada é limitada ao cap configurado
- **AND** o score fica estritamente maior que o score calculado sem cap

#### Scenario: Degradação real passa pelo cap

- **WHEN** as falhas de um pool estão distribuídas entre muitos `job_id` distintos, nenhum
  acima do cap
- **THEN** a massa de falha é preservada integralmente

#### Scenario: Cap não afeta a massa de sucesso

- **WHEN** um único `job_id` concentra os sucessos de um pool
- **THEN** nenhuma redução é aplicada à massa de sucesso

### Requirement: Wilson lower e upper bound

O sistema SHALL calcular o score do pool como o Wilson lower bound de nível de confiança
configurável (95% por padrão) sobre a proporção `S_p / (S_p + F_p)`, e SHALL preservar
também o upper bound para uso pela política de seleção.

#### Scenario: Score dentro do intervalo unitário

- **WHEN** qualquer combinação não negativa de massas de sucesso e falha é pontuada
- **THEN** o score e ambos os bounds estão em `[0, 1]`

#### Scenario: Ordenação dos bounds

- **WHEN** um pool é pontuado
- **THEN** o lower bound é menor ou igual ao upper bound

#### Scenario: Evidência escassa perde de evidência forte

- **WHEN** um pool tem 1 sucesso e 0 falhas e outro tem 950 sucessos e 50 falhas
- **THEN** o score do pool com evidência forte é maior que o do pool com evidência escassa

#### Scenario: Monotonicidade em sucessos

- **WHEN** a massa de sucesso de um pool aumenta e a de falha permanece igual
- **THEN** o score não diminui

#### Scenario: Monotonicidade em falhas

- **WHEN** a massa de falha de um pool aumenta e a de sucesso permanece igual
- **THEN** o score não aumenta

#### Scenario: Largura do intervalo diminui com evidência

- **WHEN** dois pools têm a mesma proporção de sucesso mas massas totais diferentes
- **THEN** o pool com massa total maior tem intervalo de confiança mais estreito

### Requirement: Prior para pool sem evidência

O sistema SHALL atribuir a pools sem evidência na janela um prior derivado do tipo de
instância e, na ausência dele, um prior global, marcando o resultado como de baixa
confiança.

#### Scenario: Pool novo com prior do tipo de instância

- **WHEN** um pool sem eventos na janela é pontuado e existem outros pools do mesmo tipo de
  instância com evidência
- **THEN** o score deriva do prior do tipo de instância
- **AND** o pool é marcado como de baixa confiança

#### Scenario: Prior global como último recurso

- **WHEN** não existe evidência alguma para o tipo de instância do pool
- **THEN** o prior global configurado é usado

#### Scenario: Prior nunca produz confiança alta

- **WHEN** um score vem de prior
- **THEN** o nível de confiança reportado não é alto

### Requirement: Nível de confiança e frescor derivados da evidência

O sistema SHALL classificar a confiança de cada pool em alto, médio ou baixo a partir da
massa total de evidência e da largura do intervalo, e SHALL expor a evidência que sustentou o
score: minutos da janela, sucessos, terminações spot e timeouts.

#### Scenario: Evidência abundante gera confiança alta

- **WHEN** a massa total de evidência de um pool excede o limiar configurado de confiança alta
- **THEN** o pool é reportado com confiança alta

#### Scenario: Evidência exposta na saída

- **WHEN** um pool é pontuado
- **THEN** o resultado carrega a contagem de sucessos, terminações spot e timeouts da janela
  e o tamanho da janela em minutos

### Requirement: Recomputação completa do ranking

O sistema SHALL recomputar o ranking de todos os pools conhecidos a cada ciclo, em vez de
manter acumuladores incrementais dependentes de ordem, dado que a ordem de grandeza
(centenas de pools por dezenas de buckets) torna a recomputação total trivial.

#### Scenario: Recomputação total por ciclo

- **WHEN** um ciclo de ranking é executado
- **THEN** todos os pools com agregados na janela são repontuados a partir dos contadores

#### Scenario: Ausência de acumulador dependente de ordem

- **WHEN** os agregados são apresentados ao ranking em ordens diferentes
- **THEN** o ranking resultante é o mesmo
