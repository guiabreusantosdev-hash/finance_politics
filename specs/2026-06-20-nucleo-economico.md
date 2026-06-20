# Spec — Núcleo Econômico (Spec 1)

> Ferramenta **pessoal** de pesquisa para avaliar a performance de governos do Brasil,
> com o coração na **camada de IA que escreve resumos factuais** a partir de dados já
> calculados. Cobre os resumos "situação por ano/mandato" (#1) e "comparação entre
> governos" (#3). A camada legislativa/eleitoral (#2) é um spec futuro.
>
> Stack: Python 3.12 + Streamlit + SQLite + Plotly, com a IA via **assinatura do
> Claude Code** (Agent SDK / headless) atrás de uma interface trocável.

## Job To Be Done (JTBD)

Como pesquisador analisando governos brasileiros, eu quero um app local que ingere
indicadores econômicos/fiscais/sociais oficiais, calcula derivações de forma
determinística e gera **resumos factuais em linguagem natural** (por ano, por mandato e
comparando mandatos), para entender e comparar a performance de governos sem precisar
montar planilhas à mão e sem risco de alucinação numérica.

## Princípio inegociável

**O LLM nunca calcula números.** O backend computa tudo (variações, 12m, médias por ano,
deltas entre mandatos) e entrega ao modelo um payload estruturado; o modelo apenas
**redige** o texto factual, citando os valores que recebeu. Todo número no texto tem que
existir no payload.

---

## Arquitetura (camadas com fronteiras claras)

```
APIs públicas (BCB, IBGE/SIDRA, IPEA, Tesouro)
        │
        ▼
[1] Ingestão (ETL)  ──grava JSON bruto──▶  raw/
        │  normaliza
        ▼
[2] Armazenamento (SQLite): series │ observacoes (long) │ ingestao_log
        │
        ▼
[3] Cálculo (determinístico, puro): variações, 12m, médias/ano, deltas/mandato
        │
        ▼
[4] Payload builder → PayloadAno / PayloadComparacao (DTOs Pydantic)
        │
        ▼
[5] Camada de IA (LLMClient → Claude Code): payload → ResumoFactual (validado)
        │
        ▼
[6] UI (Streamlit): gráficos (Plotly) + resumos + seletor ano/mandato/comparação
```

Camadas transversais:
- **Config** (`config/`): registro de indicadores e definição de mandatos (YAML).
- **Verificação:** guard de factualidade determinístico (camadas 3–4) + subagente-juiz
  (LLM-as-judge) na camada 5.

Dados fluem numa direção só; o LLM fica no fim, recebendo números já calculados.

---

## Componentes e decisões

### [1] Ingestão (ETL)
- Um **fetcher por fonte** (`fetch_bcb`, `fetch_sidra`, `fetch_ipea`, `fetch_tesouro`),
  cada um implementando `Fetcher.fetch(serie) -> list[Observacao]`.
- Bibliotecas: `python-bcb`, `sidrapy`, `ipeadatapy`; fallback `httpx` cru se um wrapper
  falhar.
- **JSON bruto** gravado em `raw/<fonte>/<serie>_<timestamp>.json` **antes** de normalizar.
- **Resiliência:** retry com backoff exponencial + timeout; fonte fora do ar → usa o
  último `raw/` e marca no `ingestao_log`; uma série quebrada não derruba o pipeline.
- **Idempotência:** `upsert` por `(serie_id, data)`.
- Disparo manual: `python -m app.ingest`. Agendamento (cron) **fora de escopo**.

### [2] Armazenamento — esquema SQLite (long format)
```
series
  id            TEXT PK      -- ex.: "bcb_432_selic"
  fonte         TEXT         -- BCB | IBGE | IPEA | TESOURO
  codigo_fonte  TEXT         -- código nativo ("432", tabela SIDRA "1737")
  nome          TEXT         -- "Meta Selic"
  unidade       TEXT         -- "% a.a.", "R$ milhões", "índice"
  periodicidade TEXT         -- mensal | trimestral | anual
  eixo          TEXT         -- macro | fiscal | social

observacoes
  serie_id      TEXT FK→series.id
  data          DATE         -- 1º dia do período
  valor         REAL
  PK (serie_id, data)

ingestao_log
  serie_id, executado_em, status, n_registros, erro
```

### [3] Cálculo (determinístico, puro — `app/calculo.py`)
- `valor_no_periodo(serie, ano)` — agrega conforme periodicidade; o método é declarado na
  config do indicador (`metodo_anual: fim_periodo | media | acumulado_12m`). Sem heurística
  mágica.
- `variacao(serie, de, até)` — variação % entre dois pontos.
- `resumo_ano(ano)` → `{eixo: {indicador: {valor, unidade, fonte, data_ref}}}`.
- `resumo_mandato(nome)` → indicadores início/fim + variação no período.
- `comparacao(mandato_a, mandato_b)` → por indicador: valores de A e B + delta + unidade +
  fonte.
- Dado faltante → `None` explícito (nunca interpolado). Dado preliminar/revisado é marcado
  quando a fonte sinaliza.

### [4] Payload builder (`app/payload.py`)
- `PayloadAno(ano, indicadores=[{eixo, nome, valor, unidade, fonte, data_ref}], faltantes=[...])`
- `PayloadComparacao(mandato_a, mandato_b, deltas=[{nome, valor_a, valor_b, delta, unidade, fonte}])`

### [5] Camada de IA (`app/resumo.py`, `app/guard.py`, `app/judge.py`)
- **Interface única** `LLMClient.gerar(prompt, schema) -> dict`, com implementação
  `ClaudeCodeClient` usando a **assinatura do Claude Code** (Agent SDK, fallback
  `claude -p --output-format json` via subprocess). Trocar para Messages API no futuro =
  outra implementação, sem mexer no resto.
- **Saída estruturada** garantida por validação Pydantic + retry (re-pede até N vezes se o
  JSON não bater no schema; persistindo, falha explícita).
  ```
  ResumoFactual(
    paragrafos_por_eixo: {macro: str, fiscal: str, social: str},
    afirmacoes: [{texto, valor_citado, fonte}]
  )
  ```
- **Prompt do sistema** fixa: tom factual, sem juízo de valor, sem causação especulativa,
  citar fonte por afirmação, dizer "sem dado disponível" para `faltantes`.
- **Verificação em duas camadas:**
  1. **Guard de factualidade (determinístico, roda no loop, sem rede — `app/guard.py`):**
     todo `valor_citado` casa (com tolerância de arredondamento) com um valor do payload; e
     todo número no texto dos parágrafos está em `afirmacoes`/payload. Falhou → resumo
     **rejeitado**.
  2. **Subagente-juiz (LLM-as-judge — `app/judge.py`):** recebe `(payload, resumo)` e
     devolve `{ancorado, neutro, numeros_fora_do_payload, observacoes}`. Pega viés de tom e
     causação implícita. Roda como passo de verificação, não a cada iteração do loop.
- **Chave/credencial:** assinatura via Claude Code (sem API key no repo). Se algum dia usar
  API key, vai por env (`ANTHROPIC_API_KEY`), validada na inicialização.

### [6] UI (`app/ui.py`, Streamlit) — três abas
1. **Por ano** — seletor de ano → gráficos Plotly (cada um com fonte + unidade + data da
   última atualização) + resumo factual abaixo.
2. **Por mandato** — seletor de mandato → indicadores início/fim + variação + resumo.
3. **Comparação** — dois mandatos → tabela de deltas lado a lado + gráficos sobrepostos +
   resumo comparativo.
- Resumo de IA visualmente separado ("resumo gerado por IA a partir dos dados acima");
  botão "regenerar resumo"; dado faltante aparece como "sem dado" no gráfico e no texto.

---

## Configuração

### `config/indicadores.yaml` (conjunto inicial — balanceado)
- **Macro:** PIB real (variação), IPCA (12m), desemprego (PNAD), Selic, câmbio R$/US$.
- **Fiscal:** Dívida Bruta/PIB (DBGG), resultado primário.
- **Social:** Gini, IDH-M (ou pobreza) — séries anuais do IPEA.
- Cada indicador declara: `id, fonte, codigo_fonte, nome, unidade, periodicidade, eixo,
  metodo_anual`. Adicionar série nova = editar config, não código.
- **Recorte temporal:** 2003 → presente.

### `config/mandatos.yaml`
```yaml
- nome: "Lula 1";      inicio: 2003-01-01; fim: 2006-12-31
- nome: "Lula 2";      inicio: 2007-01-01; fim: 2010-12-31
- nome: "Dilma 1";     inicio: 2011-01-01; fim: 2014-12-31
- nome: "Dilma/Temer"; inicio: 2015-01-01; fim: 2018-12-31
- nome: "Bolsonaro";   inicio: 2019-01-01; fim: 2022-12-31
- nome: "Lula 3";      inicio: 2023-01-01; fim: 2026-12-31
```
(Datas ajustáveis; o recorte 2015–2018 é uma escolha revisável.)

### Modelo de IA
- Configurável; default = melhor qualidade disponível via assinatura do Claude Code.

---

## Tratamento de erros (explícito por camada)
- **Ingestão:** fonte fora → último `raw/` + marca `ingestao_log`; não derruba o pipeline.
- **Cálculo:** dado faltante → `None`, nunca interpolado silenciosamente.
- **IA:** JSON inválido → retry; estoura → erro explícito na UI, gráficos continuam visíveis.
- **Guard falha:** resumo rejeitado (não exibido como válido), UI sinaliza.

---

## Critérios de aceitação (verificáveis por máquina — backpressure do Ralph)
- [ ] `pytest` verde: fetchers (HTTP mockado com fixtures de JSON bruto real),
      normalização/upsert (SQLite em memória), todas as funções de cálculo (séries-fixture
      com valores conhecidos).
- [ ] Guard de factualidade: passa em resumo fiel; **rejeita** resumo com número fora do
      payload (teste de alucinação proposital).
- [ ] `LLMClient` mockado nos testes — zero chamadas reais (assinatura ou API) no loop.
- [ ] Validação Pydantic de `PayloadAno`, `PayloadComparacao`, `ResumoFactual`.
- [ ] Typecheck (pyright) e lint (ruff) limpos.
- [ ] Smoke E2E (validação manual única, fora do loop): ingestão real de ≥8 séries → SQLite
      populado → uma página Streamlit renderiza gráficos + um resumo coerente e
      factualmente correto.

---

## Fora de escopo (specs futuros)
- Camada legislativa/eleitoral — resumos de candidato/parlamentar (#2: Câmara, Senado, TSE).
- Agendamento automático (cron / GitHub Actions).
- PostgreSQL / TimescaleDB / BigQuery.
- Comparação internacional (World Bank, OWID, IMF).
- Deploy / uso público / autenticação.

---

## Notas / decisões
- **Stack para o `AGENTS.md`:** Python 3.12 · `uv` · pytest · ruff · pyright · streamlit ·
  plotly · python-bcb / sidrapy / ipeadatapy · claude-agent-sdk.
- Códigos de série do BCB e tabelas do SIDRA podem mudar de versão — **confirmar cada
  código/tabela no portal oficial** antes de codar (ver `compass_artifact_*.md`, Eixo 1).
- As APIs públicas brasileiras têm instabilidade e limites conhecidos (sobretudo SIDRA) — a
  arquitetura assume falhas como normais.
- Referência de fontes, códigos e endpoints: `compass_artifact_*.md` (pesquisa de base).
