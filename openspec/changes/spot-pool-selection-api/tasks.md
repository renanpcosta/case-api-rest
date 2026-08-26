## 1. Fase 0 — Scaffolding

**Fecha:** base de R5 e R6. **Arquivos:** `pyproject.toml`, `uv.lock`, `Makefile`,
`.gitignore`, `LICENSE`, `README.md`, `.cursor/rules/*.mdc`, `.cursor/skills/*/SKILL.md`,
`.cursor/hooks.json`, `.cursor/hooks/*.sh`, `.github/workflows/ci.yml`,
`.pre-commit-config.yaml`, `src/pool_selector/__init__.py`, `tests/conftest.py`.
**DoD:** `make lint && make typecheck && make test` verdes num repo sem código de negócio, e
os hooks disparando ao editar um `.py`.

- [ ] 1.1 Criar `pyproject.toml` com `requires-python ">=3.10"`, metadados do projeto e
  layout `src/`, e gerar `uv.lock` com `uv lock`
- [ ] 1.2 Configurar ruff (lint + format) com `target-version = "py310"` e o conjunto de
  regras, incluindo as que barram `print` e `except` nu
- [ ] 1.3 Configurar mypy em modo strict e pytest (asyncio, cobertura, marcadores
  `unit`/`integration`/`acceptance`)
- [ ] 1.4 Criar a árvore de pacotes vazia `src/pool_selector/{domain,application,adapters,api,workers}`
  com `__init__.py` e a árvore `tests/{unit,integration,acceptance,load}`
- [ ] 1.5 Escrever `Makefile` com alvos `install`, `lint`, `format`, `typecheck`, `test`,
  `test-unit`, `verify`, `dev`, `down`, `smoke` (alvos de compose podem ficar como stub até a Fase 4)
- [ ] 1.6 Criar `.gitignore`, `LICENSE` e o esqueleto do `README.md` com as seções que serão
  preenchidas na Fase 5
- [ ] 1.7 Escrever as 8 rules em `.cursor/rules/` conforme o inventário do design (cada uma
  < 50 linhas, um assunto por arquivo, frontmatter com `description`/`globs`/`alwaysApply`)
- [ ] 1.8 Escrever as 7 skills em `.cursor/skills/<nome>/SKILL.md` conforme o inventário do
  design (o conteúdo executável de `scoring-eval` e `load-test` amadurece nas Fases 1 e 6)
- [ ] 1.9 Escrever `.cursor/hooks.json` (schema version 1) e os 5 scripts em `.cursor/hooks/`,
  todos executáveis, non-interactive e verificando dependências com `command -v`
- [ ] 1.10 Validar os hooks manualmente: editar um `.py` dispara o format, um comando
  bloqueado é negado e o gate de `stop` roda em menos de 60 s
- [ ] 1.11 Criar `ci.yml` mínimo (checkout, setup do uv, lint, typecheck, test) e confirmar
  execução verde
- [ ] 1.12 Configurar `.pre-commit-config.yaml` reaproveitando ruff, mais Dependabot,
  CODEOWNERS e PR template

## 2. Fase 1 — Domínio puro

**Fecha:** o coração de R1. **Arquivos:** `src/pool_selector/domain/{events.py,pool.py,
catalog.py,scoring.py,wilson.py,decay.py,cooldown.py,policy.py,priors.py}`,
`src/pool_selector/config.py`, `data/instance_catalog.yaml`, `tools/generate_events.py`,
`tests/unit/**`. **DoD:** unit + property tests verdes, cobertura do domínio > 95%, e
verificação de que nenhum módulo de `domain/` importa framework ou SDK.

- [ ] 2.1 Definir os modelos de domínio: evento normalizado, identidade de pool, `reason` como
  `class X(str, Enum)`, agregado por bucket e resultado pontuado
- [ ] 2.2 Implementar `config.py` com pydantic-settings expondo **todas** as constantes do
  algoritmo (`W`, `h`, bucket, `alpha`, cap por job, `tau`, `K`, `epsilon`, `beta`, parâmetros
  de cooldown, TTLs, limiares de confiança) — zero literal mágico no código
- [ ] 2.3 Implementar o parser de `pool_id` pela regra do primeiro hífen após o prefixo, com
  resultado explícito de inválido
- [ ] 2.4 Implementar a normalização de `finished_at` anexando UTC, e fazer as funções de
  domínio rejeitarem datetime naive
- [ ] 2.5 Escrever unit tests do parser de `pool_id` (canônico, AZ com múltiplos hífens, sem
  prefixo, sem hífen, tokens vazios) e do timestamp (sem tz, com tz, naive rejeitado)
