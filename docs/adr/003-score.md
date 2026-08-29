# ADR 3 — Score Laplace e o significado de cada reason

## Status

Aceito.

## Contexto

A API ranqueia **disponibilidade de capacidade spot**, não qualidade do job. A única evidência são eventos de término com `status` e `reason`. Argmax puro em todo GET com o mesmo filtro manda 100% dos jobs para o mesmo pool (efeito manada) antes de qualquer evento novo chegar.

## Decisão

Para cada `pool_id`, usando **todos** os eventos do seed carregados (sem janela temporal, sem decaimento):

- `S` = contagem de SUCCESS
- `F` = SPOT_INSTANCE_TERMINATION + TIMED_OUT (peso 1 cada)
- SPARK_EXECUTION_ERROR é persistido e **não** entra em `S` nem em `F`
- `score = (S + 1) / (S + F + 2)`

Entre os pools que passam nos filtros HTTP:

1. `S*` = maior score
2. Conjunto de quase-empate = pools com `score >= S* - 0,05`
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

Argmax concentra todos os GETs iguais no nº 1. A margem espalha só quando o score **não distingue**. No seed, `r6.xlarge` em `us-east-1a` lidera e `us-east-1b` fica dentro de 0,05: o GET sem filtro sorteia. Com `?az=us-east-1a` o conjunto tem um membro e o id é estável.

Não há teto de jobs/s: se só um pool é claramente melhor, concentrar é o correto.

## Consequências

- HTTP 200 devolve só `pool_id`. Score, S, F, `argmax_pool_id`, `near_tie`, filtros e runner-up vão para o **log**.
- A agregação S/F corre **em cada GET**, no SQL (`GROUP BY pool_id`). Filtro e sorteio de quase-empate usam o mapa de ~N pools em memória.
- Réplicas leem o mesmo Postgres; com quase-empate podem devolver ids diferentes no mesmo filtro.
- A margem `0,05` é config de produto (cinco pontos de Laplace).

## Alternativas recusadas

Wilson lower bound, softmax (temperatura para calibrar), cooldown, inflight, meia-vida, janela de 4h.
