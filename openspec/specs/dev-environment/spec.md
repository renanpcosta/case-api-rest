# Dev Environment Specification

## Purpose
Bootstrap local development, product docs, and CI so the API can be run and verified with a single command.

## Requirements

### Requirement: Um comando sobe a API na porta 5050

`make setup` SHALL preparar a máquina local: checar Python >= 3.10, Docker com Compose v2, `curl` e `make`; criar `.venv` com extras de dev; garantir `data/events.jsonl`; instalar k6 se estiver ausente (Homebrew; se não houver brew, avisar sem falhar); construir as imagens do compose. `make dev` SHALL, se as dependências do venv não atenderem o `pyproject.toml`, executar o setup; em seguida subir o compose com `api` e `postgres`, esperar o Postgres, criar o schema se necessário, carregar o seed versionado (`data/events.jsonl`, 10_000 eventos em 24 h) se a tabela estiver vazia, e expor a API em `http://localhost:5050`. MUST NÃO exigir Redis, MinIO nem worker.

#### Scenario: setup deixa lint e test prontos

- **WHEN** `make setup` conclui com sucesso
- **THEN** `.venv` tem ruff e pytest

#### Scenario: setup instala k6 se faltar

- **WHEN** `k6` não está no PATH e o Homebrew está disponível
- **THEN** `make setup` (ou `make dev`) instala o k6

#### Scenario: make dev instala se faltar e sobe a API

- **WHEN** `make dev` é o primeiro comando na máquina (venv ausente ou libs abaixo do `pyproject.toml`)
- **THEN** o setup roda antes do compose

#### Scenario: curl de aceite

- **WHEN** `make dev` concluiu com sucesso e o seed tem ao menos um evento válido
- **THEN** `curl http://localhost:5050/get-pools` devolve JSON com `pool_id`

### Requirement: Documentação mínima do case

O repositório SHALL conter: `README.md` (comando único, curl, premissas, como testar, CD em um parágrafo), `docs/adr/001-fastapi.md`, `docs/adr/002-postgres.md`, `docs/adr/003-score.md`, `docs/api.md` (rotas, params, 200/400/422/503, pares request/response, exemplo de log rico), `docs/cenarios-de-teste.md` (pytest, filtros, k6: como instalar, como rodar, como ler o relatório, exemplos de resultado, verificação de log).

#### Scenario: README documenta o comando único

- **WHEN** um leitor abre `README.md`
- **THEN** encontra `make dev` como comando único de subida e o curl de aceite na porta 5050

### Requirement: CI com ruff e pytest

O repositório SHALL ter `.github/workflows/ci.yml` rodando ruff e pytest no PR. MUST NÃO incluir matriz de versões, Trivy, k6, mutation testing nem coverage-gate.

#### Scenario: PR dispara lint e teste

- **WHEN** um PR é aberto
- **THEN** o workflow CI executa ruff e pytest