- [ ] 2.6 Criar `data/instance_catalog.yaml` e o carregador com validação estrita na
  inicialização, derivando família e categoria (memory r/x/z, compute c, general m/t, storage i/d)
- [ ] 2.7 Implementar os filtros do catálogo (categoria, famílias, tipos, `min_vcpu`,
  `min_memory_gib`, `az`, `exclude_az`) com precedência da exclusão e distinção entre inválido
  e logicamente vazio
- [ ] 2.8 Escrever unit tests dos filtros, cobrindo job memory-bound, job cpu-bound,
  combinação de filtros, exclusão de AZ e conjunto vazio
- [ ] 2.9 Implementar o decaimento exponencial por meia-vida e o corte pela janela
- [ ] 2.10 Implementar Wilson lower e upper bound com nível de confiança configurável
- [ ] 2.11 Implementar a composição de `S_p` e `F_p` com exclusão de `SPARK_EXECUTION_ERROR` e
  peso `alpha` para `TIMED_OUT`
- [ ] 2.12 Implementar o cap de contribuição de falha por `job_id`
- [ ] 2.13 Implementar os priors (por tipo de instância e global) e a classificação de
  confiança em alto/médio/baixo
- [ ] 2.14 Escrever unit tests de score: pesos de decaimento, exclusão do erro de execução,
  peso do timeout, cap por job com e sem concentração, escassez perdendo de evidência forte
- [ ] 2.15 Escrever property tests com Hypothesis para as invariantes: score em `[0,1]`, mais
  sucessos nunca reduz, mais falhas nunca aumenta, ordem dos eventos não altera o resultado,
  lower bound <= upper bound
- [ ] 2.16 Implementar o gatilho de cooldown (3 em 5 min, ou >= 50% com >= 2 eventos), o
  backoff 10/20/40 com teto 60 e o reset após 1 h limpa
- [ ] 2.17 Implementar a formação do conjunto elegível por sobreposição de IC com teto `K`
- [ ] 2.18 Implementar o peso por softmax com temperatura, numericamente estável
- [ ] 2.19 Implementar a penalidade de inflight sobre excesso de share
- [ ] 2.20 Implementar a exploração direcionada pelo IC mais largo, excluindo pools em cooldown
- [ ] 2.21 Implementar a amostragem ponderada com RNG injetável e a identificação da política
  aplicada, incluindo a regra de segurança de bypass quando o cooldown esvazia os candidatos
- [ ] 2.22 Escrever unit tests da política: gatilhos e backoff de cooldown, bypass com conjunto
  vazio, colapso e abertura do conjunto elegível, razão de peso do softmax no gap 0.95/0.90,
  penalidade de inflight, exploração direcionada, reprodutibilidade por seed e frequência de
  exploração
- [ ] 2.23 Implementar `tools/generate_events.py` com cenários parametrizados (degradação de AZ
  em faixa horária, rajada de pico, baseline) e seed fixa
- [ ] 2.24 Verificar por teste automatizado que nenhum módulo de `domain/` importa fastapi,
  sqlalchemy, redis ou boto3, e habilitar o gate de cobertura do domínio em 95%

## 3. Fase 2 — Ports & adapters

**Fecha:** R3. **Arquivos:** `src/pool_selector/application/{ports.py,use_cases/*.py}`,
`src/pool_selector/adapters/{postgres/*,redis/*,s3/*,sqs/*,fakes/*}`,
`src/pool_selector/workers/aggregator.py`, `migrations/**`, `alembic.ini`,
`tests/integration/**`. **DoD:** teste de integração provando idempotência de reprocessamento
e consistência entre agregado no Postgres e snapshot no Redis.

- [ ] 3.1 Definir os ports como `Protocol`: repositório de eventos, repositório de agregados,
  store de snapshot, contadores de inflight, store de cooldown, source de objetos e sink de
  recomendações
- [ ] 3.2 Implementar os fakes in-memory de todos os ports, para uso em unit e contract tests
- [ ] 3.3 Modelar as tabelas com SQLAlchemy 2.0: `job_events`, `pool_aggregates` (por
  `(pool, bucket)` e por `(pool, bucket, job_id)`), `recommendations`, `ingested_objects`
- [ ] 3.4 Configurar Alembic e escrever a migration inicial com particionamento diário e a
  rotina de criação antecipada de partição
- [ ] 3.5 Implementar o adapter Postgres de eventos com upsert idempotente por
  `(job_id, finished_at, pool_id)`
