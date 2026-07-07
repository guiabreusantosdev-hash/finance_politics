# Ajustes rápidos: Selic efetiva, gráfico de comparação, atribuição das pastas, UX de medidas

Data: 2026-07-07 (Spec 1 de 2)

## Contexto

Segunda leva de ajustes solicitada pelo usuário após uso real do app. São 6 itens; por
decisão do usuário eles foram **divididos em dois specs** — este (Spec 1) cobre os quatro
itens leves e independentes; a infraestrutura de ingestão pela UI (leis + wiki de ministros
+ histórico, com botões "atualizar o que falta"/"reimportar tudo") fica para o **Spec 2**,
num ciclo próprio. Decisões já tomadas para o Spec 2 (registradas aqui para continuidade):
wiki dos ministros traz **bio curta + foto**; os dois botões de ingestão **rodam direto**
(com spinner); ambos guardam histórico.

Este Spec 1 resolve: (1) falta a Selic efetiva (só existe a meta); (2) a aba Comparação só
mostra números, sem gráfico; (5) não há descrição do que cada pasta ministerial faz; (6) a
seção "Medidas aprovadas" aparece vazia sem explicação. (Itens 3 e 4 → Spec 2.)

## 1. Selic efetiva (item 1)

**Problema.** `config/indicadores.yaml` tem apenas `bcb_432_selic` = "Meta Selic" (série BCB
SGS 432, a taxa-meta do Copom). Não há a Selic **efetiva/realizada**.

**Solução.** Adicionar **um** indicador ao `config/indicadores.yaml`, seguindo o schema
existente (campos `id, fonte, codigo_fonte, nome, unidade, periodicidade, eixo, metodo_anual`):

```yaml
- id: bcb_1178_selic_efetiva
  fonte: BCB
  codigo_fonte: "1178"
  nome: Selic efetiva (anualizada)
  unidade: "% a.a."
  periodicidade: diaria
  eixo: macro
  metodo_anual: fim_periodo
```

Série SGS **1178** = "Taxa de juros - Selic anualizada base 252", em % a.a. — diretamente
comparável à Meta Selic. **Nenhuma mudança de código**: `app/fetchers/bcb.py` já monta a URL
SGS a partir de `codigo_fonte`, e a periodicidade `diaria` já dispara o janelamento de 10
anos existente. O indicador passa a aparecer automaticamente em todas as abas que iteram
`indicadores` (Por período, Por mandato, Comparação).

**Dado.** `finance.db` é local e gitignored; a série é populada rodando
`uv run python -m app.ingest` (rede BCB). Até a ingestão, a aba "Por período" já mostra
"sem dados no período selecionado" para o novo indicador (comportamento do Spec anterior).

**Fora de escopo.** Remover ou renomear a Meta Selic (fica como está, agora ao lado da efetiva).

## 2. Gráfico na aba Comparação (item 2)

**Problema.** `aba_comp` (`app/ui.py`) mostra só um `st.dataframe` dos deltas (valor_a,
valor_b por métrica). O usuário quer um gráfico. Cada métrica tem unidade própria (% a.a.,
R$/US$, % do PIB, índice), então **um** gráfico agrupando todas misturaria escalas.

**Solução.** Um **mini-gráfico por indicador** (barras: Mandato A vs Mandato B), cada um com
sua escala/unidade.
- Novo helper puro em `app/ui.py`:
  `grafico_comparacao_indicador(nome: str, unidade: str, valor_a: float, valor_b: float,
  rotulo_a: str, rotulo_b: str) -> go.Figure` — `go.Bar` com x=`[rotulo_a, rotulo_b]`,
  y=`[valor_a, valor_b]`, título `f"{nome} ({unidade})"`. Segue o estilo de `grafico_barras`.
- Na aba: iterar `payload_c.deltas`, **pular** os que têm `valor_a is None or valor_b is None`,
  e renderizar os gráficos em grade de 2 colunas (`st.columns(2)`), usando os nomes dos
  mandatos (`payload_c.mandato_a` / `payload_c.mandato_b`) como rótulos.
- **Manter** o `st.dataframe` de deltas abaixo dos gráficos (números exatos) e o resumo.

`DeltaIndicador` expõe `nome, valor_a, valor_b, delta, unidade, fonte`; `PayloadComparacao`
expõe `mandato_a, mandato_b, deltas` (`app/models.py`). Nenhuma mudança de payload/modelo.

## 3. Atribuição das pastas (item 5)

