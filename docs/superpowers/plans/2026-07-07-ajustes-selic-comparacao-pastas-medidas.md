# Ajustes rápidos (Selic efetiva, gráfico comparação, pastas, UX medidas) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar a Selic efetiva, um gráfico de barras A×B na aba Comparação, descrições das pastas ministeriais, e uma mensagem explicativa quando não há medidas aprovadas.

**Architecture:** Três mudanças de config/dados (novo indicador YAML, novo `config/pastas.yaml`) + duas funções testáveis fora do Streamlit (`grafico_comparacao_indicador` em ui.py; `carregar_pastas` em novo módulo `app/pastas.py`) consumidas por `app/ui.py`, que só orquestra.

**Tech Stack:** Python 3.12, uv, Streamlit, Plotly (`plotly.graph_objects`), Pydantic, PyYAML, SQLite, pytest, ruff.

## Global Constraints

- Rodar tudo via `uv run ...` (ex.: `uv run pytest -q`).
- Funções puras/de dados (sem `import streamlit`) ficam em módulos próprios; `app/ui.py` só orquestra. Exceção: `grafico_comparacao_indicador` fica em `app/ui.py` junto de `grafico_serie`/`grafico_barras` (helpers Plotly já moram lá e não importam streamlit no escopo do módulo).
- Testes de fiação da UI seguem o padrão `inspect.getsource` de `tests/test_ui_smoke.py`.
- `finance.db` é local e gitignored; dados novos (Selic efetiva) são populados via `uv run python -m app.ingest`, não commitados.
- `codigos_fonte` em YAML são strings entre aspas (ex.: `"1178"`), como as entradas atuais.
- Commits pequenos e frequentes, um por task.
- Não alterar modelos Pydantic nem payloads existentes.

---

### Task 1: Indicador Selic efetiva (config)

**Files:**
- Modify: `config/indicadores.yaml` (adicionar um item)
- Test: `tests/test_config_loader.py`

**Interfaces:**
- Consumes: `carregar_indicadores()` de `app/config_loader.py` (existente).
- Produces: novo indicador com `id="bcb_1178_selic_efetiva"` disponível em `carregar_indicadores()`.

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_config_loader.py`:

```python
def test_indicadores_inclui_selic_efetiva():
    from app.config_loader import carregar_indicadores

    inds = carregar_indicadores()
    por_id = {i.id: i for i in inds}
    assert "bcb_1178_selic_efetiva" in por_id
    sel = por_id["bcb_1178_selic_efetiva"]
    assert sel.fonte == "BCB"
    assert sel.codigo_fonte == "1178"
    assert sel.periodicidade == "diaria"
    # a meta continua existindo, lado a lado
    assert "bcb_432_selic" in por_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_loader.py::test_indicadores_inclui_selic_efetiva -v`
Expected: FAIL — `bcb_1178_selic_efetiva` não está em `por_id`.

- [ ] **Step 3: Add the indicator to the YAML**

Em `config/indicadores.yaml`, logo após o bloco `bcb_432_selic` (as 8 linhas do indicador da Meta Selic, que terminam em `metodo_anual: fim_periodo`), inserir:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_loader.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config/indicadores.yaml tests/test_config_loader.py
git commit -m "feat: adiciona indicador Selic efetiva (BCB 1178) ao lado da meta"
```

---

### Task 2: Helper `grafico_comparacao_indicador` + gráficos na aba Comparação

**Files:**
- Modify: `app/ui.py` (novo helper após `grafico_barras` ~linha 34; bloco `with aba_comp:` ~linhas 99-108)
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: `payload_c.deltas` (`list[DeltaIndicador]` com campos `nome, valor_a, valor_b, unidade`) e `payload_c.mandato_a`/`payload_c.mandato_b` (`str`), de `construir_payload_comparacao` (existente).
- Produces: `grafico_comparacao_indicador(nome: str, unidade: str, valor_a: float, valor_b: float, rotulo_a: str, rotulo_b: str) -> go.Figure` (um `go.Bar`, dois valores, título `f"{nome} ({unidade})"`).

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_ui_smoke.py`:

```python
def test_grafico_comparacao_indicador_tem_duas_barras_e_titulo():
    from app.ui import grafico_comparacao_indicador

    fig = grafico_comparacao_indicador(
        "Meta Selic", "% a.a.", 13.75, 10.5, "Bolsonaro", "Lula 3"
    )
    d = fig.to_dict()
    assert d["data"][0]["type"] == "bar"
    assert list(d["data"][0]["y"]) == [13.75, 10.5]
    assert list(d["data"][0]["x"]) == ["Bolsonaro", "Lula 3"]
    assert "Meta Selic" in d["layout"]["title"]["text"]
    assert "% a.a." in d["layout"]["title"]["text"]


