# Ajustes: gráfico PIB, ministros, legenda e filtros legislativos

Data: 2026-07-07

## Contexto

Quatro ajustes solicitados pelo usuário na UI Streamlit (`app/ui.py`) após uso real do app:

1. Na aba **"Por período"**, o gráfico de **PIB real (variação anual)** parece quebrado.
2. Os ministros parecem "não importados" — só a Fazenda aparece por governo.
3. Falta explicar o que são **EC, LC, LO e MP** na aba Legislativo.
4. Falta **filtrar** as leis por **tipo** e por **tema** (saúde, trabalho, etc.).

Investigação do código confirmou que (1) é efeito de dados esparsos, não bug; (2) é
ausência de dados no YAML, não falha de importação; (3) e (4) são features novas com
os dados já disponíveis. Objetivo: tornar a UI honesta com séries anuais, popular o
elenco ministerial completo e dar navegabilidade à camada legislativa.

## 1. Gráfico de PIB / indicadores anuais (aba "Por período")

**Problema.** O PIB é série **anual** que termina em 2023 (`config/indicadores.yaml`
`ibge_pib_real_var`, `periodicidade: anual`). O slider de `app/ui.py` (aba `aba_ano`,
linhas ~52-71) abre por padrão em 2023–2026. `observacoes_entre` devolve **1 ponto**
(2023) ou **0** para 2024+. Um `go.Scatter(mode="lines+markers")` com 1 ponto vira um
marcador solto; com 0 pontos o `if obs:` (linha ~65) **esconde** o gráfico
silenciosamente, enquanto os indicadores mensais/diários (dados até 2026) continuam
aparecendo — daí a impressão de "quebrado".

**Solução.**
- Novo helper `grafico_barras(obs, titulo, unidade, fonte) -> go.Figure` em `app/ui.py`,
  irmão do `grafico_serie` existente (linhas 23-27), usando `go.Bar`.
- Função **pura** `tipo_grafico(ind: Indicador) -> str` retornando `"barras"` quando
  `ind.periodicidade == "anual"`, senão `"linha"`. Fica em `app/calculo.py` (módulo de
  matemática determinística, sem dependência de Streamlit/Plotly → teste limpo).
  `Indicador.periodicidade` já existe em `app/models.py:26` — nenhuma mudança de modelo.
- No loop da aba "Por período": escolher o helper por `tipo_grafico(ind)`. Indicadores
  anuais (PIB, Gini) → barras (1 ponto já aparece); demais → linha (comportamento atual).
- Trocar o `if obs:` que oculta por: se vazio, `st.info(f"{ind.nome}: sem dados no período
  selecionado")`. Nada mais some sem aviso.
- Escopo: apenas a aba "Por período". O helper e a função ficam reutilizáveis.

**Fora de escopo.** Atualizar a ingestão para trazer PIB além de 2023 (é frescor de dados,
não este ajuste). Mudar a aba "Por mandato".

## 2. Ministros — todos os governos

**Problema.** `config/ministros.yaml` só tem 1 pasta por governo (Fazenda/Economia). O
loader (`app/ministros.py`) funciona; faltam dados. Ministros são 100% manuais via YAML
(não há API).

**Solução.**
- Pesquisar os titulares reais das 5 pastas em **cada** governo de `config/mandatos.yaml`
  (Lula 1, Lula 2, Dilma 1, Dilma/Temer, Bolsonaro, Lula 3):
  - **Educação**
  - **Casa Civil**
  - **Relações Exteriores**
  - **Justiça** (nome "Justiça e Segurança Pública" a partir de 2019, no governo Bolsonaro)
  - **Secretaria-Geral** (da Presidência)
- Para cada pasta em cada governo, listar o(s) titular(es) com `inicio`, `fim` (ou `null`
  para o titular atual do governo vigente) e `fonte` (URL verificável — Wikipedia é
  aceitável, seguindo o padrão das entradas atuais). O schema aceita **múltiplos titulares
  por pasta** quando houve troca no mandato; incluir as trocas principais.
- Datas alinhadas à janela de cada governo (mesma convenção das entradas atuais). Onde não
  houver fonte confiável para um período, **marcar explicitamente na revisão** em vez de
  inventar (respeita o guard de factualidade do projeto).
- Adicionar as entradas ao bloco correto de cada governo em `config/ministros.yaml`,
  respeitando o schema (`pasta`, `nome`, `inicio`, `fim`, `fonte`; `governo` herdado do bloco).