**Problema.** Não há descrição do que cada ministério (pasta) faz — em lugar nenhum do
config/código.

**Solução.**
- Novo `config/pastas.yaml`: mapa de `pasta → descrição` (1–2 linhas, tom neutro/factual)
  para as 8 pastas que aparecem em `config/ministros.yaml`: **Casa Civil, Economia, Fazenda,
  Educação, Justiça, Justiça e Segurança Pública, Relações Exteriores, Secretaria-Geral**.
  Formato simples (mapa YAML):
  ```yaml
  Casa Civil: "Coordena e integra a ação dos ministérios e assessora diretamente a Presidência."
  Fazenda: "Formula e executa a política econômica, fiscal e tributária do governo federal."
  # ... demais pastas
  ```
- Novo módulo `app/pastas.py` espelhando `app/config_loader.py`:
  `carregar_pastas(path: str = "config/pastas.yaml") -> dict[str, str]` — abre o YAML e
  retorna o dict (via `yaml.safe_load`). Sem modelo Pydantic novo (é um mapa string→string).
- Na aba Ministros (`app/ui.py`, `with aba_min:`): após a tabela de ministros, um
  `st.expander("O que faz cada pasta")` listando, para as pastas **presentes no governo
  selecionado** (`{m.pasta for m in do_gov}`), `**{pasta}** — {descrição}`. Pastas sem
  descrição no YAML são omitidas (defensivo com `.get`).

## 4. UX das medidas vazias (item 6)

**Problema.** A tabela `medidas` tem 0 linhas (estado esperado — nada foi gerado/aprovado).
A UI mostra apenas `st.caption("Nenhuma medida aprovada ainda.")` (`app/ui.py:145`), sem
explicar por quê nem como popular.

**Solução.** Trocar o `st.caption` por um `st.info` explicativo, por exemplo:
"Nenhuma medida aprovada ainda. Use **Sugerir medidas (IA)** abaixo para gerar rascunhos com
fonte e aprovar os que quiser — eles aparecerão aqui." **Sem mudança de lógica**; só o texto
e o componente (`st.caption` → `st.info`).

## Testes

- `grafico_comparacao_indicador(...)` — retorna `go.Figure` com um traço `bar`, dois valores
  em y, e título contendo o nome e a unidade.
- `carregar_pastas()` — carrega `config/pastas.yaml` e retorna um dict cobrindo as 8 pastas
  esperadas (chaves presentes, valores não vazios).
- Wiring por source-inspection (padrão de `tests/test_ui_smoke.py`): aba Comparação usa
  `grafico_comparacao_indicador`; aba Ministros tem o expander "O que faz cada pasta" e chama
  `carregar_pastas`; a mensagem nova de medidas está presente.
- Config: `carregar_indicadores()` inclui o id `bcb_1178_selic_efetiva`.
- Suíte atual (136 testes) continua verde.

## Verificação end-to-end

1. `uv run pytest -q` — verde; `uv run ruff check .` — limpo.
2. `uv run python -m app.ingest` — popula a Selic efetiva (e demais séries) no `finance.db` local.
3. `uv run streamlit run app/ui.py` e conferir:
   - Por período / Por mandato: "Selic efetiva (anualizada)" aparece ao lado da "Meta Selic".
   - Comparação: mini-gráficos de barras A vs B por indicador + tabela de deltas.
   - Ministros: expander "O que faz cada pasta" com as descrições das pastas do governo;
     seção de medidas mostra a mensagem explicativa quando vazia.

## Arquivos afetados

- `config/indicadores.yaml` — novo indicador Selic efetiva.
- `config/pastas.yaml` — novo arquivo (mapa pasta → descrição).
- `app/pastas.py` — novo módulo `carregar_pastas`.
- `app/ui.py` — helper `grafico_comparacao_indicador`; gráficos na aba Comparação; expander de
  pastas + `carregar_pastas` na aba Ministros; mensagem de medidas (`st.caption`→`st.info`).
- `tests/` — testes de `grafico_comparacao_indicador`, `carregar_pastas`, wiring e config.

## Follow-up (Spec 2, não incluído aqui)

Ingestão pela UI da camada legislativa (leis MP/LO/LC/EC) e da wiki dos ministros (bio+foto),
com botões "atualizar o que falta" e "reimportar tudo" (ambos diretos, com spinner) e histórico
de operações persistido. Exige: fetcher de Wikipedia, tabela `ministros` no banco + campos de
enriquecimento, tabela de histórico de runs, e wiring de botões nas abas Legislativo e Ministros.
