# Ajustes UI, Ministros e Legislativo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir o gráfico de PIB na aba "Por período", popular os ministros de todos os governos, adicionar legenda EC/LC/LO/MP e filtros (tipo + tema) na aba Legislativo.

**Architecture:** Duas funções puras novas em módulos sem Streamlit (`app/calculo.py`, `app/legislativo.py`) carregam a lógica testável; `app/ui.py` apenas consome. Dados de ministros são inseridos no `config/ministros.yaml` (fonte manual, sem API). Tipo e tema das leis já existem no banco (`Lei.tipo`, tabela `lei_temas`) — só faltam expor.

**Tech Stack:** Python 3.12, uv, Streamlit, Plotly (`plotly.graph_objects`), Pydantic, SQLite, pytest, ruff.

## Global Constraints

- Rodar tudo via `uv run ...` (ex.: `uv run pytest -q`).
- Toda entrada de ministro exige `fonte` (URL verificável); nunca inventar dado factual — Wikipedia é aceitável (padrão das entradas atuais). Respeitar o guard de factualidade do projeto.
- Funções puras (sem `import streamlit`) ficam em `app/calculo.py` / `app/legislativo.py`; `app/ui.py` só orquestra.
- Testes de fiação da UI seguem o padrão existente em `tests/test_ui_smoke.py` (inspeção de `inspect.getsource`).
- `Indicador.periodicidade` já existe (`app/models.py:26`) com valores `"mensal" | "trimestral" | "anual" | "diaria"`. Não alterar o modelo.
- Commits pequenos e frequentes, um por task.

---

### Task 1: `tipo_grafico` — escolher barras para séries anuais

**Files:**
- Modify: `app/calculo.py` (adicionar função no fim do arquivo)
- Test: `tests/test_calculo.py`

**Interfaces:**
- Consumes: `Indicador` de `app/models.py` (campo `periodicidade`).
- Produces: `tipo_grafico(ind: Indicador) -> str` retornando `"barras"` se `ind.periodicidade == "anual"`, senão `"linha"`.

- [ ] **Step 1: Write the failing test**

Adicionar ao fim de `tests/test_calculo.py` (o helper `_ind` já existe no arquivo e aceita `periodicidade`):

```python
from app.calculo import tipo_grafico


def test_tipo_grafico_anual_vira_barras():
    assert tipo_grafico(_ind("fim_periodo", "anual")) == "barras"


def test_tipo_grafico_mensal_vira_linha():
    assert tipo_grafico(_ind("media", "mensal")) == "linha"


def test_tipo_grafico_diaria_vira_linha():
    assert tipo_grafico(_ind("fim_periodo", "diaria")) == "linha"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calculo.py::test_tipo_grafico_anual_vira_barras -v`
Expected: FAIL — `ImportError: cannot import name 'tipo_grafico'`.

- [ ] **Step 3: Write minimal implementation**

Adicionar ao fim de `app/calculo.py`:

```python
def tipo_grafico(ind: Indicador) -> str:
    """Séries anuais têm poucos pontos; barras evitam o 'ponto solto' de uma linha."""
    return "barras" if ind.periodicidade == "anual" else "linha"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_calculo.py -q`
Expected: PASS (todos, incluindo os 3 novos).

- [ ] **Step 5: Commit**

```bash
git add app/calculo.py tests/test_calculo.py
git commit -m "feat: tipo_grafico escolhe barras para indicadores anuais"
```

---

### Task 2: `grafico_barras` + fiação da aba "Por período"

**Files:**
- Modify: `app/ui.py` (novo helper após `grafico_serie` na linha 27; loop da aba `aba_ano` linhas 63-69)
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: `tipo_grafico` (Task 1), `grafico_serie` (existente), `observacoes_entre` (existente).
- Produces: `grafico_barras(obs: list[Observacao], titulo: str, unidade: str, fonte: str) -> go.Figure` (usa `go.Bar`, mesmo layout de título de `grafico_serie`).

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_ui_smoke.py`:

```python
def test_grafico_barras_usa_bar_e_titulo():
    from app.ui import grafico_barras

    fig = grafico_barras(_obs(), titulo="PIB", unidade="%", fonte="IBGE")
    d = fig.to_dict()
    assert d["data"][0]["type"] == "bar"
    assert "PIB" in d["layout"]["title"]["text"]
    assert "IBGE" in d["layout"]["title"]["text"]