- [ ] 3.6 Implementar o adapter Postgres de agregados com incremento por bucket independente de
  ordem, e o registro de objetos ingeridos
- [ ] 3.7 Implementar o adapter Postgres de recomendações, com gravação que não bloqueia a
  resposta em caso de falha
- [ ] 3.8 Implementar a rotina de expurgo por DROP de partição respeitando as retenções (7/30/30/7
  dias), sem nenhum DELETE em massa
- [ ] 3.9 Implementar o adapter Redis: publicação atômica do snapshot serializado, contadores
  de inflight com TTL de 60 s e flags de cooldown com TTL e contador de reincidência
- [ ] 3.10 Implementar o source S3/MinIO com listagem e leitura streaming de JSON Lines, e o
  source SQS consumindo notificações e confirmando a mensagem só após o commit do lote
- [ ] 3.11 Implementar o caso de uso de ingestão de objeto: parsing linha a linha, descarte
  contabilizado de malformados, dedupe em dois níveis e agregação
- [ ] 3.12 Implementar o caso de uso de recomputação de ranking e publicação de snapshot com
  instante de geração
- [ ] 3.13 Implementar o worker agregador orquestrando ingestão, ranking e expurgo em laço, com
  intervalo configurável, shutdown limpo e `asyncio.gather` (nunca `TaskGroup`)
- [ ] 3.14 Escrever teste de integração de idempotência: reprocessar o mesmo objeto e o mesmo
  evento duplicado não altera os agregados
- [ ] 3.15 Escrever teste de integração de consistência: agregados no Postgres refletem
  exatamente o snapshot publicado no Redis
- [ ] 3.16 Escrever teste de integração do expurgo por partição e da reconstrução do snapshot
  após limpeza do Redis
- [ ] 3.17 Escrever teste de integração de eventos fora de ordem e atrasados caindo no bucket
  correto

## 4. Fase 3 — API

**Fecha:** R1 e R2. **Arquivos:** `src/pool_selector/api/{app.py,routers/pools.py,
routers/health.py,schemas.py,deps.py,errors.py,middleware.py,metrics.py}`,
`src/pool_selector/application/use_cases/recommend.py`, `tests/unit/api/**`,
`tests/integration/api/**`. **DoD:** contract tests verdes, `openapi.json` gerado, e requisição
sem dado nenhum respondendo 200 com `confidence=low`.

- [ ] 4.1 Criar a aplicação FastAPI com lifespan carregando catálogo e configuração, e
  registrar o middleware de `X-Request-Id` e de logging correlacionado
- [ ] 4.2 Definir os schemas Pydantic v2 de request (todos os filtros, `job_id`, `candidates`)
  e de response (todos os campos de explicabilidade), com descrições e exemplos
- [ ] 4.3 Implementar o envelope de erro único e os handlers de 422, 400 e exceção não tratada
- [ ] 4.4 Implementar o caso de uso de recomendação orquestrando snapshot, filtro, cooldown,
  política e registro de telemetria
- [ ] 4.5 Implementar o cache em processo do snapshot com TTL curto configurável
- [ ] 4.6 Implementar a escada de degradação: Redis → snapshot stale em memória → prior
  estático com alternância entre AZs, cada nível com aviso e nível de confiança próprios
- [ ] 4.7 Registrar `GET /get-pool` com `response_model` explícito, mais o alias `/get-pools`
  visível e o alias `/getpools` com `include_in_schema=False`
- [ ] 4.8 Aplicar `Cache-Control: no-store` e a propagação/geração de `X-Request-Id` nas
  respostas
- [ ] 4.9 Implementar `/health/live`, `/health/ready` (verde só com snapshot utilizável),
  `/metrics` e `/version`
- [ ] 4.10 Implementar a autenticação opcional por `X-API-Key`, desligada por padrão
- [ ] 4.11 Escrever contract tests: 200 com payload completo, 422 por parâmetro inválido, 400
  por filtro logicamente vazio, ausência total de dado devolvendo 200 com `confidence=low`
- [ ] 4.12 Escrever contract tests dos três aliases de rota e da visibilidade de cada um no
  documento OpenAPI
- [ ] 4.13 Escrever testes da escada de degradação com Redis indisponível, Postgres
  indisponível e nenhum snapshot
- [ ] 4.14 Escrever teste de estabilidade do schema comparando o response model ao contrato
  versionado, e adicionar o comando de exportação do `openapi.json`

## 5. Fase 4 — Um comando

