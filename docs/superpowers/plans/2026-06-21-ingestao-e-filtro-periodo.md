# Correção da ingestão (BCB/SIDRA) e filtro por período — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir os indicadores que ingerem 0 observações (BCB erro 406 e IPEA→SIDRA) e transformar a aba "Por ano" em "Por período" com filtro de intervalo que recorta gráficos e o resumo de IA.

**Architecture:** Três frentes. (1) Fetchers: `BCBFetcher` passa a enviar intervalo de datas e fatia séries diárias em janelas ≤10 anos; `SIDRAFetcher` ganha seleção opcional de variável/classificação. (2) Config: PIB e Gini migram de IPEA (códigos inválidos) para IBGE/SIDRA. (3) UI/payload: novo `PayloadPeriodo` + `construir_payload_periodo` (início vs fim + variação, reusando a lógica de mandato) e slider de intervalo na aba renomeada.

**Tech Stack:** Python 3.12, pydantic v2, httpx (com `httpx.MockTransport` nos testes), SQLite, Streamlit, plotly, pytest, ruff, pyright. Gerenciado por `uv`.

## Global Constraints

- Testes NUNCA fazem rede: `LLMClient` e HTTP são sempre mockados (`httpx.MockTransport`). A ingestão real (Task 8) é o único passo com rede e roda manualmente, fora do CI.
- O LLM nunca calcula números — o backend computa, o modelo só redige.
- Comandos sempre via `uv`: `uv run pytest -q`, `uv run ruff check .`, `uv run pyright`.
- `ruff` line-length = 100, target `py312`.
- Commits pequenos, um por tarefa concluída; mensagem descreve a tarefa.
- Não introduzir dependências novas.
- Janela de ingestão padrão do BCB: de `2003-01-01` (mandato mais antigo) até `datetime.date.today()`.

---

### Task 1: `Indicador` ganha campos opcionais `variavel` e `classificacao`

**Files:**
- Modify: `app/models.py:20-28` (classe `Indicador`)
- Test: `tests/test_config_loader.py`

**Interfaces:**
- Produces: `Indicador.variavel: str | None = None`, `Indicador.classificacao: str | None = None` (consumidos pelo `SIDRAFetcher` na Task 2).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar a `tests/test_config_loader.py`:

```python
def test_indicador_aceita_variavel_e_classificacao_opcionais():
    from app.models import Indicador

    ind = Indicador(
        id="x", fonte="IBGE", codigo_fonte="6784", nome="PIB",
        unidade="%", periodicidade="anual", eixo="macro",
        metodo_anual="fim_periodo", variavel="9808", classificacao="c11255/90707",
    )
    assert ind.variavel == "9808"
    assert ind.classificacao == "c11255/90707"

    ind2 = Indicador(
        id="y", fonte="BCB", codigo_fonte="432", nome="Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro",
        metodo_anual="fim_periodo",
    )
    assert ind2.variavel is None
    assert ind2.classificacao is None
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `uv run pytest tests/test_config_loader.py::test_indicador_aceita_variavel_e_classificacao_opcionais -v`
Expected: FAIL com `ValidationError` / `unexpected keyword argument 'variavel'`.

- [ ] **Step 3: Implementar (mínimo)**

Em `app/models.py`, na classe `Indicador`, adicionar as duas linhas ao final dos campos:

```python
class Indicador(BaseModel):
    id: str
    fonte: str
    codigo_fonte: str
    nome: str
    unidade: str
    periodicidade: Periodicidade
    eixo: Eixo
    metodo_anual: MetodoAnual
    variavel: str | None = None
    classificacao: str | None = None
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: PASS (incluindo os testes já existentes).

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_config_loader.py
git commit -m "feat: Indicador aceita variavel/classificacao opcionais (SIDRA)"
```

---

### Task 2: `SIDRAFetcher` usa `variavel`/`classificacao`

**Files:**
- Modify: `app/fetchers/sidra.py:11-27`
- Test: `tests/test_fetchers_sidra.py`

**Interfaces:**
- Consumes: `Indicador.variavel`, `Indicador.classificacao` (Task 1).
- Produces: comportamento de URL — com `variavel` usa `/v/{variavel}/`, senão `/v/allxp/`; com `classificacao` injeta `/{classificacao}` após o período.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar a `tests/test_fetchers_sidra.py`:

```python
def _captura_url():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        return httpx.Response(200, json=FIXTURE)

    return capturado, httpx.MockTransport(handler)


