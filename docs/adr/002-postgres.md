# ADR 2 — Postgres apenas

## Status

Aceito.

## Contexto

R3 pede uma escolha de banco documentada (ou nenhuma). Os eventos precisam sobreviver ao restart do processo para o score não ser recalculado a partir de um arquivo em cada réplica de forma inconsistente. A entrada de produção do enunciado é JSONL no S3; este MVP roda localmente.

## Decisão

Um **Postgres**. Tabela `job_events`, schema criado na subida da API (sem Alembic). `data/events.jsonl` (premissa assumida: 10_000 eventos em janela de 24 h) substitui o S3 no desenvolvimento e é carregado **somente quando a tabela está vazia**.

O GET agrega S/F no Postgres (`GROUP BY pool_id`) e aplica Laplace/quase-empate em processo. Não lê o arquivo JSONL nem o S3. Sem cache de score e sem Redis.

O Compose sobe só **api + postgres**. A API fala com o Postgres na rede interna (`postgresql://pool:pool@postgres:5432/pool`). A porta **5432** também é publicada no host para IDE (`localhost:5432`, user/password/db `pool`). Arquivo: [compose.yaml](../../compose.yaml). Referência: [Compose file](https://docs.docker.com/reference/compose-file/).

## Consequências

- Reiniciar a API não recarrega o seed se já existirem linhas. Reset com `docker compose down -v`.
- Cliente no host (DBeaver, TablePlus, `psql`) usa `localhost:5432`. Dentro do container: `docker compose exec postgres psql -U pool -d pool`. Detalhes no [README](../../README.md).
- Linhas SPARK_EXECUTION_ERROR são gravadas para auditoria, mesmo sem entrar no score.
- **Produção (só texto):** subir N réplicas stateless da API contra um Postgres compartilhado. Essa é a história de escalabilidade de R4. Sem HPA, Redis, MinIO ou worker neste MVP. Pico de GET pode ser verificado localmente com k6 ([cenarios-de-teste.md](../cenarios-de-teste.md#3-teste-de-performance-k6)); não faz parte do runtime nem do CI.



## Alternativas

- Só arquivo: mais simples, mas as réplicas não compartilhariam um conjunto consistente de eventos (R4 mais fraco).
- Redis ou MinIO + worker: dois stores e um processo a mais. O ranking de N pools cabe em uma query mais memória.