**Fecha:** R6. **Arquivos:** `compose.yaml`, `docker/Dockerfile.api`,
`docker/Dockerfile.worker`, `docker/seed/*`, `.env.example`, `Makefile` (alvos `dev`/`smoke`),
`tests/acceptance/**`. **DoD:** em máquina limpa, um único comando sobe tudo e
`curl http://localhost:5050/get-pools` devolve payload válido; teste de aceitação do replay de
24 h verde.

- [ ] 5.1 Escrever o Dockerfile multi-stage da API com `uv`, container 3.12, usuário não-root e
  versões pinadas
- [ ] 5.2 Escrever o Dockerfile do worker reaproveitando o estágio de build
- [ ] 5.3 Escrever `compose.yaml` com api, aggregator, postgres, redis, minio e seeder,
  healthcheck em cada serviço e `depends_on: service_healthy` em todas as arestas
- [ ] 5.4 Expor a API em `localhost:5050` e implementar o seeder que cria o bucket no MinIO e
  carrega o dataset sintético inicial
- [ ] 5.5 Implementar o alvo `make dev` idempotente (segunda execução conclui com sucesso) e o
  alvo `make down`
- [ ] 5.6 Implementar `make smoke`: aguardar readiness, chamar `http://localhost:5050/get-pools`
  e validar o payload contra o contrato, falhando com dump de logs dos serviços
- [ ] 5.7 Validar a subida em ambiente limpo (volumes e imagens removidos) e cronometrar o
  tempo até o endpoint responder
- [ ] 5.8 Escrever o teste de aceitação de replay de 24 h com degradação de uma AZ das 14h às
  16h e seed fixa, assertando a queda das recomendações para aquela AZ dentro da janela e a
  volta depois
- [ ] 5.9 Documentar `.env.example` com todas as variáveis e seus defaults, sem nenhum segredo

## 6. Fase 5 — Documentação

**Fecha:** R5. **Arquivos:** `README.md`, `docs/adr/000-index.md`, `docs/adr/001..012-*.md`,
`docs/architecture.md`, `docs/api.md`, `docs/runbook.md`. **DoD:** a skill
`case-compliance-audit` reporta zero lacuna nos 7 requisitos.
**Convenção da fase:** todo ADR linka a documentação oficial da opção escolhida e das
alternativas descartadas — é nos ADRs que os links de stack vivem, não em `project.md`.

- [ ] 6.1 Escrever os ADRs 1 a 4 (framework web, piso de Python, divisão Postgres + Redis,
  ingestão event-driven vs polling vs query-on-read) no template MADR
- [ ] 6.2 Escrever os ADRs 5 e 6 (métrica de confiabilidade e política de seleção estocástica),
  incluindo a complementaridade de escalas de tempo entre score e cooldown
- [ ] 6.3 Escrever o ADR 7 (HA e degradação graciosa em três níveis, com a readiness amarrada
  à existência de snapshot utilizável)
- [ ] 6.4 Escrever o ADR 8 com o diagrama da topologia de produção e o **inventário concreto
  de recursos** — rede, load balancer interno, autoscaling, health check, estratégia de rolling
  update e de rollback — mais o registro explícito de por que não há IaC no escopo
- [ ] 6.5 Escrever os ADRs 9 a 12 (estratégia de testes e definição de pronto, retenção e
  migrations, premissas e limitações do dado, segurança e ausência de autenticação)
- [ ] 6.6 Criar o índice de ADRs e garantir numeração sequencial, links cruzados e o link de
  documentação oficial em cada decisão e alternativa descartada
- [ ] 6.7 Escrever `docs/architecture.md` com o diagrama dos dois caminhos e da escada de
  degradação
- [ ] 6.8 Escrever `docs/api.md` com o contrato completo, todos os parâmetros, os códigos de
  erro e exemplos reais de request e resposta
- [ ] 6.9 Escrever `docs/runbook.md` cobrindo agregador atrasado, Redis fora, Postgres fora e
  replay/backfill a partir do S3
- [ ] 6.10 Completar o `README.md` com a promessa do comando único, `curl` de exemplo com
  resposta real, diagrama, premissas assumidas, links de onboarding da stack e como rodar os
  testes
- [ ] 6.11 Rodar a skill `case-compliance-audit` e fechar as lacunas que ela apontar

## 7. Fase 6 — Produção

**Fecha:** R4, R5 e R7. **Arquivos:** `.github/workflows/{ci.yml,cd.yml}`,
`tests/load/*.js`, `docs/load-test.md`, `docs/adr/*` (revisões), configuração de branch
protection. **DoD:** `docs/load-test.md` com números medidos batendo os SLOs nos três cenários
e pipeline verde no remoto.

