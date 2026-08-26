# Project Context

## Purpose

API REST que responde, a qualquer instante, qual pool de instâncias EC2 spot tem a maior
probabilidade de um job Apache Spark terminar sem perder capacidade computacional,
respeitando restrições de tipo de instância (memory-bound vs cpu-bound).

Case técnico: "Desafio 02 - API REST para seleção de pools de instâncias".

## Glossário do domínio

- **POOL**: grupo de instâncias de um mesmo tipo em uma mesma AZ. Id no formato
  `pool-<instance-type>-<az>` (ex. `pool-r6.xlarge-us-east-1c`).
- **AZ**: zona de disponibilidade AWS.
- **SPOT**: instância barata e interruptível, retomável pela AWS a qualquer momento.
- **SCORE**: confiabilidade estimada de um pool (Wilson lower bound sobre sucessos vs
  terminações spot, com decaimento exponencial).
- **POOL DEGRADADO**: pool com evidência recente de terminações spot.
- **INFLIGHT**: recomendações emitidas para um pool nos últimos 60s.
- **COOLDOWN**: exclusão temporária de um pool do conjunto de candidatos.

## Dado de entrada

Arquivos `.json` em bucket S3, um evento JSON por linha (JSON Lines), chegando em tempo real.

```json
{"finished_at": "2024-08-07T00:04:52.767830", "job_id": "my-job",
 "pool_id": "pool-r6.xlarge-us-east-1c", "status": "FAILED",
 "reason": "SPOT_INSTANCE_TERMINATION"}
```

`reason` ∈ {`SPOT_INSTANCE_TERMINATION`, `TIMED_OUT`, `SPARK_EXECUTION_ERROR`}.

### Armadilhas do dado (cada uma é caso de teste obrigatório)

1. `finished_at` não tem sufixo de timezone mas é UTC — o parser anexa UTC explicitamente.
   Datetime naive vazando para o cálculo é bug silencioso.
2. `pool_id`: remover prefixo `pool-`; o instance type é o primeiro token até o próximo
   hífen (tipos contêm ponto, não hífen); todo o resto é a AZ (que contém hífens).
   Split ingênuo por hífen quebra.
3. Eventos malformados / `reason` desconhecido / `pool_id` fora do padrão: descartar sem
   falhar o batch, incrementando `malformed_events_total`. Nunca descartar em silêncio.
4. Entrega at-least-once: ingestão idempotente por `(job_id, finished_at, pool_id)`.
5. Só existe `finished_at` (não há `started_at` nem duração): a evidência é atribuída ao
   instante do término. Limitação conhecida, documentada em ADR.
6. Eventos podem chegar fora de ordem: contadores por bucket de tempo absorvem isso;
   nunca usar acumuladores dependentes de ordem.

## Requisitos do case (invariantes rastreáveis)

- **R1**: Python > 3.9; endpoint que devolve um pool id; aceita parâmetros para restringir
  tipos de instância (memória vs CPU).
- **R2**: framework livre, com racional documentado.
- **R3**: banco de dados livre (ou nenhum), com racional documentado.
- **R4**: alta disponibilidade e escalabilidade para picos imprevisíveis de jobs.
- **R5**: pronto para produção — ADRs, documentação do endpoint, CI/CD, testes unitários.
- **R6**: ambiente de dev sobe com UM comando, dependências isoladas, endpoint responde em
  `http://localhost:5050/get-pools`.
- **R7**: versionado em repositório remoto no github.com.

## Tech Stack (decisões travadas)

| Tema | Decisão |
|---|---|
| Python | `requires-python ">=3.10"`; ruff `target-version py310`; matriz CI 3.10/3.11/3.12; container 3.12 |
| Deps | uv + `pyproject.toml` + `uv.lock` |
| Framework | FastAPI + uvicorn |
| Store durável | PostgreSQL (SQLAlchemy 2.0 async + asyncpg, Alembic, particionado por dia) |
| Store de serving | Redis/Valkey (snapshot de ranking, inflight, cooldown) |
| S3 local | MinIO |
| Qualidade | ruff (lint+format) + mypy strict + pytest |
| Observabilidade | structlog (JSON) + prometheus-client |
| Infra | Docker Compose funcional + ADR 8 com inventário concreto de recursos e diagrama; sem IaC |
| CI/CD | GitHub Actions |

## Convenções

