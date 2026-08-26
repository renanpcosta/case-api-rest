## Why

Jobs Apache Spark rodam em pools de instâncias EC2 spot e falham quando a AWS retoma
capacidade; a disponibilidade spot varia por tipo de instância, por AZ e ao longo do dia, e
hoje não existe nada que responda "qual pool tem, agora, a maior probabilidade de um job
terminar sem perder instâncias". A única evidência disponível é o histórico de términos de
job em S3, e extrair um sinal confiável dele exige resolver quatro problemas que uma média
simples de taxa de sucesso não resolve: viés por motivo de falha, evidência escassa, efeito
manada e loop de feedback fechado.

O repositório é greenfield (apenas README e commit inicial), então esta change cobre o
sistema completo, do scaffolding à entrega pronta para produção.

## What Changes

- **Ingestão assíncrona desacoplada do request**: worker que lê objetos JSON Lines do S3
  (prod: S3 Event Notifications → SQS; dev: polling de MinIO), faz upsert idempotente por
  `(job_id, finished_at, pool_id)`, agrega em contadores por bucket de 5 min e publica um
  snapshot de ranking serializado no Redis. O caminho do request **nunca** toca o S3.
- **Métrica de confiabilidade por pool** que ataca o viés e a escassez: Wilson lower bound
  95% sobre sucessos vs terminações spot, com decaimento exponencial (meia-vida 30 min),
  `SPARK_EXECUTION_ERROR` totalmente ignorado (é culpa do job, não do pool),
  `TIMED_OUT` com peso `alpha` = 0.3 (sinal precoce de degradação) e cap de 25% da massa de
  falha por `job_id` (um job cronicamente quebrado não degrada o pool mais saudável).
- **Política de seleção estocástica** que ataca o efeito manada e o loop fechado: conjunto
  elegível por sobreposição de intervalo de confiança (limitado a K=5), peso por softmax com
  temperatura `tau` = 0.02, penalidade de inflight sobre share dos últimos 60s, exploração
  direcionada tipo UCB com `epsilon` = 0.02 e cooldown com backoff exponencial. Não é argmax.
- **Endpoint `GET /get-pool`** (aliases `/get-pools` visível e `/getpools` oculto) com
  filtros combináveis de categoria, família, tipo, vCPU, memória e AZ, e resposta com
  explicabilidade completa: score, confidence, evidência da janela, frescor do dado,
  alternativas ranqueadas, política aplicada e warnings.
- **Escada de degradação graciosa**: snapshot no Redis → snapshot stale em memória → prior
  estático por tipo de instância. A API nunca devolve 5xx nem 404 por ausência de dado.
- **Catálogo de instâncias versionado no repo** mapeando `instance_type` → família,
  categoria (memory/compute/general/storage), vCPU e memória — é o que traduz "apenas
  instâncias focadas em memória" em filtro concreto.
- **Persistência dual**: PostgreSQL para eventos deduplicados, agregados e histórico de
  recomendações (habilita a métrica de efetividade e avaliação offline por SQL); Redis para
  serving sub-ms.
- **Ambiente de dev em um comando**: Docker Compose com api, aggregator, postgres, redis,
  minio e seeder, com `depends_on: service_healthy` e readiness gate, respondendo em
  `http://localhost:5050/get-pools`.
- **Prontidão para produção**: 12 ADRs no template MADR, `docs/api.md`, `docs/runbook.md`,
  `docs/load-test.md` com números medidos, observabilidade (structlog JSON +
  prometheus-client, incluindo a métrica de efetividade), CI com matriz 3.10/3.11/3.12,
  gates de cobertura, scan de segurança e smoke test do compose, e CD por OIDC.
- **Ferramental Cursor completo**: 8 rules, 7 skills e 5 hooks, incluindo a rule de
  fronteiras de arquitetura e as skills `scoring-eval` (avaliação offline do algoritmo) e
  `case-compliance-audit` (auditoria dos 7 requisitos).

Nenhuma mudança é breaking: não existe nada em produção.

## Capabilities

### New Capabilities

- `event-ingestion`: leitura de objetos JSON Lines do S3, parsing e validação de eventos
  (timezone, `pool_id`, malformados), idempotência at-least-once em dois níveis (objeto e
  evento) e agregação em contadores por bucket de tempo tolerantes a eventos fora de ordem.
- `pool-scoring`: cálculo do score de confiabilidade por pool — decaimento exponencial,
  tratamento por `reason`, cap por `job_id`, Wilson lower/upper bound, priors para pools sem
  evidência — e a recomputação periódica do ranking publicado como snapshot.
- `pool-selection`: política estocástica de escolha do pool — cooldown com backoff e regra de
  segurança de conjunto vazio, conjunto elegível por sobreposição de IC, softmax, penalidade
  de inflight, exploração direcionada e amostragem ponderada com RNG injetável.
- `instance-catalog`: catálogo estático de tipos de instância e a semântica dos filtros
  (categoria, família, tipo, `min_vcpu`, `min_memory_gib`, `az`/`exclude_az`), incluindo a
  distinção entre filtro inválido (422) e filtro logicamente vazio (400).
- `pool-api`: contrato HTTP do endpoint de recomendação e seus aliases, envelope de erro
  único, campos de explicabilidade, headers, escada de degradação no caminho de leitura e
  endpoints auxiliares `/health/live`, `/health/ready`, `/metrics`, `/version`.
- `observability`: logs JSON correlacionados por `request_id`, métricas Prometheus
  (latência, `pool_selection_total`, staleness, consumer lag, malformed, cooldown, fallback),
  a métrica de efetividade baseada na tabela `recommendations` e os SLOs.
- `dev-environment`: subida do ambiente completo em um único comando com dependências
  isoladas, healthchecks, seeder de dados sintéticos e o alvo de smoke test que valida R6.

### Modified Capabilities

Nenhuma — `openspec/specs/` está vazio (projeto greenfield).

## Impact

- **Repositório inteiro**: `src/pool_selector/{domain,application,adapters,api,workers}`,
  `tests/{unit,integration,acceptance,load}`, `docs/{adr,architecture.md,api.md,runbook.md,load-test.md}`,
  `tools/generate_events.py`, `docker/`, `.github/workflows/`, `.cursor/`, `Makefile`,
  `compose.yaml`, `pyproject.toml`, `uv.lock`.
- **Dependências novas** (cada uma coberta por decisão já travada em `openspec/project.md`):
  fastapi, uvicorn, pydantic/pydantic-settings, sqlalchemy 2.0 async, asyncpg, alembic,
  redis-py, boto3, structlog, prometheus-client, tomli, typing_extensions; dev: ruff, mypy,
  pytest (+asyncio, +cov), hypothesis, fakeredis, moto, httpx, k6 (via container).
- **Infraestrutura**: PostgreSQL e Redis passam a ser dependências de runtime; MinIO apenas
  em dev. Sem IaC — a topologia de produção fica documentada em ADR.
- **Externo**: requer repositório remoto no github.com com Actions habilitado (R7) e, em
  produção, permissão de leitura no bucket S3 e uma fila SQS.
- **Fora de escopo** (anti-objetivos): PySpark/Polars/DuckDB na ingestão, consulta a
  S3/Athena no request, Kafka, Kubernetes real, service mesh, frontend, autenticação
  complexa.