- [ ] 7.1 Completar `ci.yml`: ruff check + format check, mypy strict, pytest com gates de
  cobertura (global 85%, domínio 95%, diff 90%) e matriz 3.10/3.11/3.12
- [ ] 7.2 Adicionar ao `ci.yml` o build da imagem, trivy, pip-audit e o export do
  `openapi.json` como artefato
- [ ] 7.3 Adicionar ao `ci.yml` o job de smoke que sobe o compose e valida
  `http://localhost:5050/get-pools` — é a proteção automática de R6
- [ ] 7.4 Adicionar o relatório não bloqueante de mutation testing sobre `domain/scoring.py`
- [ ] 7.5 Escrever `cd.yml`: build/push no GHCR com tag do SHA em `main`, release com changelog
  de conventional commits em tag semver, e job de deploy com `environment: production`,
  aprovação manual e autenticação por OIDC (zero chave estática)
- [ ] 7.6 Instrumentar as métricas Prometheus: histograma de latência, `pool_selection_total`,
  `aggregate_staleness_seconds`, `consumer_lag`, `malformed_events_total`, `cooldown_active` e
  `fallback_used_total`
- [ ] 7.7 Implementar a consulta da métrica de efetividade (taxa de falha por terminação spot
  dos jobs que rodaram nos pools recomendados) sobre a tabela de recomendações
- [ ] 7.8 Escrever os três cenários k6: estável a 500 rps, rajada de 0 a 3000 rps em 10 s e
  soak de 30 min
- [ ] 7.9 Executar os cenários e escrever `docs/load-test.md` com p50, p99 e vazão **medidos**,
  comparados aos SLOs
- [ ] 7.10 Calibrar `beta` pela distribuição observada em `pool_selection_total` no cenário de
  rajada e registrar o resultado
- [ ] 7.11 Validar `alpha` em 0.0, 0.3 e 0.5 com a skill `scoring-eval` sobre o dataset de
  replay e registrar a tabela comparativa no ADR 5
- [ ] 7.12 Fazer o push para o repositório remoto no github.com, habilitar Actions, configurar
  branch protection e confirmar pipeline verde no remoto

## Grafo de dependências e paralelização

**Caminho crítico:** Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 6.

**Arestas reais entre fases:**

- Fase 1 depende da Fase 0 apenas pelo tooling (`pyproject`, ruff, pytest); nada mais.
- Fase 2 depende da Fase 1 pelos modelos de domínio e por `config.py`.
- Fase 3 depende da Fase 1 (política e catálogo) e da Fase 2 (ports e fakes) — mas **só dos
  fakes**, não dos adapters reais, então 4.1–4.14 podem ser escritos e testados antes de
  Postgres e Redis existirem.
- Fase 4 depende da Fase 3 (imagem da API) e da Fase 2 (imagem do worker).
- Fase 5 depende conceitualmente de tudo, mas cada ADR pode ser escrito assim que sua decisão
  é implementada.
- Fase 6 depende da Fase 4 para o smoke e o teste de carga, e da Fase 1 para o `scoring-eval`.

**O que pode ser paralelizado:**

- Dentro da Fase 1: os três blocos são independentes entre si — parsing/catálogo (2.3–2.8),
  score (2.9–2.15) e política/cooldown (2.16–2.22). O gerador de eventos (2.23) só depende dos
  modelos (2.1).
- Dentro da Fase 2: Postgres (3.3–3.8), Redis (3.9) e S3/SQS (3.10) são independentes depois
  que os ports (3.1) e os fakes (3.2) existem.
- Fase 3 em paralelo com os adapters reais da Fase 2, usando os fakes.
- Fase 5 em paralelo com as Fases 2, 3 e 4: os ADRs 1, 2, 5, 6 e 11 podem ser escritos logo
  após a Fase 1, porque suas decisões já estão travadas.
- Dentro da Fase 6: os workflows (7.1–7.5) são independentes da instrumentação (7.6–7.7) e dos
  cenários k6 (7.8), que só convergem em 7.9–7.11.
- As skills e rules da Fase 0 (1.7–1.9) são independentes de todo o resto e podem ser feitas
  em paralelo com 1.1–1.6.

**Ordem de corte se o cronograma apertar** (do primeiro ao último a cair): mutation testing
(7.4) → soak de 30 min (parte de 7.8) → cd.yml completo (7.5, mantendo build/push) → teste de
aceitação de replay de 24 h (5.8). O 5.8 é o **último** a ser cortado porque é o único teste
que prova o produto, não apenas as partes.
