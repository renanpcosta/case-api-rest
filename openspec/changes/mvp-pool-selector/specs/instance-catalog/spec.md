## ADDED Requirements

### Requirement: Catálogo estático no repositório

O sistema SHALL ler `data/catalog.json` mapeando `instance_type` → `{category, vcpu, memory_gib}`. `category` MUST ser um de `memory`, `compute`, `general`, `storage`.

#### Scenario: Tipo conhecido resolve atributos

- **WHEN** o catálogo contém `r6.xlarge` com category `memory`, vcpu e memory_gib
- **THEN** filtros que dependem desses campos usam esses valores

#### Scenario: Tipo ausente do catálogo não é candidato

- **WHEN** um `pool_id` tem instance type que não existe em `catalog.json`
- **THEN** esse pool é excluído do conjunto de candidatos

### Requirement: Filtros opcionais e combináveis

O sistema SHALL aplicar, todos opcionais e combináveis, os filtros: `category`, `instance_types` (lista), `min_vcpu` (inteiro), `min_memory` (inteiro, GiB), `az` (lista). MUST NÃO expor `families`, `exclude_az`, `job_id` nem `candidates`.

#### Scenario: Filtro por category

- **WHEN** o request informa `category=memory`
- **THEN** só pools cujo instance type tem category `memory` no catálogo permanecem

#### Scenario: Filtro por instance_types

- **WHEN** o request informa `instance_types=r6.xlarge,r6.2xlarge`
- **THEN** só pools desses tipos permanecem

#### Scenario: Filtro por min_vcpu

- **WHEN** o request informa `min_vcpu=8`
- **THEN** só pools cujo tipo tem `vcpu >= 8` permanecem

#### Scenario: Filtro por min_memory

- **WHEN** o request informa `min_memory=64`
- **THEN** só pools cujo tipo tem `memory_gib >= 64` permanecem

#### Scenario: Filtro por az

- **WHEN** o request informa `az=us-east-1a,us-east-1c`
- **THEN** só pools dessas AZs (extraídas do `pool_id`) permanecem

#### Scenario: Filtros combinados são interseção

- **WHEN** o request informa `category=memory` e `az=us-east-1a`
- **THEN** o candidato precisa satisfazer os dois filtros
