# ADR 1 — FastAPI + uvicorn

## Status

Aceito.

## Contexto

R1 exige Python > 3.9 e um GET que devolve um pool. R2 permite qualquer framework se o racional estiver documentado. R5 pede documentação do endpoint.

## Decisão

Usar **FastAPI** servido por **uvicorn**, com `requires-python >=3.10`.

O Pydantic valida os query params (enum `category`, `min_vcpu`/`min_memory` ≥ 0) e o FastAPI mapeia essas falhas para **422**. OpenAPI/Swagger é gerado a partir dos mesmos models, o que cobre parte de R5 sem um arquivo de schema separado.

## Consequências

- `/docs` fica disponível no desenvolvimento.
- A validação dos filtros vive na assinatura da rota, não em parsing ad-hoc.
- O model HTTP 200 tem um único campo: `pool_id`.

## Alternativas

- Flask: menor, mas OpenAPI seria trabalho extra (falha a parte “documentação sem trabalho extra” de R5).
- Django: superfície grande demais para um GET.