- **Arquitetura hexagonal**: `domain/` puro (não importa fastapi, sqlalchemy, redis, boto3);
  acesso a dado sempre por port (`Protocol`); direção de dependência única.
- **Zero literal mágico**: toda constante do algoritmo vive em settings (pydantic-settings).
- **RNG injetável**: nada de aleatoriedade global; seed fixa nos testes.
- **Piso de sintaxe 3.10**. Proibido: `asyncio.TaskGroup`, `ExceptionGroup`/`except*`,
  `datetime.UTC`, `StrEnum`, `tomllib`, `typing.Self`, `itertools.batched`, `@override`,
  generics PEP 695. Usar: `asyncio.gather`, `timezone.utc`, `class X(str, Enum)`, `tomli`,
  `typing_extensions`.
- **Logs**: structlog estruturado, nunca `print`. Sem `except` nu.
- **Conventional commits**; proibido force push.
- ADR obrigatório para nova dependência ou troca de store.
- **Links de documentação oficial vivem nos ADRs** (cada um linka a decisão e as alternativas
  descartadas) e no README, para onboarding. Este documento não carrega links: é contexto
  injetado a cada interação, e link aqui custa token e apodrece sem validação.

## Parâmetros fechados (não reabrir sem evidência de scoring-eval ou load test)

Toda constante abaixo é configuração (`pydantic-settings`), nunca literal no código. O formato
é: **nome** = valor — o que controla; efeito de mexer.

### Score

- **`W`** (janela) = **4h** — quanto de história entra no cálculo. É limite de *memória*, não
  de relevância: com meia-vida de 30 min, um evento de 4h atrás já pesa 0.004, então aumentar
  `W` não muda o ranking, só custa contador. Reduzir demais descarta a evidência de pool de
  baixo tráfego.
- **`h`** (meia-vida) = **30 min** — tempo para o peso de um evento cair à metade
  (`w = 0.5 ^ (idade / h)`). Governa a velocidade de reação do ranking de médio prazo. Menor
  reage mais rápido e oscila mais; maior é mais estável e mais lento a perceber degradação. A
  reação rápida a rajada é responsabilidade do cooldown, não deste parâmetro.
- **`bucket`** = **5 min** — granularidade do contador agregado, e portanto o erro máximo de
  datação de um evento. Menor dá mais precisão ao custo de mais linhas; maior borra o sinal. É
  também a janela natural do gatilho de cooldown.
- **`alpha`** (peso de `TIMED_OUT`) = **0.3** — fração com que um timeout conta como evidência
  de falha por spot. `TIMED_OUT` é o sinal *precoce* de degradação (o Spark recomputa partições
  e estoura o prazo) e `SPOT_INSTANCE_TERMINATION` é o *tardio*. Em 0 o sinal precoce é jogado
  fora; em 1 um timeout por culpa do job infla a falha do pool. **Pendente de medição.**
- **cap por `job_id`** = **25%** — teto da contribuição de um único job à massa de falha do
  pool na janela. Um job cronicamente quebrado estoura justamente no pool mais saudável (por
  ser o mais recomendado); sem cap ele degradaria exatamente o que funciona. Degradação real
  atinge muitos `job_id` distintos e passa intacta. Menor é mais robusto a job ruim e mais
  cego a degradação concentrada em poucos jobs; maior, o inverso.
- **nível de confiança do Wilson** = **95%** — quão conservador é o lower bound usado como
  score. Mais confiança significa intervalo mais largo, evidência escassa mais penalizada e
  conjunto elegível maior.
- `SPARK_EXECUTION_ERROR` entra com peso **0** (ignorado por completo): é atributo do job, não
  do pool.

### Seleção

- **`tau`** (temperatura do softmax) = **0.02** — converte diferença de score em razão de peso
  (`w ∝ exp(score / tau)`). Scores reais vivem em [0.80, 1.00]: com `tau` = 0.02 um gap de
  0.05 vira ~12x de preferência. Menor aproxima de argmax (traz a manada de volta); maior
  aproxima de uniforme (manda job para pool pior).
- **`K`** = **5** — teto do conjunto elegível. Limita o espalhamento quando muitos pools
  empatam estatisticamente; sem ele, uma frota nova (todos com intervalo largo) distribuiria
  carga por dezenas de pools medianos.