**Robustez.** Endurecer `app/ui.py:109` (`carregar_ministros()` sem try/except): envolver
em try/except e mostrar `st.error(...)` com a mensagem de validação, para que um YAML
inconsistente não derrube a aba inteira.

**Revisão.** Como é dado factual em volume, apresentar as entradas ao usuário para revisão
antes do commit.

## 3. Legenda EC/LC/LO/MP (aba Legislativo)

Inserir, na aba `aba_leg` (`app/ui.py` ~165-197), logo após o seletor de mandato (~linha
171), um `st.expander("O que significam EC, LC, LO e MP?")` com:

- **EC** — Emenda Constitucional (altera o texto da Constituição; quórum de 3/5).
- **LC** — Lei Complementar (regula matéria que a Constituição exige; maioria absoluta).
- **LO** — Lei Ordinária (lei comum; maioria simples).
- **MP** — Medida Provisória (editada pelo Executivo com força de lei imediata; precisa ser
  convertida em lei pelo Congresso).

## 4. Filtros no Legislativo (tipo + tema)

**Dados.** `Lei.tipo` já traz EC/LC/LO/MP (`app/models.py:156-163`, mapeados em
`app/fetchers/camara.py:13`). O tema já vem da API da Câmara e está em `lei_temas`
(N:N), acessível via `temas_de(conn, lei_id)` (`app/db.py:352`). `agregar_por_tema`
alimenta `payload_l.por_tema` por mandato (`app/payload.py:180`).

**Solução (na aba `aba_leg`).**
- Buscar as leis **uma vez** (`leis_no_mandato` hoje é chamado em duplicidade — via payload
  e via tabela; consolidar numa única leitura reutilizada).
- Montar `temas_por_lei: dict[lei_id, list[str]]` via `temas_de()` para as leis do mandato.
- `st.multiselect("Tipo", ["EC","LC","LO","MP"])` (vazio = todos).
- `st.multiselect("Tema", opcoes)` onde `opcoes = sorted(payload_l.por_tema.keys())` (temas do
  mandato; vazio = todos).
- Função **pura** `filtrar_leis(leis, temas_por_lei, tipos_sel, temas_sel) -> list[Lei]` em
  `app/legislativo.py`: mantém a lei se (`tipos_sel` vazio ou `lei.tipo in tipos_sel`) **e**
  (`temas_sel` vazio ou interseção não vazia entre `temas_por_lei[lei.id]` e `temas_sel`).
  Testável isoladamente.
- Adicionar coluna **"temas"** (`", ".join(...)`) à tabela de leis (`st.dataframe`).
- Estado vazio: se o filtro não retorna nada, `st.info("Nenhuma lei para os filtros
  selecionados.")`.

## Testes

- `tipo_grafico(ind)` — anual→"barras", mensal/diário→"linha".
- `filtrar_leis(...)` — sem filtros (retorna tudo), só tipo, só tema, tipo+tema, interseção
  vazia, lei sem temas.
- Carga de `config/ministros.yaml` — `carregar_ministros()` valida sem erro e retorna todas
  as pastas por governo (contagem esperada).
- Suíte atual (124 testes) continua verde.

## Verificação end-to-end

1. `uv run pytest -q` — verde.
2. `uv run streamlit run app/ui.py` e conferir manualmente:
   - Aba "Por período": PIB/Gini como barras; arrastar o slider para 2024–2026 mostra aviso
     "sem dados no período" no PIB, sem quebrar os demais gráficos.
   - Aba "Ministros": cada governo lista as 5 pastas novas + Fazenda/Economia.
   - Aba "Legislativo": expander de legenda visível; multiselects de tipo e tema filtram a
     tabela; coluna "temas" presente; estado vazio com aviso.

## Arquivos afetados

- `app/ui.py` — helper `grafico_barras`, `tipo_grafico`, escolha de gráfico + aviso na aba
  "Por período"; try/except em `carregar_ministros()`; expander de legenda; multiselects e
  coluna de temas na aba legislativa; leitura única das leis.
- `app/calculo.py` — `tipo_grafico`.
- `app/legislativo.py` — `filtrar_leis`.
- `config/ministros.yaml` — entradas das 5 pastas em cada governo.
- `tests/` — testes de `tipo_grafico`, `filtrar_leis`, carga de ministros.
