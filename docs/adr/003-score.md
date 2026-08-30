# ADR 3 — Score Laplace e o significado de cada reason

## Status

Aceito.

## Contexto

A API escolhe pool por **disponibilidade de capacidade spot**, não por qualidade do job. A evidência é o conjunto de eventos de término já carregados (`status` e `reason`): o GET não ingere evento novo e o score usa todos eles, sem janela.

No mesmo dado há três problemas: 

- `reason` mistura falha de pool e falha de aplicação; 
- a taxa crua `S/(S+F)` faz 1/1 vencer 950/1000; 
- argmax puro devolve sempre o mesmo `pool_id` quando dois scores não se distinguem.

## Decisão

Para cada `pool_id`, usando **todos** os eventos do seed carregados (sem janela temporal, sem decaimento):

- `S` = contagem de SUCCESS
- `F` = SPOT_INSTANCE_TERMINATION + TIMED_OUT (peso 1 cada)
- SPARK_EXECUTION_ERROR é persistido e **não** entra em `S` nem em `F`
- `score = (S + 1) / (S + F + 2)`

Entre os pools que passam nos filtros HTTP:

1. Melhor score = maior Laplace entre os candidatos
2. Conjunto de quase-empate = pools com `score >= melhor - 0,05`
3. Um membro → esse `pool_id`
4. Dois ou mais → sorteio **uniforme** (`random.choice`)

O ranking `(-score, pool_id)` ordena o conjunto e o log (`argmax_pool_id`). Não escolhe sozinho o HTTP quando há quase-empate.

### Por que SPARK_EXECUTION_ERROR não entra em S nem em F

Não mede o pool. É falha da aplicação (bug, dado ruim, erro no Spark). A instância pode ter estado saudável o tempo todo.

- Não entra em `F`: contar como falha do pool derrubaria uma AZ boa porque um job quebrado rodou lá, e o próximo job saudável seria empurrado para outro lugar.
- Não entra em `S`: o job não terminou com sucesso. Contar como sucesso inflaria a saúde do pool com uma execução que falhou.

Contraexemplo: um job com bug em `us-east-1a` não pode fazer a API parar de recomendar `1a`.

### Por que TIMED_OUT é falha do pool (peso 1)

Neste MVP um timeout é tratado como o pool não entregar capacidade a tempo. É regra de produto travada, não uma afirmação sobre o interno do Spark.

### Por que Laplace

Evidência escassa não pode vencer evidência abundante: **1/1 não vence 950/1000**. `(S+1)/(S+F+2)` é um prior Beta uniforme que faz isso sem intervalos de Wilson.

### Por que quase-empate 0,05 e não argmax

Argmax concentra todos os GETs iguais no nº 1 mesmo quando o Laplace não separa os pools. A margem espalha **só** nesse caso; se um pool é claramente melhor, concentrar é o correto. Não há teto de jobs/s nem “efeito manada” a corrigir com evento futuro: o seed é estático.

`0,05` não é constante solta. O score Laplace já vive em `[0, 1]`; a margem é cinco pontos percentuais **nessa mesma escala** (prior Beta uniforme), não temperatura de softmax nem z de Wilson. O passo canônico com F = 0 é 3 SUCCESS vs 2 SUCCESS: `(3+1)/(3+0+2) = 0,80` e `(2+1)/(2+0+2) = 0,75`, diferença exatamente 0,05 — a API não trata “um sucesso a mais” como ranking fechado. Com evidência abundante o mesmo 0,05 é um gap real (Laplace de 950/1000 vs ~900/1000), então o nº 1 vence sozinho. No seed, `r6.xlarge` em `us-east-1a` lidera e `us-east-1b` fica ~0,042 abaixo: o GET sem filtro sorteia. Com `?az=us-east-1a` o conjunto tem um membro e o id é estável.

## Consequências

- HTTP 200 devolve só `pool_id`. Score, S, F, `argmax_pool_id`, `near_tie`, filtros e runner-up vão para o **log**.
- A agregação S/F corre **em cada GET**, no SQL (`GROUP BY pool_id`). Filtro e sorteio de quase-empate usam o mapa de ~N pools em memória.
- Réplicas leem o mesmo Postgres; com quase-empate podem devolver ids diferentes no mesmo filtro.
- A margem `0,05` é config de produto: cinco pontos percentuais na escala do próprio Laplace.



## Alternativas recusadas

Wilson lower bound, softmax (temperatura para calibrar), cooldown, inflight, meia-vida, janela de 4h.