def test_ui_aba_comparacao_usa_grafico_por_indicador():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "grafico_comparacao_indicador" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_grafico_comparacao_indicador_tem_duas_barras_e_titulo -v`
Expected: FAIL — `ImportError: cannot import name 'grafico_comparacao_indicador'`.

- [ ] **Step 3: Add the helper**

Em `app/ui.py`, após `grafico_barras` (que termina na linha ~34, antes de `def main()`), inserir:

```python
def grafico_comparacao_indicador(
    nome: str, unidade: str, valor_a: float, valor_b: float, rotulo_a: str, rotulo_b: str
) -> go.Figure:
    fig = go.Figure(go.Bar(x=[rotulo_a, rotulo_b], y=[valor_a, valor_b]))
    fig.update_layout(title=f"{nome} ({unidade})")
    return fig
```

- [ ] **Step 4: Wire the tab**

Substituir o corpo de `with aba_comp:` (linhas ~99-108) por:

```python
    with aba_comp:
        nomes = [m.nome for m in mandatos]
        col_a, col_b = st.columns(2)
        a = col_a.selectbox("Mandato A", nomes, index=0)
        b = col_b.selectbox("Mandato B", nomes, index=len(nomes) - 1)
        ma = next(m for m in mandatos if m.nome == a)
        mb = next(m for m in mandatos if m.nome == b)
        payload_c = construir_payload_comparacao(conn, indicadores, ma, mb)

        comparaveis = [
            d for d in payload_c.deltas if d.valor_a is not None and d.valor_b is not None
        ]
        for i in range(0, len(comparaveis), 2):
            cols = st.columns(2)
            for col, d in zip(cols, comparaveis[i : i + 2]):
                col.plotly_chart(
                    grafico_comparacao_indicador(
                        d.nome, d.unidade, d.valor_a, d.valor_b,
                        payload_c.mandato_a, payload_c.mandato_b,
                    ),
                    width="stretch",
                    key=f"comp_{d.nome}",
                )

        st.dataframe(pd.DataFrame([d.model_dump() for d in payload_c.deltas]))
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_c)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui_smoke.py -q`
Expected: PASS (incluindo os 2 novos).

- [ ] **Step 6: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: aba Comparacao mostra grafico de barras A vs B por indicador"
```

---

### Task 3: `config/pastas.yaml` + loader `carregar_pastas`

**Files:**
- Create: `config/pastas.yaml`
- Create: `app/pastas.py`
- Test: `tests/test_pastas.py`

**Interfaces:**
- Consumes: `yaml.safe_load` (PyYAML, já dependência).
- Produces: `carregar_pastas(path: str = "config/pastas.yaml") -> dict[str, str]` (mapa pasta → descrição).

- [ ] **Step 1: Create the config file**

Criar `config/pastas.yaml` (mapa pasta → descrição, tom neutro/factual):

```yaml
Casa Civil: "Coordena e integra a ação dos ministérios e assessora diretamente a Presidência da República."
Fazenda: "Formula e executa a política econômica, fiscal e tributária do governo federal."
Economia: "Pasta que concentrou as áreas econômica, fazendária e de planejamento (2019-2022)."
Educação: "Formula e coordena as políticas nacionais de educação básica, técnica e superior."
Justiça: "Responsável pela política de justiça, cidadania e defesa da ordem jurídica."
Justiça e Segurança Pública: "Responsável pelas políticas de justiça, cidadania e segurança pública nacional."
Relações Exteriores: "Conduz a política externa e as relações diplomáticas do Brasil (Itamaraty)."
Secretaria-Geral: "Assessora a Presidência na coordenação política e na relação com a sociedade civil."
```

- [ ] **Step 2: Write the failing test**

Criar `tests/test_pastas.py`:

```python
def test_carregar_pastas_cobre_as_oito_pastas():
    from app.pastas import carregar_pastas

    pastas = carregar_pastas()
    esperadas = {
        "Casa Civil", "Fazenda", "Economia", "Educação", "Justiça",
        "Justiça e Segurança Pública", "Relações Exteriores", "Secretaria-Geral",
    }
    assert esperadas <= set(pastas.keys())
    assert all(isinstance(v, str) and v.strip() for v in pastas.values())


def test_carregar_pastas_retorna_dict():
    from app.pastas import carregar_pastas

    pastas = carregar_pastas()
    assert isinstance(pastas, dict)
    assert "coordena" in pastas["Casa Civil"].lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_pastas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pastas'`.

- [ ] **Step 4: Create the loader**