- **`epsilon`** = **0.02** — probabilidade de exploração direcionada. 2% dos requests vão ao
  pool de intervalo mais largo, para que pool sem evidência não fique congelado como ruim.
  Maior aprende mais rápido e paga mais jobs em pool pior.
- **`beta`** (penalidade de inflight) = **2**, janela de **60s** — força do freio da manada:
  peso ÷ (1 + `beta` × excesso de share). 0 desliga a penalidade; muito alto força distribuição
  uniforme independentemente do score. **Pendente de calibração.**

### Cooldown

- **gatilho** = **3 terminações spot em 5 min** OU **taxa ≥ 50% com ≥ 2 eventos** — o primeiro
  pega pool de tráfego normal; o segundo existe porque pool de baixo tráfego nunca chegaria a 3
  eventos e ficaria imune ao cooldown.
- **duração** = **10 min**, com **backoff 10/20/40** e **teto 60** — reincidência custa mais
  caro; o teto evita banir um pool por tempo indeterminado com base em evidência velha.
- **reset** = **1h limpa** — devolve o pool ao início da escada de backoff.
- **regra de segurança** — se o cooldown esvaziar os candidatos, ele é ignorado e a resposta é
  o melhor score com `confidence=low` e aviso. Zerar respostas transformaria degradação em
  indisponibilidade e violaria R4.

### Serving

- **intervalo de recomputação do ranking** = **10–30s** — de quanto em quanto tempo o worker
  repontua todos os pools e publica o snapshot. É o principal componente do frescor do dado.
- **TTL do cache em processo** = **1–5s** — quanto tempo a réplica reusa o snapshot sem ler o
  Redis. É o que faz a maioria dos requests não ter I/O de rede. O teto de 5s é uma ordem de
  magnitude menor que a duração mínima de cooldown, então não atrasa a reação de forma
  relevante.
- **TTL de inflight** = **60s** — janela de memória do contador de recomendações por pool,
  alinhada à janela de `beta`.

### Retenção

- **`job_events`** = **7 dias** — o S3 permanece como fonte histórica completa, então o
  Postgres só precisa da janela útil para reprocessamento e auditoria recente.
- **`pool_aggregates`** = **30 dias** — são baratos (~4M linhas) e habilitam avaliação offline
  sobre um mês inteiro sem reler o S3.
- **`recommendations`** = **30 dias** — viabiliza a métrica de efetividade (taxa de falha por
  spot dos jobs que rodaram nos pools recomendados).
- **`ingested_objects`** = **7 dias** — janela de dedupe no nível de arquivo, alinhada à de
  eventos.
- Tudo particionado por dia, com expurgo por **DROP de partição** — nunca DELETE em massa.

### Operação

- **autenticação** — desligada por default (ligar quebraria o `curl` de um comando de R6);
  header `X-API-Key` habilitado por env var. A defesa real em produção é topologia de rede.
- **SLOs** — p50 < 5ms, p99 < 25ms a 1k rps por réplica, alvo de 2k rps por réplica,
  disponibilidade 99.9%, frescor do dado p95 < 30s entre o evento chegar no S3 e refletir no
  ranking.
- **gates de qualidade** — cobertura global ≥ 85%, domínio ≥ 95%, diff ≥ 90% (impede código
  novo descoberto, que é o modo real de a cobertura apodrecer); mutation testing sobre
  `domain/scoring.py` como relatório não bloqueante.

Pendentes de **medição** (não de decisão), ambos tarefas da Fase 6: `alpha` (confirmar
0.0/0.3/0.5 via scoring-eval) e `beta` (calibrar pela distribuição em `pool_selection_total`
sob rajada).

## Anti-objetivos (recusar explicitamente)

**Escopo**: PySpark/Polars/DuckDB na ingestão; consultar S3/Athena no caminho do request;
Kafka; Kubernetes real; service mesh; frontend; autenticação complexa.

**Sintaxe**: qualquer construção indisponível em Python 3.10, ainda que o container rode 3.12
e a máquina de desenvolvimento rode mais que isso. A restrição não é redundante justamente
porque 3.10 nunca é o interpretador em uso: o piso `>=3.10` é uma promessa a quem instala o
pacote, e quem a mantém honesta é `mypy python_version = "3.10"` (pega uso de API de stdlib
inexistente no piso) mais a perna 3.10 da matriz de CI (pega o resto). A lista do
proibido/permitido está em Convenções.
