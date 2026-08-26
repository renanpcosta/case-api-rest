## Context

O repositório é greenfield: apenas `README.md` e commit inicial. Não há sistema legado, dado
de produção nem contrato a preservar, o que significa que todo o risco está em decisões de
design, não em migração.

O problema tem uma assimetria importante: o **enunciado é fácil** ("um endpoint que devolve
um pool id") e o **valor está escondido** em quatro armadilhas de modelagem que uma taxa
média de sucesso por pool não resolve:

1. **Sinal enviesado por motivo.** `SPARK_EXECUTION_ERROR` é culpa do job. Se entrar no score,
   um job com bug envenena a reputação de uma AZ saudável.
2. **Evidência escassa.** Um pool com 1 sucesso tem taxa 100% e venceria um pool com 950/1000.
3. **Efeito manada / profecia autorrealizável.** Se a API devolve sempre o melhor pool, no
   pico todos os jobs vão para lá e esgotam a capacidade que motivou a escolha — a API causa a
   falha que deveria evitar.
4. **Loop de feedback fechado.** Um pool nunca recomendado nunca gera evento e fica congelado
   como "ruim" para sempre.

Restrições dadas: a única evidência é o histórico de términos de job em S3 (JSON Lines,
tempo real, entrega at-least-once); o dado tem `finished_at` sem timezone, `pool_id` que
quebra em split ingênuo por hífen, e **não tem** `started_at` nem duração; o ambiente de dev
precisa subir em um comando; e o sistema precisa aguentar picos imprevisíveis.

Todas as decisões de stack e todos os parâmetros do algoritmo estão travados em
`openspec/project.md`. Este documento explica **por que** cada uma é assim e como as peças se
encaixam.

## Goals / Non-Goals

**Goals:**

- Produzir uma recomendação de pool estatisticamente defensável e **explicável** — o time de
  plataforma precisa poder depurar "por que esse pool?" a partir da própria resposta.
- Tratar as quatro armadilhas acima explicitamente, cada uma com mecanismo próprio e teste
  que o comprova.
- Manter o caminho do request sem I/O de rede na maioria dos casos e **nunca** devolver 5xx
  ou 404 por ausência de dado: degradação graciosa em três níveis.
- Absorver as seis armadilhas do dado no adapter de ingestão, de forma que o domínio receba
  apenas eventos válidos, com datetime aware, e agregados independentes de ordem.
- Rastreabilidade completa: cada um dos 7 requisitos do case mapeia para uma fase, um
  artefato e um teste que o comprova.
- Prontidão para produção demonstrada por artefato (ADRs, CI/CD, observabilidade, runbook,
  números de carga medidos), não por afirmação.

**Non-Goals:**

- IaC e cluster Kubernetes real. O executável é Docker Compose, verificado pelo smoke test do
  CI; a topologia de produção é entregue como **documentação verificável** no ADR 8 (diagrama
  mais inventário concreto de recursos com sua configuração), e não como código nunca
  aplicado. IaC que nunca roda `apply` não é infraestrutura: não pode ser provada, abre flanco
  em revisão e consome o tempo que pertence ao algoritmo.
- Processamento distribuído na ingestão (PySpark/Polars/DuckDB). O volume é incremental por
  objeto; `json.loads` linha a linha resolve. Usar Spark para processar logs do Spark é
  complexidade sem retorno.
- Consulta a S3/Athena no caminho do request, Kafka, service mesh, frontend, autenticação
  complexa.
- Qualquer sintaxe Python acima de 3.10, mesmo rodando em container 3.12.
- Previsão de disponibilidade spot (modelo de série temporal, ML). O escopo é estimar
  confiabilidade a partir da evidência observada, não prever o futuro da AWS.

## Decisions

### D1. Separação de caminhos: escrita assíncrona, leitura sem I/O

**Decisão.** Dois caminhos independentes.

*Escrita (fora do request):* S3 → (prod: S3 Event Notifications → SQS; dev: polling) → worker
agregador → upsert idempotente no Postgres → recomputação do ranking a cada 10–30 s →
snapshot serializado no Redis.

*Leitura (o request):* 1 leitura do snapshot no Redis + cache em processo com TTL de 1–5 s →
filtro por catálogo → política de seleção → resposta.

**Por quê.** É a condição necessária para R4. Se o request tocasse o S3, a latência ficaria
atrelada à latência do object storage e o pico de jobs viraria pico de chamadas ao S3 — o
oposto de escalabilidade. Com snapshot + cache em processo, a maioria dos requests não faz
nenhum I/O de rede, e escalar horizontalmente é adicionar réplicas stateless.

**Alternativas.** *Query-on-read* no Postgres a cada request: simples, mas coloca o banco no
caminho crítico e o transforma em ponto único de falha, quebrando a promessa de HA.
*Recálculo incremental* em vez de recomputação total: 500 pools × 48 buckets ≈ 24k
contadores — recomputar tudo é trivial e elimina toda uma classe de bug de acumulador
dessincronizado.

### D2. Dois stores, com papéis distintos

**Decisão.** PostgreSQL como store durável; Redis/Valkey como store de serving.

**Por quê.** Não é redundância, são funções diferentes. O Postgres guarda o que precisa de
integridade e história: eventos deduplicados por chave de idempotência, agregados por bucket,
e o histórico de recomendações — que é o que viabiliza a **métrica de efetividade** (a taxa de
falha por spot dos jobs que rodaram nos pools que a API recomendou) e a avaliação offline por
SQL. O Redis guarda dado **derivado e reconstruível**: o snapshot de ranking, os contadores de
inflight e as flags de cooldown, todos com TTL, servidos em sub-ms.

Essa divisão é também o argumento de HA: **se o Postgres cair, a API continua servindo** (só o
agregador para de avançar); **se o Redis cair, a API serve o snapshot stale da memória**. Um
store único não permitiria isso.

**Alternativas.** Só Postgres: perde a latência sub-ms e coloca o banco no caminho crítico.
Só Redis: perde durabilidade, história de recomendações e a avaliação offline. Nenhum store
(tudo em memória): impossível compartilhar estado entre réplicas — inflight e cooldown
precisam ser globais para que a penalidade de manada funcione com N réplicas.

### D3. Score: Wilson lower bound com decaimento, filtro por motivo e cap por job

**Decisão.** Para cada pool `p`, com meia-vida `h` = 30 min e janela `W` = 4 h:

- peso do evento: `w = 0.5 ^ ((agora − finished_at) / h)`
- `S_p` = soma dos `w` dos sucessos
- `F_p` = soma dos `w` das terminações spot + `alpha` × soma dos `w` dos timeouts
- `SPARK_EXECUTION_ERROR` é **ignorado por completo**
- cap por job: um único `job_id` contribui no máximo 25% da massa de `F_p`
- `score_p` = Wilson lower bound 95% de `S_p / (S_p + F_p)`; o upper bound é preservado
- pool sem evidência: prior do tipo de instância; na falta, prior global

**Por que Wilson e não média.** Wilson penaliza incerteza pelo tamanho da amostra: resolve a
armadilha 2 diretamente — 1 sucesso em 1 tentativa produz lower bound baixo, 950 em 1000
produz lower bound alto. E o intervalo que ele produz é reaproveitado de graça pela política
de seleção (D4) e pela exploração.

**Por que ignorar `SPARK_EXECUTION_ERROR`.** É a armadilha 1. Erro de execução é atributo do
job, não do pool. Incluí-lo faria um job com bug rodando em uma AZ saudável rebaixar aquela
AZ para todos os outros jobs.

**Por que `alpha` = 0.3 e não 0.** Perda de executores spot geralmente **não** faz o job
falhar: o Spark recomputa partições, o job fica mais lento e estoura o timeout. Ou seja,
`TIMED_OUT` é o sinal **precoce** de degradação e `SPOT_INSTANCE_TERMINATION` é o sinal
**tardio** (perda catastrófica). Descartar timeouts jogaria fora o sinal antecipado;
tratá-los como terminação confirmada inflaria falha por causas não relacionadas a spot. 0.3 é
o ponto de partida, a ser confirmado empiricamente contra 0.0 e 0.5 na Fase 6.

**Por que o cap por job.** Um job cronicamente lento ou quebrado sempre estoura no pool que a
API recomendou — isto é, **no pool mais saudável**. Sem o cap, ele degrada exatamente o que
funciona, e o sistema se auto-sabota. Degradação real de capacidade atinge muitos `job_id`
distintos e passa pelo cap intacta: o cap discrimina "um job ruim" de "um pool ruim".

**Por que `h` = 30 min é aceitável.** O score governa o ranking de médio prazo; a reação
rápida a rajadas é responsabilidade do cooldown (D4). Os dois mecanismos operam em escalas de
tempo complementares e por isso coexistem — não são redundantes.

### D4. Seleção estocástica, não argmax

**Decisão.** Dado o conjunto que passa o filtro de tipo de instância:

1. **Remover pools em cooldown.** Gatilho: 3+ terminações spot no mesmo pool em 5 min, OU
   taxa de terminação ≥ 50% nos últimos 5 min com ≥ 2 eventos (pega pool de baixo tráfego).
   Duração 10 min, backoff 10/20/40 com teto 60 em reincidência, reset após 1 h limpa.
   **Regra de segurança:** se o cooldown esvaziar o conjunto, ele é **ignorado** e a API
   devolve o melhor score com `confidence=low` e aviso.
2. **Conjunto elegível por sobreposição de IC.** Elegível é todo pool cujo Wilson *upper*
   bound ≥ Wilson *lower* bound do melhor pool (empate estatístico), limitado a `K` = 5.
3. **Peso por softmax com temperatura:** `w ∝ exp(score / tau)`, `tau` = 0.02.
4. **Penalidade de inflight:** dividir o peso por `1 + beta × excesso_de_share`, onde o
   excesso é a fração de recomendações do pool nos últimos 60 s acima do seu share justo.
5. **Exploração direcionada:** com probabilidade `epsilon` = 0.02, escolher o pool com o
   intervalo de confiança **mais largo**, não um pool uniformemente aleatório.
6. **Amostragem ponderada** no conjunto elegível.

**Por que não argmax.** É a armadilha 3. Argmax concentra 100% dos jobs no mesmo pool; no
pico, isso esgota a capacidade que justificou a escolha.

**Por que sobreposição de IC e não "top-K sempre".** O conjunto elegível é
**auto-regulável**: com evidência forte os intervalos são estreitos, o conjunto colapsa no
melhor pool e não há espalhamento indevido; com evidência fraca os intervalos são largos, o
conjunto abre e a carga se distribui. Espalhar entre pools estatisticamente **distinguíveis**
seria simplesmente mandar job para pool pior.

**Por que softmax com `tau` e não `score^gamma`.** Scores reais vivem em [0.80, 1.00]. Com
`gamma` = 3, um pool de 0.95 contra um de 0.90 recebe razão de peso de apenas 1.18 — quase
uniforme, o que é indistinguível de ignorar o score. Com `tau` = 0.02 o mesmo gap vira ~12×.
A temperatura dá controle direto sobre o quão agressiva é a preferência.

**Por que penalidade de inflight.** É o que efetivamente quebra a manada **no pico**: softmax
sozinho é um sorteio sem memória, e 3000 sorteios simultâneos com o mesmo peso concentram
carga na mesma proporção. O contador de inflight introduz realimentação negativa em janela de
60 s, com estado no Redis para ser global entre réplicas. `beta` = 2 é o ponto de partida, a
calibrar observando `pool_selection_total` sob rajada.

**Por que exploração direcionada (sabor UCB) e não epsilon-greedy uniforme.** É a armadilha
4. Escolher uniformemente gasta a cota de exploração em pools sobre os quais já se sabe o
suficiente. Escolher o de intervalo mais largo direciona a exploração para onde o dado é mais
escasso ou mais velho — muito mais eficiente em amostras, que é exatamente o recurso caro
aqui (cada amostra é um job real que pode falhar).

**Por que a regra de segurança do cooldown.** Um circuit breaker que zera as respostas
transformaria degradação em **indisponibilidade** e violaria R4. Melhor devolver o menos pior
com confiança baixa e aviso explícito do que não devolver nada.

### D5. Escada de degradação graciosa

**Decisão.** Snapshot no Redis → snapshot stale em memória → prior estático por tipo de
instância (alternando entre as AZs conhecidas). Toda resposta carrega o nível de confiança e a
idade do dado. A API **nunca** responde 5xx nem 404 por falta de dado.

**Por quê.** Um sistema de recomendação de melhor esforço não deveria falhar quando não tem
certeza — deveria responder com menos confiança e **dizer isso**. Devolver 503 forçaria o
chamador a implementar seu próprio fallback (provavelmente um pool hardcoded, pior que o
prior). Este é o argumento central de HA para R4, e é o que justifica os dois stores de D2.

### D6. Catálogo de instâncias como arquivo estático versionado

**Decisão.** Arquivo YAML/JSON no repo mapeando `instance_type` → {família, categoria, vCPU,
memória_GiB}. Categorias: `memory` (r, x, z), `compute` (c), `general` (m, t), `storage`
(i, d).

**Por quê.** É o que traduz "apenas instâncias focadas em memória" (R1) em um filtro
concreto. Arquivo versionado é auditável em diff, não exige chamada à API da AWS em runtime e
não adiciona dependência de rede na inicialização. Um tipo desconhecido em evento não quebra a
ingestão — o pool recebe categoria indefinida.

### D7. Arquitetura hexagonal com regra de ouro de import

**Decisão.** `domain/` puro (score, wilson, decaimento, catálogo, política); `application/`
com casos de uso e ports como `Protocol`; `adapters/` com Postgres, Redis, S3, SQS e fakes
in-memory; `api/`, `workers/`, `config.py`. **`domain/` não importa fastapi, sqlalchemy, redis
nem boto3.**

**Por quê.** O valor do case está no algoritmo, e o algoritmo precisa ser testável sem
infraestrutura: unit e property tests rodam em milissegundos, sem rede, o que é o que permite
a cobertura de 95% no domínio e o uso de Hypothesis para invariantes. Também é o que permite
a skill `scoring-eval` fazer replay de datasets contra configs alternativas sem levantar nada.
Esta é a regra que a rule `20-architecture-boundaries.mdc` protege.

### D8. Idempotência em dois níveis

**Decisão.** Nível de objeto: tabela `ingested_objects` com a chave do objeto S3. Nível de
evento: upsert por `(job_id, finished_at, pool_id)`.

**Por quê.** A entrega é at-least-once em dois pontos independentes — o mesmo objeto pode ser
notificado duas vezes pelo SQS, e o mesmo evento pode aparecer em dois objetos. Um único nível
não cobre os dois casos. Contadores por bucket recomputados a partir de eventos deduplicados
tornam a agregação idempotente por construção, sem depender de ordem (armadilha 6).

### D9. Fronteira de parsing como camada de defesa

**Decisão.** Todo o tratamento das armadilhas do dado acontece no adapter de ingestão: anexar
UTC explicitamente a `finished_at`; parsear `pool_id` por "primeiro hífen depois do prefixo"
em vez de split; descartar malformados incrementando `malformed_events_total`. As funções de
domínio **rejeitam** datetime naive em vez de assumir timezone.

**Por quê.** Datetime naive vazando para o cálculo de decaimento é bug silencioso — produz
score errado sem erro visível. Rejeitar nas fronteiras internas transforma um bug silencioso
em falha ruidosa em teste. E descarte silencioso de evento malformado esconde deterioração do
upstream; a métrica é o que torna isso observável.

### D10. Endpoint canônico com dois aliases

**Decisão.** `/get-pool` canônico; `/get-pools` alias visível no schema; `/getpools` alias
oculto (`include_in_schema=False`).

**Por quê.** R1 fala de `/get-pool`, R6 exige `http://localhost:5050/get-pools`, e o
enunciado original escreveu "/getpools" (interpretado como hífen faltante). O alias oculto
custa uma linha e elimina o risco de a avaliação usar a grafia literal do enunciado.

### D11. Piso Python 3.10 com sintaxe travada em 3.10

**Decisão.** `requires-python ">=3.10"`, ruff `target-version = py310`, matriz de CI
3.10/3.11/3.12, container 3.12. Proibido no código: `asyncio.TaskGroup`, `ExceptionGroup` /
`except*`, `datetime.UTC`, `StrEnum`, `tomllib`, `typing.Self`, `itertools.batched`,
`@override`, generics PEP 695.

**Por quê.** "Python > 3.9" lido como estritamente maior. As versões atuais de fastapi,
uvicorn, redis-py, structlog, alembic, pytest, mypy, boto3 e pydantic-settings exigem >= 3.10,
e o 3.9 está EOL desde 10/2025 — fixar o piso em 3.9 obrigaria a pinar toda a stack em versões
sem patch de segurança, o que é incompatível com "pronto para produção". A matriz de CI é o
que garante que o piso declarado é real, e a lista de sintaxe proibida é o que evita quebrar
3.10 desenvolvendo em 3.12.

### D12. Autenticação desligada por padrão

**Decisão.** Sem autenticação por default; header `X-API-Key` opcional habilitado por env var.

**Por quê.** Ligar autenticação por padrão quebraria o `curl` de um comando exigido por R6. A
defesa real em produção é topologia de rede (ALB interno, security groups, auth no gateway),
não código de aplicação — o toggle existe para o caso de exposição direta.

## ADRs previstos

| # | Decisão em uma frase |
|---|---|
| 1 | Framework web: **FastAPI + uvicorn**, por OpenAPI nativo (que já entrega parte de R5), validação Pydantic v2 dos filtros e maturidade de ecossistema — Litestar e Flask considerados. |
| 2 | Piso de Python: **>= 3.10**, lendo "> 3.9" como estritamente maior e apoiado no EOL do 3.9 e nos pisos das dependências atuais. |
| 3 | **Postgres + Redis** em vez de store único, porque durabilidade/história e serving sub-ms são requisitos distintos e a divisão é o que sustenta a degradação graciosa. |
| 4 | Ingestão **event-driven em produção e polling em dev**, atrás do mesmo port, recusando query-on-read para manter o S3 fora do caminho do request. |
| 5 | Métrica de confiabilidade: **Wilson lower bound com decaimento exponencial**, `SPARK_EXECUTION_ERROR` ignorado, `TIMED_OUT` com peso `alpha`, cap de 25% por `job_id`, e a complementaridade de escalas de tempo entre score e cooldown. |
| 6 | Política de seleção **estocástica** (sobreposição de IC + softmax + inflight + exploração direcionada), porque argmax cria o efeito manada e o loop de feedback fechado. |
| 7 | **HA por degradação graciosa** em três níveis, com a API nunca respondendo 5xx por ausência de dado e a readiness amarrada à existência de snapshot utilizável. |
| 8 | Topologia de produção: **container stateless atrás de load balancer interno**, com rolling update, readiness/liveness, HPA e PDB, entregue como diagrama mais **inventário concreto de recursos** (rede, autoscaling, health check, rollback) em vez de IaC não aplicada. |
| 9 | Estratégia de testes: **pirâmide com domínio puro, property-based para invariantes do score e um teste de aceitação de replay** como definição de pronto do produto. |
| 10 | Retenção e migrations: **particionamento diário com expurgo por DROP de partição**, nunca DELETE em massa, com Alembic versionando o schema. |
| 11 | Premissas e limitações do dado: ausência de `started_at` (evidência atribuída ao término), timezone implícito e duplicatas at-least-once. |
| 12 | Segurança: **sem autenticação por padrão** para preservar R6, com toggle de API key e a defesa real delegada à topologia de rede. |

## Inventário de artefatos Cursor

**Rules** (`.cursor/rules/*.mdc`, frontmatter `description`/`globs`/`alwaysApply`, cada uma
< 50 linhas, um assunto por arquivo):

| Arquivo | Escopo | Conteúdo |
|---|---|---|
| `00-project-context.mdc` | `alwaysApply: true` | glossário do domínio, mapa da arquitetura, os 7 requisitos como invariantes, links para os ADRs |
| `10-python-standards.mdc` | `**/*.py` | type hints obrigatórios, Pydantic v2, structlog (nunca `print`), sem `except` nu, zero literal mágico, piso de sintaxe 3.10 com a lista do proibido/permitido |
| `20-architecture-boundaries.mdc` | `src/**/*.py` | **regra de ouro**: `domain/` não importa fastapi/sqlalchemy/redis/boto3; acesso a dado sempre por port; direção de dependência única; exemplos BAD/GOOD de import |
| `30-api-contract.mdc` | `src/**/api/**` | `response_model` explícito, envelope de erro único, nunca 5xx por falta de dado, exemplos e descrições obrigatórios no OpenAPI, manter os três aliases |
| `40-testing.mdc` | `tests/**` | AAA, zero rede em unit, fakes/fakeredis/moto obrigatórios, seed fixa no estocástico, Hypothesis para invariantes do score |
| `50-docs-adr.mdc` | `docs/**` | template MADR, numeração sequencial, atualizar índice; ADR obrigatório para nova dependência ou troca de store; cada ADR linka a documentação oficial da opção escolhida e das alternativas descartadas |
| `60-infra-ci.mdc` | `Dockerfile`, `compose*.yaml`, `.github/workflows/**`, `Makefile` | multi-stage, usuário não-root, versões pinadas, healthchecks, zero segredo, OIDC, manter `make dev` verde |
| `70-git-workflow.mdc` | agent-requested (só `description`) | conventional commits, corpo de PR, proibido force push |

**Skills** (`.cursor/skills/<nome>/SKILL.md`):

| Skill | O que faz |
|---|---|
| `adr-new` | cria ADR com o próximo número no template MADR e atualiza o índice |
| `endpoint-slice` | checklist de fatia vertical: schema → serviço → port → adapter → testes → OpenAPI → docs |
| `event-generator` | gera dataset sintético a partir de cenário em linguagem natural ("us-east-1c degrada das 14h às 16h") |
| `quality-gate` | roda o CI localmente na mesma ordem e resume as falhas |
| `scoring-eval` | replay de dataset contra configs alternativas de score/política, com tabela comparativa (avaliação offline) |
| `case-compliance-audit` | audita os 7 requisitos um a um contra o repo e reporta lacunas |
| `load-test` | executa o perfil k6 e escreve o relatório em `docs/load-test.md` |

**Hooks** (`.cursor/hooks.json`, schema version 1, scripts em `.cursor/hooks/`, executáveis,
non-interactive, dependências verificadas com `command -v`, matchers em regex estilo
JavaScript — nunca classes POSIX):

| Evento | Matcher | Script | Efeito |
|---|---|---|---|
| `afterFileEdit` | `Write` | `format-python.sh` | `ruff format` + `ruff check --fix` no arquivo editado, ignorando não-`.py` |
| `beforeShellExecution` | — (`failClosed: true`) | `guard-commands.sh` | deny/ask em `git push --force`, `rm -rf`, `docker compose down -v`, `terraform apply/destroy`, comandos `aws` mutantes |
| `beforeSubmitPrompt` | — | `scan-secrets.sh` | bloqueia prompt contendo padrão de credencial AWS |
| `beforeReadFile` | — | `block-secrets.sh` | bloqueia `.env*`, `*.pem`, `~/.aws/credentials` |
| `stop` | — (`loop_limit: 2`) | `verify-gate.sh` | ruff + mypy + unit tests **apenas dos arquivos alterados**; devolve `followup_message` se falhar; orçamento < 60 s ou vira atrito |

## Matriz de rastreabilidade

| Req | Como é fechado | Fase | Teste / comando que comprova |
|---|---|---|---|
| **R1** Python > 3.9, endpoint devolve pool id, filtros de tipo | `requires-python >=3.10`; `GET /get-pool`; filtros de categoria/família/tipo/vCPU/memória via catálogo | 1, 3 | unit de parser/score/política + contract test do endpoint + cenários de `instance-catalog` (job memory-bound e cpu-bound); matriz de CI 3.10/3.11/3.12 |
| **R2** Framework com racional | FastAPI + uvicorn, ADR 1 | 3, 5 | `openapi.json` exportado como artefato do CI; ADR 1 presente e indexado |
| **R3** Banco com racional | Postgres + Redis, ADR 3 | 2, 5 | teste de integração de idempotência e de consistência agregado → snapshot; ADR 3 presente |
| **R4** HA e escalabilidade | ingestão fora do request, snapshot + cache em processo, escada de degradação, réplicas stateless, ADRs 7 e 8 | 2, 3, 6 | testes da escada de degradação (Redis fora, Postgres fora, sem snapshot); k6 nos três cenários com números em `docs/load-test.md` |
| **R5** Pronto para produção | 12 ADRs, `docs/api.md`, `docs/runbook.md`, CI/CD completo, observabilidade, testes unitários | 5, 6 | `make lint && make typecheck && make test` verdes com gates de cobertura; pipeline verde no remoto; skill `case-compliance-audit` sem lacuna |
| **R6** Um comando, deps isoladas, `localhost:5050/get-pools` | `uv` + compose com healthchecks + `make dev` | 4 | smoke test do CI: `docker compose up` + `curl http://localhost:5050/get-pools` validando o payload contra o contrato |
| **R7** Repositório remoto no GitHub | push com Actions habilitado, branch protection, CODEOWNERS | 6 | pipeline verde no remoto; badge/execução visível no repositório |

Além dos requisitos, os quatro problemas escondidos têm cada um seu teste-testemunha:

| Problema | Mecanismo | Teste que o comprova |
|---|---|---|
| Sinal enviesado por motivo | exclusão de `SPARK_EXECUTION_ERROR`, `alpha` para `TIMED_OUT` | unit "erro de execução do Spark não afeta o pool" |
| Evidência escassa | Wilson lower bound | unit "evidência escassa perde de evidência forte" + property de monotonicidade |
| Efeito manada | conjunto elegível + softmax + penalidade de inflight | distribuição em `pool_selection_total` no cenário de rajada do k6 |
| Loop de feedback fechado | exploração direcionada por IC mais largo | unit "pool congelado volta a ser avaliado" + frequência ≈ `epsilon` |

## Risks / Trade-offs

- **Latência de detecção com meia-vida de 30 min** → o cooldown (janela de 5 min, gatilho de
  3 eventos) cobre a reação rápida; as duas escalas de tempo são complementares por design e o
  ADR 5 registra isso explicitamente.
- **`alpha` = 0.3 é um chute informado** → tarefa explícita da Fase 6: validar 0.0/0.3/0.5 com
  a skill `scoring-eval` sobre dataset de replay antes de considerar o valor final.
- **`beta` = 2 pode sub ou sobrecorrigir a manada** → calibração empírica na Fase 6 observando
  `pool_selection_total` sob o cenário de rajada; a métrica existe justamente para isso.
- **Evidência atribuída ao `finished_at` porque não há `started_at`** → limitação inerente ao
  dado, não corrigível por implementação; documentada como premissa no ADR 11 e no README.
- **Efeito manada distribuído entre réplicas** → inflight e cooldown vivem no Redis com TTL
  para serem globais; com o Redis fora, a penalidade degrada para local, o que é registrado
  como aviso na resposta.
- **Cache em processo de 1–5 s adia a reação ao cooldown** → TTL é configuração e o teto de 5 s
  é uma ordem de magnitude menor que a duração mínima de cooldown (10 min), então o atraso é
  irrelevante na prática.
- **Prior de fallback pode recomendar um pool ruim** → é aceito conscientemente: a alternativa
  (5xx) transferiria o problema para o chamador com menos informação; a resposta sempre carrega
  `confidence=low` e aviso.
- **Cobertura de 95% no domínio pode virar teste que passa sem verificar nada** →
  mutation testing sobre `domain/scoring.py` como relatório não bloqueante, mais gate de
  cobertura de **diff** ≥ 90% para impedir código novo descoberto.
- **Escopo grande para o tempo de um case** → fases ordenadas por valor decrescente, com o
  teste de aceitação de replay de 24 h explicitamente marcado como o último item a ser cortado
  se o cronograma apertar (é o que prova o produto, então corta-se depois de tudo).
- **Compose com 6 serviços é frágil em máquina limpa** → `depends_on: service_healthy` em
  todas as arestas, readiness gate na API e smoke test no CI, que é a única forma de detectar
  quebra de R6 sem depender de alguém rodando na mão.
- **Hook `stop` lento vira atrito** → roda ruff, mypy e unit tests **apenas dos arquivos
  alterados**, com `loop_limit: 2` e orçamento de 60 s.

## Migration Plan

Não há migração: o sistema é novo e não há consumidor em produção. A sequência de entrega é a
das seis fases em `tasks.md`, e cada fase tem um comando que prova sua conclusão.

Estratégia de rollback do deploy (ADR 8): imagem versionada por SHA no GHCR, rolling update
com readiness gate, rollback por reapontar a tag anterior. Como o snapshot no Redis é dado
derivado, rollback de aplicação não exige rollback de dado; migrations do Postgres são
aditivas e reversíveis por Alembic.

## Open Questions

1. **`alpha` (peso de `TIMED_OUT`)**: 0.3 é o default; confirmar contra 0.0 e 0.5 por
   medição na Fase 6. Pendente de **medição**, não de decisão.
2. **`beta` (penalidade de inflight)**: 2 é o default; calibrar pela distribuição observada em
   `pool_selection_total` sob rajada na Fase 6. Pendente de **medição**, não de decisão.
3. **Limiares de `confidence`** (massa de evidência que separa alto/médio/baixo): valores
   iniciais definidos em configuração na Fase 1, a revisar com o dataset de replay — não
   afetam contrato nem arquitetura.