def test_ui_aba_por_periodo_usa_tipo_grafico_e_aviso_sem_dados():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "tipo_grafico" in src
    assert "grafico_barras" in src
    assert "sem dados no período" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_grafico_barras_usa_bar_e_titulo -v`
Expected: FAIL — `ImportError: cannot import name 'grafico_barras'`.

- [ ] **Step 3: Write the helper**

Em `app/ui.py`, após `grafico_serie` (linha 27), adicionar:

```python
def grafico_barras(obs: list[Observacao], titulo: str, unidade: str, fonte: str) -> go.Figure:
    df = serie_para_df(obs)
    fig = go.Figure(go.Bar(x=df["data"], y=df["valor"]))
    fig.update_layout(title=f"{titulo} ({unidade}) — fonte: {fonte}")
    return fig
```

- [ ] **Step 4: Wire the tab**

Em `app/ui.py`, dentro de `main()`, importar `tipo_grafico` junto dos outros imports de `app.calculo` — se não houver import de `app.calculo` em `main()`, adicionar a linha `from app.calculo import tipo_grafico` no bloco de imports de `main()` (após linha 33). Depois substituir o loop atual (linhas 63-69):

```python
        for ind in indicadores:
            obs = observacoes_entre(conn, ind.id, data_ini, data_fim)
            if not obs:
                st.info(f"{ind.nome}: sem dados no período selecionado")
                continue
            fabrica = grafico_barras if tipo_grafico(ind) == "barras" else grafico_serie
            st.plotly_chart(
                fabrica(obs, ind.nome, ind.unidade, ind.fonte),
                width="stretch", key=f"periodo_{ind.id}",
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui_smoke.py -q`
Expected: PASS (incluindo os 2 novos).

- [ ] **Step 6: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: aba Por periodo usa barras p/ anuais e avisa quando nao ha dados"
```

---

### Task 3: `filtrar_leis` — filtro puro por tipo e tema

**Files:**
- Modify: `app/legislativo.py` (adicionar função no fim)
- Test: `tests/test_legislativo.py`

**Interfaces:**
- Consumes: `Lei` de `app/models.py`.
- Produces: `filtrar_leis(leis: list, temas_por_lei: dict, tipos_sel: list[str], temas_sel: list[str]) -> list` — mantém `lei` se (`tipos_sel` vazio **ou** `lei.tipo in tipos_sel`) **e** (`temas_sel` vazio **ou** interseção não vazia entre `temas_por_lei.get(lei.id, [])` e `temas_sel`). `temas_por_lei` mapeia `lei.id -> list[str]`.

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_legislativo.py` (o arquivo já importa `datetime` e `Lei`):

```python
from app.legislativo import filtrar_leis


def _leis():
    return [
        Lei(id="a", tipo="LO", numero="1", ano=2023, data=datetime.date(2023, 1, 1), ementa="e", url="u"),
        Lei(id="b", tipo="MP", numero="2", ano=2023, data=datetime.date(2023, 2, 1), ementa="e", url="u"),
        Lei(id="c", tipo="EC", numero="3", ano=2023, data=datetime.date(2023, 3, 1), ementa="e", url="u"),
    ]


_TEMAS = {"a": ["Saúde"], "b": ["Trabalho e Emprego", "Economia"], "c": []}


def test_filtrar_leis_sem_filtros_retorna_tudo():
    assert len(filtrar_leis(_leis(), _TEMAS, [], [])) == 3


def test_filtrar_leis_por_tipo():
    r = filtrar_leis(_leis(), _TEMAS, ["LO", "EC"], [])
    assert [x.id for x in r] == ["a", "c"]


def test_filtrar_leis_por_tema():
    r = filtrar_leis(_leis(), _TEMAS, [], ["Saúde"])
    assert [x.id for x in r] == ["a"]


def test_filtrar_leis_tipo_e_tema_intersecao():
    r = filtrar_leis(_leis(), _TEMAS, ["MP"], ["Economia"])
    assert [x.id for x in r] == ["b"]


def test_filtrar_leis_tema_sem_correspondencia_exclui_lei_sem_temas():
    r = filtrar_leis(_leis(), _TEMAS, [], ["Saúde"])
    assert all(x.id != "c" for x in r)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_legislativo.py::test_filtrar_leis_sem_filtros_retorna_tudo -v`
Expected: FAIL — `ImportError: cannot import name 'filtrar_leis'`.

- [ ] **Step 3: Write minimal implementation**

Adicionar ao fim de `app/legislativo.py`:

```python
def filtrar_leis(leis, temas_por_lei, tipos_sel, temas_sel):
    def ok(lei):
        if tipos_sel and lei.tipo not in tipos_sel:
            return False
        if temas_sel and not (set(temas_por_lei.get(lei.id, [])) & set(temas_sel)):
            return False
        return True

    return [lei for lei in leis if ok(lei)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_legislativo.py -q`
Expected: PASS (incluindo os 5 novos).

- [ ] **Step 5: Commit**

```bash
git add app/legislativo.py tests/test_legislativo.py
git commit -m "feat: filtrar_leis filtra leis por tipo e tema"
```

---

### Task 4: Aba Legislativo — legenda EC/LC/LO/MP + filtros + coluna de temas

**Files:**
- Modify: `app/ui.py` (bloco `with aba_leg:`, ~linhas 165-197)
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: `filtrar_leis` (Task 3), `leis_no_mandato`/`vetos_no_mandato` (existentes), `temas_de` de `app.db` (existente), `construir_payload_legislativo` (existente, expõe `payload_l.por_tema: dict`).
- Produces: nenhuma nova API pública (só UI).

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_ui_smoke.py`:

```python
def test_ui_legislativo_tem_legenda_e_filtros():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    # legenda dos tipos
    assert "Emenda Constitucional" in src
    assert "Lei Complementar" in src
    assert "Lei Ordinária" in src
    assert "Medida Provisória" in src
    # filtros e temas
    assert "filtrar_leis" in src
    assert "st.multiselect" in src
    assert "temas_de" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_ui_legislativo_tem_legenda_e_filtros -v`
Expected: FAIL — asserts não encontram os termos no source.

- [ ] **Step 3: Reescrever o bloco `with aba_leg:`**

Substituir o corpo atual de `with aba_leg:` (linhas ~165-197) por:

```python
    with aba_leg:
        from app.db import temas_de
        from app.legislativo import (
            filtrar_leis,
            leis_no_mandato,
            vetos_no_mandato,
        )
        from app.payload import construir_payload_legislativo

        nome_l = st.selectbox("Mandato", [m.nome for m in mandatos], key="mand_leg")
        mandato_l = next(m for m in mandatos if m.nome == nome_l)
        payload_l = construir_payload_legislativo(conn, mandato_l)

        with st.expander("O que significam EC, LC, LO e MP?"):
            st.markdown(
                "- **EC** — Emenda Constitucional (altera a Constituição; quórum de 3/5).\n"
                "- **LC** — Lei Complementar (regula matéria que a Constituição exige; maioria absoluta).\n"
                "- **LO** — Lei Ordinária (lei comum; maioria simples).\n"
                "- **MP** — Medida Provisória (editada pelo Executivo com força de lei imediata; "
                "precisa ser convertida em lei pelo Congresso)."
            )

        c1, c2 = st.columns(2)
        c1.metric("Leis sancionadas", payload_l.total_leis)
        c2.metric("Vetos", payload_l.total_vetos)
        if payload_l.por_tipo:
            st.bar_chart(pd.DataFrame(
                {"tipo": list(payload_l.por_tipo), "n": list(payload_l.por_tipo.values())}
            ).set_index("tipo"))
        if payload_l.por_tema:
            st.bar_chart(pd.DataFrame(
                {"tema": list(payload_l.por_tema), "n": list(payload_l.por_tema.values())}
            ).set_index("tema"))

        st.subheader("Leis")
        leis = leis_no_mandato(conn, mandato_l)
        temas_por_lei = {x.id: temas_de(conn, x.id) for x in leis}
        tipos_sel = st.multiselect("Tipo", ["EC", "LC", "LO", "MP"], key="filtro_tipo")
        temas_sel = st.multiselect(
            "Tema", sorted(payload_l.por_tema.keys()), key="filtro_tema"
        )
        leis_f = filtrar_leis(leis, temas_por_lei, tipos_sel, temas_sel)
        if leis_f:
            st.dataframe(pd.DataFrame([
                {
                    "tipo": x.tipo, "número": x.numero, "data": x.data,
                    "temas": ", ".join(temas_por_lei.get(x.id, [])),
                    "ementa": x.ementa, "url": x.url,
                }
                for x in leis_f
            ]))
        else:
            st.info("Nenhuma lei para os filtros selecionados.")

        st.subheader("Vetos")
        st.dataframe(pd.DataFrame([
            {"data": v.data, "tipo": v.tipo, "matéria": v.materia, "descrição": v.descricao}
            for v in vetos_no_mandato(conn, mandato_l)
        ]))

        st.subheader("Resumo legislativo")
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_l)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui_smoke.py -q`
Expected: PASS (incluindo `test_ui_tem_aba_legislativo` que já existia e o novo).

- [ ] **Step 5: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: aba Legislativo com legenda EC/LC/LO/MP e filtros por tipo e tema"
```

---

### Task 5: Ministros — popular todos os governos + endurecer carregamento

**Files:**
- Modify: `config/ministros.yaml` (novas entradas por governo)
- Modify: `app/ui.py` (try/except em `carregar_ministros()`, linha ~109)
- Test: `tests/test_ministros.py`

**Interfaces:**
- Consumes: schema `Ministro` (`app/models.py:118`: `pasta, nome, inicio, fim, fonte`; `governo` herdado do bloco), `carregar_ministros` (existente).
- Produces: nenhuma nova API.

**Pesquisa factual (execução).** Para cada governo de `config/mandatos.yaml` (Lula 1, Lula 2, Dilma 1, Dilma/Temer, Bolsonaro, Lula 3) e cada uma das 5 pastas — **Educação, Casa Civil, Relações Exteriores, Justiça** (usar "Justiça e Segurança Pública" a partir de 2019, no bloco Bolsonaro) **e Secretaria-Geral** (da Presidência) — pesquisar o(s) titular(es) via WebSearch em fonte verificável (Wikipedia é aceitável, seguindo o padrão atual). Registrar `inicio`/`fim` alinhados à janela do governo; `fim: null` só para o titular vigente do governo atual (Lula 3). Incluir trocas principais dentro do mandato (múltiplas entradas na mesma pasta). Onde não houver fonte confiável, **não inventar** — marcar na revisão. **Apresentar a lista completa ao usuário para conferência antes do commit final.**

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_ministros.py` (usa a config real do projeto, não `tmp_path`):

```python
def test_config_real_tem_pastas_esperadas_por_governo():
    ms = carregar_ministros("config/ministros.yaml", "config/mandatos.yaml")
    esperadas = {
        "Educação", "Casa Civil", "Relações Exteriores", "Secretaria-Geral",
    }
    for governo in ["Lula 1", "Lula 2", "Dilma 1", "Dilma/Temer", "Bolsonaro", "Lula 3"]:
        pastas = {m.pasta for m in ministros_do_governo(ms, governo)}
        faltando = esperadas - pastas
        assert not faltando, f"{governo} sem pastas: {faltando}"
        # Justiça aparece com um dos dois nomes conforme a época
        assert any("Justiça" in p for p in pastas), f"{governo} sem pasta de Justiça"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ministros.py::test_config_real_tem_pastas_esperadas_por_governo -v`
Expected: FAIL — hoje só existe a pasta Fazenda/Economia por governo.

- [ ] **Step 3: Pesquisar e preencher `config/ministros.yaml`**

Para cada governo, adicionar os itens das 5 pastas ao bloco `ministros:` correspondente, no formato:

```yaml
- governo: "Lula 3"
  ministros:
    - pasta: "Fazenda"          # entrada existente — manter
      nome: "Fernando Haddad"
      inicio: 2023-01-01
      fim: null
      fonte: "https://pt.wikipedia.org/wiki/Fernando_Haddad"
    - pasta: "Casa Civil"
      nome: "<titular pesquisado>"
      inicio: <data ISO>
      fim: <data ISO ou null>
      fonte: "<URL verificável>"
    # ... Educação, Relações Exteriores, Justiça e Segurança Pública, Secretaria-Geral
```

Repetir para Lula 1, Lula 2, Dilma 1, Dilma/Temer, Bolsonaro (nesses, "Justiça"; em Bolsonaro e Lula 3, "Justiça e Segurança Pública"). Preservar as entradas de Fazenda/Economia já existentes.

- [ ] **Step 4: Endurecer o carregamento na UI**

Em `app/ui.py`, localizar a aba de ministros (`with aba_min:`) onde há `ministros = carregar_ministros()` (linha ~109) e envolver:

```python
        try:
            ministros = carregar_ministros()
        except Exception as e:  # noqa: BLE001 - queremos degradar a aba, não a app
            st.error(f"Falha ao carregar ministros: {e}")
            st.stop()
```

- [ ] **Step 5: Validar YAML e rodar testes**

Run: `uv run pytest tests/test_ministros.py -q`
Expected: PASS.

- [ ] **Step 6: Apresentar ao usuário para conferência factual**

Mostrar a tabela final (governo × pasta × nome × início × fim × fonte) e aguardar OK do usuário antes do commit.

- [ ] **Step 7: Commit**

```bash
git add config/ministros.yaml app/ui.py tests/test_ministros.py
git commit -m "feat: ministros das 5 pastas em todos os governos + carregamento defensivo na UI"
```

---

## Verificação final (após todas as tasks)

- [ ] `uv run pytest -q` — toda a suíte verde (124 anteriores + novos).
- [ ] `uv run ruff check .` — sem erros.
- [ ] `uv run streamlit run app/ui.py` e conferir manualmente:
  - **Por período:** PIB e Gini como barras; arrastar o slider para 2024–2026 mostra "PIB real (variação anual): sem dados no período selecionado" sem quebrar os demais gráficos.
  - **Ministros:** cada governo lista as 5 pastas novas além de Fazenda/Economia.
  - **Legislativo:** expander de legenda; multiselects de tipo e tema filtram a tabela; coluna "temas" presente; filtro sem resultado mostra aviso.

## Self-review (feita)

- **Cobertura do spec:** item 1 → Tasks 1-2; item 2 → Task 5; item 3 → Task 4 (legenda); item 4 → Tasks 3-4. Robustez do carregamento → Task 5. Testes e verificação e2e → seções finais. Sem lacunas.
- **Placeholders:** o único conteúdo "a preencher" é dado factual de ministros (Task 5), inerentemente de execução, com formato exato e gate de revisão — não é placeholder de código.
- **Consistência de tipos:** `tipo_grafico` (Task 1) usado em Task 2; `filtrar_leis(leis, temas_por_lei, tipos_sel, temas_sel)` (Task 3) chamado com os mesmos nomes/tipos em Task 4; `grafico_barras` assinatura idêntica a `grafico_serie`.