def test_sidra_usa_variavel_quando_presente():
    cap, transport = _captura_url()
    ind = Indicador(
        id="ibge_pib", fonte="IBGE", codigo_fonte="6784", nome="PIB",
        unidade="%", periodicidade="anual", eixo="macro",
        metodo_anual="fim_periodo", variavel="9808",
    )
    SIDRAFetcher().fetch(ind, httpx.Client(transport=transport))
    assert "/v/9808/" in cap["url"]
    assert "allxp" not in cap["url"]


def test_sidra_injeta_classificacao_quando_presente():
    cap, transport = _captura_url()
    ind = Indicador(
        id="ibge_gini", fonte="IBGE", codigo_fonte="7435", nome="Gini",
        unidade="índice", periodicidade="anual", eixo="social",
        metodo_anual="fim_periodo", variavel="10681", classificacao="c11255/90707",
    )
    SIDRAFetcher().fetch(ind, httpx.Client(transport=transport))
    assert "/v/10681/" in cap["url"]
    assert "/c11255/90707" in cap["url"]


def test_sidra_mantem_allxp_sem_variavel():
    cap, transport = _captura_url()
    SIDRAFetcher().fetch(_ind(), httpx.Client(transport=transport))
    assert "/v/allxp/" in cap["url"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_fetchers_sidra.py -v`
Expected: FAIL — `test_sidra_usa_variavel_quando_presente` e `test_sidra_injeta_classificacao_quando_presente` falham (URL ainda fixa em `allxp`, sem classificação).

- [ ] **Step 3: Implementar**

Substituir o topo e o início do `fetch` em `app/fetchers/sidra.py`:

```python
URL_SIDRA = (
    "https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/{variavel}/p/all{classif}?formato=json"
)


class SIDRAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        variavel = ind.variavel or "allxp"
        classif = f"/{ind.classificacao}" if ind.classificacao else ""
        url = URL_SIDRA.format(tabela=ind.codigo_fonte, variavel=variavel, classif=classif)
        resp = client.get(url, timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        # ... resto do parsing inalterado ...
```

(O bloco de parsing das linhas `raw[1:]` permanece idêntico.)

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_fetchers_sidra.py -v`
Expected: PASS (inclusive `test_sidra_skips_header_and_parses_quarter`, que usa o caminho `allxp`).

- [ ] **Step 5: Commit**

```bash
git add app/fetchers/sidra.py tests/test_fetchers_sidra.py
git commit -m "feat: SIDRAFetcher seleciona variavel/classificacao opcionais"
```

---

### Task 3: `BCBFetcher` envia intervalo de datas e fatia séries diárias

**Files:**
- Modify: `app/fetchers/bcb.py`
- Test: `tests/test_fetchers_bcb.py`

**Interfaces:**
- Produces: `janelas(inicio: date, fim: date, max_anos: int = 10) -> list[tuple[date, date]]` (helper puro) e `BCBFetcher.fetch` que envia `dataInicial`/`dataFinal`; para `periodicidade == "diaria"` faz uma requisição por janela e concatena.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar a `tests/test_fetchers_bcb.py` (manter o teste existente):

```python
from app.fetchers.bcb import BCBFetcher, INICIO_PADRAO, janelas


def test_janelas_fatia_em_blocos_de_10_anos():
    js = janelas(datetime.date(2003, 1, 1), datetime.date(2026, 1, 1))
    assert len(js) == 3
    assert js[0][0] == datetime.date(2003, 1, 1)
    assert js[0][1] == datetime.date(2012, 12, 31)
    assert js[1][0] == datetime.date(2013, 1, 1)
    assert js[-1][1] == datetime.date(2026, 1, 1)


def test_bcb_url_inclui_intervalo_de_datas():
    cap = {}

    def handler(request: httpx.Request) -> httpx.Response:
        cap.setdefault("urls", []).append(str(request.url))
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    BCBFetcher().fetch(_ind(), client)  # _ind() é mensal
    assert len(cap["urls"]) == 1
    assert "dataInicial=" in cap["urls"][0]
    assert "dataFinal=" in cap["urls"][0]


def test_bcb_serie_diaria_faz_varias_janelas_e_concatena():
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(200, json=[{"data": "01/01/2024", "valor": "5.0"}])

    ind = Indicador(
        id="bcb_1_cambio", fonte="BCB", codigo_fonte="1", nome="Câmbio",
        unidade="R$/US$", periodicidade="diaria", eixo="macro",
        metodo_anual="fim_periodo",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    raw, obs = BCBFetcher().fetch(ind, client)
    esperado = len(janelas(INICIO_PADRAO, datetime.date.today()))
    assert chamadas["n"] == esperado
    assert chamadas["n"] >= 2          # 2003→hoje sempre dá ≥ 2 janelas
    assert len(obs) == esperado        # 1 obs por janela na fixture
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_fetchers_bcb.py -v`
Expected: FAIL com `ImportError: cannot import name 'janelas'`.

- [ ] **Step 3: Implementar**

Substituir o conteúdo de `app/fetchers/bcb.py` por:

```python
"""BCB/SGS REST adapter."""
from __future__ import annotations

import datetime
from typing import Any

import httpx

from app.models import Indicador, Observacao

URL_BCB = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial={di}&dataFinal={df}"
)
INICIO_PADRAO = datetime.date(2003, 1, 1)


def janelas(
    inicio: datetime.date, fim: datetime.date, max_anos: int = 10
) -> list[tuple[datetime.date, datetime.date]]:
    out: list[tuple[datetime.date, datetime.date]] = []
    ini = inicio
    while ini <= fim:
        try:
            prox = ini.replace(year=ini.year + max_anos)
        except ValueError:  # 29/02 em ano não bissexto
            prox = ini.replace(year=ini.year + max_anos, day=28)
        fim_janela = min(fim, prox - datetime.timedelta(days=1))
        out.append((ini, fim_janela))
        ini = fim_janela + datetime.timedelta(days=1)
    return out


class BCBFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]:
        fim = datetime.date.today()
        if ind.periodicidade == "diaria":
            blocos = janelas(INICIO_PADRAO, fim)
        else:
            blocos = [(INICIO_PADRAO, fim)]
        raw_total: list[Any] = []
        out: list[Observacao] = []
        for di, df in blocos:
            url = URL_BCB.format(
                codigo=ind.codigo_fonte,
                di=di.strftime("%d/%m/%Y"),
                df=df.strftime("%d/%m/%Y"),
            )
            resp = client.get(url, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            raw_total.extend(raw)
            for row in raw:
                data = datetime.datetime.strptime(row["data"], "%d/%m/%Y").date()
                out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["valor"])))
        return raw_total, out
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_fetchers_bcb.py -v`
Expected: PASS — inclusive `test_bcb_parses_brazilian_dates_and_floats` (mensal → 1 janela, `raw_total[0]` == `FIXTURE[0]`).

- [ ] **Step 5: Commit**

```bash
git add app/fetchers/bcb.py tests/test_fetchers_bcb.py
git commit -m "fix: BCBFetcher envia intervalo de datas e fatia série diária (corrige 406)"
```

---

### Task 4: `observacoes_entre` — busca de observações por intervalo de datas

**Files:**
- Modify: `app/db.py` (adicionar função após `observacoes_da_serie:116-129`)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `observacoes_entre(conn, serie_id: str, inicio: datetime.date, fim: datetime.date) -> list[Observacao]` (consumido pela UI na Task 7).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar a `tests/test_db.py` (usar os imports/helpers já presentes no arquivo; se faltar algum, importar de `app.db`/`app.models`):

```python
def test_observacoes_entre_filtra_por_data():
    import datetime

    from app.db import conectar, criar_schema, observacoes_entre, upsert_observacoes, upsert_serie
    from app.models import Indicador, Observacao

    conn = conectar(":memory:")
    criar_schema(conn)
    ind = Indicador(
        id="s", fonte="BCB", codigo_fonte="1", nome="n", unidade="u",
        periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )
    upsert_serie(conn, ind)
    upsert_observacoes(conn, [
        Observacao(serie_id="s", data=datetime.date(2021, 6, 1), valor=1.0),
        Observacao(serie_id="s", data=datetime.date(2023, 6, 1), valor=2.0),
        Observacao(serie_id="s", data=datetime.date(2026, 6, 1), valor=3.0),
    ])
    res = observacoes_entre(conn, "s", datetime.date(2022, 1, 1), datetime.date(2025, 12, 31))
    assert [o.valor for o in res] == [2.0]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_db.py::test_observacoes_entre_filtra_por_data -v`
Expected: FAIL com `ImportError: cannot import name 'observacoes_entre'`.

- [ ] **Step 3: Implementar**

Em `app/db.py`, logo após `observacoes_da_serie`, adicionar:

```python
def observacoes_entre(
    conn: sqlite3.Connection,
    serie_id: str,
    inicio: datetime.date,
    fim: datetime.date,
) -> list[Observacao]:
    cur = conn.execute(
        """SELECT serie_id, data, valor FROM observacoes
           WHERE serie_id = ? AND data >= ? AND data <= ? ORDER BY data""",
        (serie_id, inicio.isoformat(), fim.isoformat()),
    )
    return [
        Observacao(serie_id=r[0], data=datetime.date.fromisoformat(r[1]), valor=r[2])
        for r in cur.fetchall()
    ]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: observacoes_entre filtra observacoes por intervalo de datas"
```

---

### Task 5: `PayloadPeriodo` + `construir_payload_periodo` + guard + descrever_payload

**Files:**
- Modify: `app/models.py` (novo `PayloadPeriodo` após `PayloadMandato:79-84`)
- Modify: `app/payload.py` (nova função + `descrever_payload:102-113` + unions de tipo)
- Modify: `app/guard.py:59-97` (ramo para `PayloadPeriodo`)
- Test: `tests/test_payload.py`, `tests/test_guard.py`

**Interfaces:**
- Consumes: `valor_no_periodo`, `variacao` (de `app/calculo.py`), `observacoes_da_serie`, `ValorIndicadorMandato`.
- Produces: `PayloadPeriodo(ano_inicio:int, ano_fim:int, indicadores:list[ValorIndicadorMandato], faltantes:list[str])`; `construir_payload_periodo(conn, indicadores, ano_inicio:int, ano_fim:int) -> PayloadPeriodo`; `descrever_payload(PayloadPeriodo) -> ("periodo", f"{ano_inicio}-{ano_fim}")`.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar a `tests/test_payload.py` (reusa `_conn_com_dados`/`_ind` já no arquivo):

```python
def test_payload_periodo_calcula_inicio_fim_e_variacao():
    from app.models import PayloadPeriodo
    from app.payload import construir_payload_periodo

    conn = _conn_com_dados()  # tem 2014->11.75 e 2018->6.5
    p = construir_payload_periodo(conn, [_ind()], 2014, 2018)
    assert isinstance(p, PayloadPeriodo)
    vi = p.indicadores[0]
    assert vi.valor_inicio == 11.75
    assert vi.valor_fim == 6.5
    assert vi.variacao is not None


def test_payload_periodo_marca_faltante():
    from app.payload import construir_payload_periodo

    conn = _conn_com_dados()
    p = construir_payload_periodo(conn, [_ind()], 2090, 2099)
    assert "Meta Selic" in p.faltantes


def test_descrever_payload_periodo():
    from app.payload import construir_payload_periodo, descrever_payload

    conn = _conn_com_dados()
    p = construir_payload_periodo(conn, [_ind()], 2014, 2018)
    assert descrever_payload(p) == ("periodo", "2014-2018")
```

Adicionar a `tests/test_guard.py` (seguir o padrão dos testes já existentes nesse arquivo para construir `ResumoFactual`/`Afirmacao`; o ponto central é que o guard NÃO quebre com `PayloadPeriodo`):

```python
def test_guard_aceita_payload_periodo():
    from app.guard import numeros_permitidos
    from app.models import PayloadPeriodo, ValorIndicadorMandato

    p = PayloadPeriodo(
        ano_inicio=2022, ano_fim=2025,
        indicadores=[ValorIndicadorMandato(
            nome="Selic", valor_inicio=13.75, valor_fim=10.5,
            variacao=-23.6, unidade="% a.a.", fonte="BCB",
        )],
        faltantes=[],
    )
    nums = numeros_permitidos(p)
    assert 13.75 in nums
    assert 10.5 in nums
    assert 2022.0 in nums
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_payload.py tests/test_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'PayloadPeriodo'` / `construir_payload_periodo`.

- [ ] **Step 3a: Modelo**

Em `app/models.py`, após `PayloadMandato`, adicionar:

```python
class PayloadPeriodo(BaseModel):
    ano_inicio: int
    ano_fim: int
    indicadores: list[ValorIndicadorMandato]
    faltantes: list[str]
```

- [ ] **Step 3b: Função de payload**

Em `app/payload.py`: importar `PayloadPeriodo` no bloco de imports de `app.models` e adicionar a função após `construir_payload_mandato`:

```python
def construir_payload_periodo(
    conn, indicadores: list[Indicador], ano_inicio: int, ano_fim: int
) -> PayloadPeriodo:
    valores: list[ValorIndicadorMandato] = []
    faltantes: list[str] = []
    for ind in indicadores:
        obs = observacoes_da_serie(conn, ind.id)
        v_inicio = valor_no_periodo(obs, ind, ano_inicio)
        v_fim = valor_no_periodo(obs, ind, ano_fim)
        var = variacao(v_inicio, v_fim)
        if v_inicio is None and v_fim is None:
            faltantes.append(ind.nome)
        valores.append(ValorIndicadorMandato(
            nome=ind.nome, valor_inicio=v_inicio, valor_fim=v_fim,
            variacao=var, unidade=ind.unidade, fonte=ind.fonte,
        ))
    return PayloadPeriodo(
        ano_inicio=ano_inicio, ano_fim=ano_fim,
        indicadores=valores, faltantes=faltantes,
    )
```

Trocar o import `from app.calculo import valor_no_mandato, valor_no_periodo, variacao` — já contém `valor_no_periodo` e `variacao`, então nada muda nesse import.

- [ ] **Step 3c: descrever_payload e unions**

Em `app/payload.py`, dentro de `descrever_payload`, adicionar o ramo ANTES do `return` final de comparação:

```python
    if isinstance(payload, PayloadPeriodo):
        return ("periodo", f"{payload.ano_inicio}-{payload.ano_fim}")
```

Adicionar `PayloadPeriodo` às anotações de união em `hash_payload` e `descrever_payload` (puramente cosmético, mantém o pyright feliz).

- [ ] **Step 3d: guard aceita PayloadPeriodo**

Em `app/guard.py`: importar `PayloadPeriodo` e trocar o ramo de `PayloadMandato` para cobrir os dois (mesma forma):

```python
    elif isinstance(payload, (PayloadMandato, PayloadPeriodo)):
        nums.add(float(payload.ano_inicio))
        nums.add(float(payload.ano_fim))
        for vi in payload.indicadores:
            for v in (vi.valor_inicio, vi.valor_fim, vi.variacao):
                if v is not None:
                    nums.add(v)
```

Isso evita que `PayloadPeriodo` caia no `else` (que assume `PayloadComparacao` e quebraria com `AttributeError` em `ano_inicio_a`). Adicionar `PayloadPeriodo` às uniões de tipo de `numeros_permitidos` e `verificar`.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_payload.py tests/test_guard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/payload.py app/guard.py tests/test_payload.py tests/test_guard.py
git commit -m "feat: PayloadPeriodo + construir_payload_periodo (resumo por intervalo)"
```

---

### Task 6: UI — aba "Por período" com slider, gráficos filtrados e resumo por intervalo

**Files:**
- Modify: `app/ui.py:35-47` (tabs + bloco `aba_ano`)
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: `observacoes_entre` (Task 4), `construir_payload_periodo` (Task 5).

- [ ] **Step 1: Escrever o teste que falha**

Adicionar a `tests/test_ui_smoke.py`:

```python
def test_ui_aba_por_periodo_usa_slider_e_payload_periodo():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "Por período" in src
    assert "st.slider" in src
    assert "construir_payload_periodo" in src
    assert "observacoes_entre" in src
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_ui_smoke.py::test_ui_aba_por_periodo_usa_slider_e_payload_periodo -v`
Expected: FAIL (string "Por período"/`st.slider` ausentes).

- [ ] **Step 3: Implementar**

Em `app/ui.py`:

1. No import de `app.payload` dentro de `main()` (linha ~27), trocar `construir_payload_ano` por `construir_payload_periodo`:

```python
    from app.payload import (
        construir_payload_comparacao,
        construir_payload_mandato,
        construir_payload_periodo,
    )
```

2. Importar `observacoes_entre` junto de `observacoes_da_serie` (linha ~25):

```python
    from app.db import conectar, criar_schema, observacoes_da_serie, observacoes_entre
```

3. Renomear o rótulo da primeira aba (linha ~35-37):

```python
    aba_ano, aba_mandato, aba_comp, aba_min, aba_leg = st.tabs(
        ["Por período", "Por mandato", "Comparação", "Ministros", "Legislativo"]
    )
```

4. Substituir o corpo de `with aba_ano:` (linhas ~39-47) por:

```python
    with aba_ano:
        import datetime as _dt

        anos = [m.inicio.year for m in mandatos] + [m.fim.year for m in mandatos]
        ano_min, ano_max = min(anos), max(anos)
        ano_ini, ano_fim = st.slider(
            "Período", min_value=ano_min, max_value=ano_max,
            value=(max(ano_min, ano_max - 3), ano_max),
        )
        di = _dt.date(ano_ini, 1, 1)
        df = _dt.date(ano_fim, 12, 31)
        for ind in indicadores:
            obs = observacoes_entre(conn, ind.id, di, df)
            if obs:
                st.plotly_chart(
                    grafico_serie(obs, ind.nome, ind.unidade, ind.fonte),
                    width="stretch", key=f"periodo_{ind.id}",
                )
        payload = construir_payload_periodo(conn, indicadores, int(ano_ini), int(ano_fim))
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload)
```

- [ ] **Step 4: Rodar e ver passar (testes + smoke do AppTest)**

Run: `uv run pytest tests/test_ui_smoke.py -v`
Expected: PASS.

Smoke de render completo:

```bash
uv run python - <<'PY'
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app/ui.py", default_timeout=60)
at.run()
assert len(at.exception) == 0, at.exception
print("OK: 0 exceptions")
PY
```
Expected: `OK: 0 exceptions`.

- [ ] **Step 5: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: aba 'Por período' com slider, graficos filtrados e resumo por intervalo"
```

---

### Task 7: Verificação completa da suíte (sem rede)

**Files:** nenhum (gate de qualidade).

- [ ] **Step 1: Rodar tudo**

Run: `uv run pytest -q`
Expected: todos os testes PASS.

- [ ] **Step 2: Lint + typecheck**

Run: `uv run ruff check . && uv run pyright`
Expected: sem erros. (Se o `pyright` reclamar de uniões de payload, adicionar `PayloadPeriodo` à anotação faltante.)

- [ ] **Step 3: Commit (se houve ajustes de lint/types)**

```bash
git add -A
git commit -m "chore: lint/typecheck apos filtro por periodo"
```

---

### Task 8: Migração IPEA→IBGE no config + ingestão real (REDE — manual)

> ⚠️ Esta task faz **rede real** (não roda no CI). Depende das Tasks 2 e 3.
> Os códigos exatos de tabela/variável do SIDRA precisam ser **descobertos e
> validados** contra a API; os candidatos abaixo são ponto de partida, não verdade.

**Files:**
- Modify: `config/indicadores.yaml` (entradas `ipea_pib_real_var` e `ipea_gini`)

- [ ] **Step 1: Descobrir os códigos SIDRA via metadados**

Para cada candidato de tabela, inspecionar variáveis/classificações:

```bash
# PIB real (variação de volume) — candidato: Contas Nacionais (tabela 6784 / 5938 / 1846)
uv run python -c "import httpx,json; print(json.dumps(httpx.get('https://servicodados.ibge.gov.br/api/v3/agregados/6784/metadados', timeout=60).json(), ensure_ascii=False, indent=2)[:3000])"

# Gini do rendimento domiciliar per capita (PNAD Contínua) — candidato: tabela 7435 e correlatas
uv run python -c "import httpx,json; print(json.dumps(httpx.get('https://servicodados.ibge.gov.br/api/v3/agregados/7435/metadados', timeout=60).json(), ensure_ascii=False, indent=2)[:3000])"
```

Escolher: a **tabela** (`codigo_fonte`), a **variável** (`variavel`) que corresponde a "PIB - variação real anual" e a "Índice de Gini", e a **classificação** (`classificacao`, formato `cNNN/CAT`) se a tabela exigir. Anotar os escolhidos.

- [ ] **Step 2: Atualizar `config/indicadores.yaml`**

Substituir as duas entradas IPEA por entradas IBGE (preencher com os códigos validados no Step 1):

```yaml
- id: ibge_pib_real_var
  fonte: IBGE
  codigo_fonte: "<tabela_pib>"
  variavel: "<variavel_pib>"
  classificacao: "<classif_ou_remover_a_linha>"
  nome: PIB real (variação anual)
  unidade: "%"
  periodicidade: anual
  eixo: macro
  metodo_anual: fim_periodo
- id: ibge_gini
  fonte: IBGE
  codigo_fonte: "<tabela_gini>"
  variavel: "<variavel_gini>"
  classificacao: "<classif_ou_remover_a_linha>"
  nome: Índice de Gini
  unidade: índice
  periodicidade: anual
  eixo: social
  metodo_anual: fim_periodo
```

(Remover a linha `classificacao` quando a tabela não exigir classificação.)

- [ ] **Step 3: Rodar a ingestão real e conferir > 0 observações**

```bash
uv run python -m app.ingest
```
Expected: as linhas de saída para `bcb_432_selic`, `bcb_1_cambio`, `ibge_pib_real_var` e `ibge_gini` mostram **N > 0** observações. Conferir também via log:

```bash
uv run python -c "import sqlite3; [print(r) for r in sqlite3.connect('finance.db').execute(\"SELECT serie_id,status,n_registros,substr(erro,1,80) FROM ingestao_log ORDER BY rowid DESC LIMIT 8\")]"
```

- [ ] **Step 4: Mostrar ao usuário os códigos escolhidos e os totais**

Reportar: qual tabela/variável foi usada para PIB e Gini e quantas observações cada série trouxe, para o usuário confirmar que são as séries certas (Gini tem versões diferentes).

- [ ] **Step 5: Commit**

```bash
git add config/indicadores.yaml
git commit -m "fix: migrar PIB e Gini de IPEA (codigos invalidos) para IBGE/SIDRA"
```

---

## Self-Review

**Cobertura do spec:**
- A1 (BCB 406 + janelas) → Task 3 + verificação real na Task 8. ✓
- A2 (SIDRA variavel/classificacao + migração) → Tasks 1, 2, 8. ✓
- B1 (slider + rename "Por período") → Task 6. ✓
- B2 (gráficos filtrados por range) → Tasks 4 + 6. ✓
- B3 (`construir_payload_periodo`, início vs fim + variação) → Task 5. ✓
- B4 (cache `periodo`/`{ini}-{fim}`) → Task 5 (`descrever_payload`). ✓
- Integração não citada no spec mas necessária: guard aceitar `PayloadPeriodo` → Task 5 Step 3d. ✓
- Testes (mock, AppTest) → cada task + Task 7. ✓

**Placeholders:** os únicos `<...>` ficam na Task 8 (códigos SIDRA), e é intencional/aprovado — a própria task instrui como descobri-los via metadados antes de preencher.

**Consistência de tipos:** `construir_payload_periodo` retorna `PayloadPeriodo`; `PayloadPeriodo.indicadores` reusa `ValorIndicadorMandato` (campos `valor_inicio/valor_fim/variacao`), batendo com o ramo do guard e com `descrever_payload`. `observacoes_entre(conn, serie_id, inicio, fim)` tem a mesma assinatura usada na UI. `janelas`/`INICIO_PADRAO` exportados de `app/fetchers/bcb.py` batem com os imports do teste.