Criar `app/pastas.py`:

```python
"""Load the ministry-portfolio descriptions registry."""
from __future__ import annotations

import yaml


def carregar_pastas(path: str = "config/pastas.yaml") -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_pastas.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/pastas.yaml app/pastas.py tests/test_pastas.py
git commit -m "feat: config/pastas.yaml + carregar_pastas (descricao das pastas ministeriais)"
```

---

### Task 4: Expander de pastas na aba Ministros + UX das medidas vazias

**Files:**
- Modify: `app/ui.py` (bloco `with aba_min:`; expander após a tabela de ministros; mensagem em `app/ui.py:145`)
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: `carregar_pastas` (Task 3); `do_gov` (lista de `Ministro` do governo selecionado, já existente no bloco).
- Produces: nenhuma nova API (só UI).

- [ ] **Step 1: Write the failing test**

Adicionar a `tests/test_ui_smoke.py`:

```python
def test_ui_ministros_tem_expander_pastas_e_msg_medidas():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "carregar_pastas" in src
    assert "O que faz cada pasta" in src
    # a mensagem de medidas vazias virou explicativa e cita o botao de IA
    assert "Sugerir medidas (IA)" in src
    assert "Nenhuma medida aprovada ainda" in src
```

Nota: `test_ui_tem_aba_ministros` (já existente) continua válido; não removê-lo.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_ui_ministros_tem_expander_pastas_e_msg_medidas -v`
Expected: FAIL — `carregar_pastas` e "O que faz cada pasta" ainda não estão no source.

- [ ] **Step 3: Add the pastas expander**

No `app/ui.py`, dentro de `with aba_min:`, no bloco de imports locais desse `with` (onde já há `from app.ministros import carregar_ministros, ministros_do_governo`), adicionar o import `from app.pastas import carregar_pastas`. Depois, logo após o `st.dataframe([...])` que lista os ministros (a tabela com colunas pasta/nome/início/fim/fonte) e antes do `st.subheader("Medidas aprovadas")`, inserir:

```python
        descricoes = carregar_pastas()
        with st.expander("O que faz cada pasta"):
            for pasta in sorted({m.pasta for m in do_gov}):
                desc = descricoes.get(pasta)
                if desc:
                    st.markdown(f"**{pasta}** — {desc}")
```

- [ ] **Step 4: Improve the empty-medidas message**

Em `app/ui.py`, localizar (linha ~145):

```python
            st.caption("Nenhuma medida aprovada ainda.")
```

e substituir por:

```python
            st.info(
                "Nenhuma medida aprovada ainda. Use **Sugerir medidas (IA)** abaixo para "
                "gerar rascunhos com fonte e aprovar os que quiser — eles aparecerão aqui."
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui_smoke.py -q`
Expected: PASS (incluindo o novo).

- [ ] **Step 6: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: aba Ministros lista atribuicao das pastas + mensagem util quando sem medidas"
```

---

## Verificação final (após todas as tasks)

- [ ] `uv run pytest -q` — suíte inteira verde (136 anteriores + novos).
- [ ] `uv run ruff check .` — sem erros.
- [ ] `uv run python -m app.ingest` — popula a Selic efetiva no `finance.db` local (requer rede BCB).
- [ ] Smoke de runtime (AppTest, como no ciclo anterior):
  ```python
  from streamlit.testing.v1 import AppTest
  at = AppTest.from_file("app/ui.py", default_timeout=60).run()
  assert not at.exception, at.exception
  ```
  Expected: 0 exceções (as abas Comparação e Ministros reescritas renderizam sem erro).
- [ ] `uv run streamlit run app/ui.py` e conferir manualmente:
  - Por período / Por mandato: "Selic efetiva (anualizada)" ao lado da "Meta Selic".
  - Comparação: mini-gráficos de barras A vs B por indicador + tabela de deltas + resumo.
  - Ministros: expander "O que faz cada pasta"; mensagem explicativa quando não há medidas.

## Self-review (feita)

- **Cobertura do spec:** item 1 → Task 1; item 2 → Task 2; item 5 → Tasks 3-4; item 6 → Task 4. Testes e verificação e2e → seções finais. Sem lacunas.
- **Placeholders:** nenhum — todo YAML, código e teste estão completos e explícitos.
- **Consistência de tipos:** `grafico_comparacao_indicador(nome, unidade, valor_a, valor_b, rotulo_a, rotulo_b)` (Task 2) chamado com os mesmos nomes/tipos na fiação da aba; `carregar_pastas() -> dict[str,str]` (Task 3) usado como dict em Task 4; ids de indicador consistentes com o teste da Task 1.
