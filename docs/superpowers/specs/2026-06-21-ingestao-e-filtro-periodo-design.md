# Design — Correção da ingestão (BCB/IPEA→SIDRA) e filtro por período

Data: 2026-06-21
Status: aprovado (aguardando revisão do spec)

## Contexto / Problema

Ao rodar `python -m app.ingest`, quatro indicadores ficaram com 0 observações,
por **duas causas distintas**, confirmadas no `ingestao_log`:

| Série | Status | Causa |
|---|---|---|
| `bcb_432_selic`, `bcb_1_cambio` | erro **406** | A API BCB/SGS retorna `406 Not Acceptable` ao pedir a série inteira sem intervalo de datas. Séries grandes/diárias (câmbio diário, Selic) estouram o limite. As mensais menores (433/13762/5793) funcionam. |
| `ipea_pib_real_var`, `ipea_gini` | ok, 0 registros | O `codigo_fonte` (`PIB_real_var`, `GINI`) **não são SERCODIGO válidos** do IPEADATA; a API devolve `value: []`. |

Além disso, o filtro "Por ano" da UI **não filtra os gráficos**: o `ano` do
`number_input` só alimenta o payload do resumo de IA; os gráficos chamam
`observacoes_da_serie` (todas as observações). O usuário quer um **range**
(ex.: 2022–2025) que recorte gráficos **e** o resumo.

## Decisões tomadas (brainstorming)

1. O range filtra **gráficos + resumo de IA** (não só os gráficos).
2. O resumo do período usa **início vs fim + variação** (reaproveita a lógica de
   `construir_payload_mandato`/`comparacao`), não matriz ano-a-ano.
3. PIB real e Gini migram de IPEA para **IBGE/SIDRA** (fonte mais estável).
4. A aba "Por ano" é renomeada para **"Por período"**.

## Parte A — Ingestão

### A1. BCB (erro 406) — `app/fetchers/bcb.py`
- Adicionar `&dataInicial=dd/MM/yyyy&dataFinal=dd/MM/yyyy` à URL.
- Série diária (`bcb_1_cambio`): o BCB limita ~10 anos por requisição → buscar em
  **janelas de ≤10 anos** e concatenar as observações.
- Janela total: de 2003-01-01 (início do mandato mais antigo) até hoje.
- Séries mensais continuam funcionando (uma janela só basta), mas passam a usar o
  mesmo caminho com datas para robustez.

### A2. SIDRA — extensão para escolher variável — `app/fetchers/sidra.py` + `config/indicadores.yaml`
- Tabelas SIDRA podem ter **múltiplas variáveis**; `v/allxp` mistura séries. Hoje
  funciona só porque `sidra_6468_desemprego` é tabela de variável única.
- Adicionar campos **opcionais** ao indicador:
  - `variavel`: código da variável SIDRA (ex.: `"9808"`).
  - `classificacao`: trecho de classificação/categoria quando a tabela exigir
    (ex.: `"c<cod>/<categoria>"`).
- `SIDRAFetcher` monta a URL com `v/{variavel}` (e `/{classificacao}/` quando
  presente) e cai para `allxp` quando ausente → **não quebra o desemprego atual**.
- Trocar os dois indicadores IPEA por entradas IBGE:
  - PIB real (variação anual) → tabela das Contas Nacionais (variação de volume).
  - Gini → tabela do IBGE (PNAD Contínua, rendimento domiciliar per capita).
- **Ressalva:** os códigos exatos de tabela/variável serão **descobertos e
  validados batendo na API do SIDRA durante a implementação**; os escolhidos
  serão apresentados ao usuário para conferência (Gini tem versões diferentes).
- O `Indicador` (em `app/models.py`) ganha os campos opcionais `variavel` e
  `classificacao` (default `None`); o `config_loader` os repassa.

## Parte B — Filtro por período (UI) — `app/ui.py`, `app/payload.py`, `app/db.py`

### B1. UI — slider de intervalo
- Substituir `st.number_input("Ano")` por
  `ano_ini, ano_fim = st.slider("Período", min_value=..., max_value=..., value=(2022, 2025))`.
- min/max derivados dos mandatos; default nos últimos ~4 anos.
- Renomear a aba `"Por ano"` → `"Por período"`.

### B2. Gráficos filtrados pelo range
- Filtrar observações por `data` entre `ano_ini-01-01` e `ano_fim-12-31` antes de
  plotar, reaproveitando/adaptando a query por intervalo já existente em
  `app/db.py` (linhas ~315/325).

### B3. Resumo de IA por período — `app/payload.py`
- Nova função `construir_payload_periodo(conn, indicadores, ano_ini, ano_fim)` que,
  por indicador, pega o valor no início e no fim e calcula a variação,
  reaproveitando a lógica de período de `construir_payload_mandato`/`comparacao`.
- Resultado conceitual: "começou em X (ano_ini) → terminou em Y (ano_fim),
  variação Z%".

### B4. Cache/histórico do resumo
- `descrever_payload` deve mapear o novo payload de período para
  `tipo="periodo"`, `identificador="{ano_ini}-{ano_fim}"`, evitando colisão de
  cache com o payload de ano único antigo.

## Testes (TDD, sem rede — LLMClient e HTTP mockados)
- BCB: dado um cliente mockado, verificar que a URL inclui `dataInicial/dataFinal`
  e que a série diária faz múltiplas requisições por janela e concatena.
- SIDRA: com `variavel`/`classificacao` presentes, a URL usa `v/{variavel}`; sem
  eles, mantém `allxp`.
- `construir_payload_periodo`: início/fim/variação corretos a partir de
  observações sintéticas; ausência de dados → marcado como faltante.
- `descrever_payload`: payload de período → `("periodo", "2022-2025")`.
- UI: smoke via `streamlit.testing.v1.AppTest` — 0 exceções, aba "Por período"
  renderiza com o slider.

## Fora de escopo (YAGNI)
- Resumo de IA com matriz ano-a-ano.
- Refatoração de fetchers não citados (Tesouro, Câmara, Senado).
- Cache de `raw/` por janela (a concatenação acontece em memória).
