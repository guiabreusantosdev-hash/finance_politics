# Camada Legislativa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingerir leis sancionadas (Câmara) e vetos presidenciais (Senado/Congresso) por mandato, agregar por tipo/tema, e oferecer visualização navegável + resumo factual.

**Architecture:** Dois fetchers novos baixam arquivos anuais da Câmara e o conjunto de vetos do Senado, gravam JSON bruto e normalizam para as tabelas `leis`/`vetos`/`lei_temas`. Agregações puras contam por mandato (atribuição por data). Payload e resumo reutilizam o guard, o juiz e a persistência de resumos existentes.

**Tech Stack:** Python 3.12, httpx, Pydantic v2, SQLite (`sqlite3`), pytest, Streamlit, Plotly.

## Global Constraints

- Python `>=3.12`; pyright modo `standard`; ruff `line-length = 100`.
- **O LLM nunca calcula números** — o backend conta; o modelo só redige citando contagens do payload.
- **Zero rede nos testes:** HTTP e `LLMClient` sempre mockados; fetchers testados com **fixtures de JSON real reduzido**; conexões de teste usam `conectar(":memory:")`.
- JSON bruto gravado em `raw/<fonte>/<conjunto>_{ano}_<timestamp>.json` antes de normalizar.
- Resiliência: um ano/fonte que falha registra em `ingestao_log` e segue (não derruba o pipeline).
- Não adicionar dependências novas. Commits pequenos, um por tarefa; TDD.

## Dependência de ordem

> Assume o plano `2026-06-21-persistencia-resumos.md` já implementado (`descrever_payload`,
> `salvar_resumo`, `_mostrar_resumo(st, conn, client, payload)`). A Task 6 estende
> `descrever_payload`; a Task 8 reusa `_mostrar_resumo`.

---

### Task 1: Spike de verificação das fontes (fixtures reais)

> Tarefa de descoberta: confirma os campos reais das duas APIs e congela fixtures reduzidas
> que as Tasks 3/4 consomem. Sem isso, os fetchers chutariam o formato. NÃO escreve código de
> produção.

**Files:**
- Create: `tests/fixtures/legislativo/camara_proposicoes_2023.json`
- Create: `tests/fixtures/legislativo/camara_temas_2023.json`
- Create: `tests/fixtures/legislativo/senado_vetos_2023.json`
- Create: `docs/superpowers/notas-fontes-legislativo.md`

- [ ] **Step 1: Baixar amostras ao vivo**

```bash
mkdir -p tests/fixtures/legislativo
curl -s "https://dadosabertos.camara.leg.br/arquivos/proposicoes/json/proposicoes-2023.json" -o /tmp/prop2023.json
curl -s "https://dadosabertos.camara.leg.br/arquivos/proposicoesTemas/json/proposicoesTemas-2023.json" -o /tmp/temas2023.json
```

- [ ] **Step 2: Inspecionar os campos reais**

```bash
uv run python -c "import json; d=json.load(open('/tmp/prop2023.json'))['dados']; print(list(d[0].keys())); print(json.dumps(d[0], ensure_ascii=False, indent=2)[:1500])"
uv run python -c "import json; d=json.load(open('/tmp/temas2023.json'))['dados']; print(list(d[0].keys())); print(d[0])"
```

Anote em `docs/superpowers/notas-fontes-legislativo.md`: o caminho do array (`dados`), o nome
do campo de situação (esperado `ultimoStatus.descricaoSituacao`), o valor exato que indica lei
sancionada (esperado `"Transformada em Norma Jurídica"`), e os campos de número/ano/ementa/data.

- [ ] **Step 3: Confirmar o endpoint de vetos do Senado**

Abra `https://legis.senado.leg.br/dadosabertos/docs/index.html`, localize o recurso de
**Vetos do Congresso Nacional** por ano, e baixe um ano de amostra (ajuste o caminho conforme
a doc; sufixo `.json`):

```bash
curl -s "https://legis.senado.leg.br/dadosabertos/dados/VetoList.json?ano=2023" -o /tmp/vetos2023.json || echo "ajustar caminho conforme docs"
uv run python -c "import json; print(json.load(open('/tmp/vetos2023.json')))" | head -c 1500
```

Anote em `notas-fontes-legislativo.md` o caminho REST exato e os campos (data, número, tipo
total/parcial, descrição, matéria, url).

- [ ] **Step 4: Congelar fixtures reduzidas**

Crie cada fixture com **3–5 registros reais** representativos (inclua ao menos uma proposição
"Transformada em Norma Jurídica" e uma que NÃO foi, para testar o filtro). Mantenha a mesma
estrutura aninhada da API (`{"dados": [...]}`).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/legislativo docs/superpowers/notas-fontes-legislativo.md
git commit -m "test: fixtures reais + notas das fontes legislativas (spike)"
```

---

### Task 2: DTOs `Lei`/`Veto` + tabelas + storage (`app/db.py`, `app/models.py`)

**Files:**
- Modify: `app/models.py`
- Modify: `app/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `Lei(BaseModel)`: `id: str, tipo: str, numero: str, ano: int, data: datetime.date, ementa: str, url: str`.
  - `Veto(BaseModel)`: `id: str, data: datetime.date, tipo: str, descricao: str, materia: str, url: str`.
  - `upsert_leis(conn, leis: list[Lei]) -> int`
  - `upsert_vetos(conn, vetos: list[Veto]) -> int`
  - `upsert_lei_temas(conn, lei_id: str, temas: list[str]) -> int`
  - `leis_entre(conn, inicio: datetime.date, fim: datetime.date) -> list[Lei]`
  - `vetos_entre(conn, inicio: datetime.date, fim: datetime.date) -> list[Veto]`
  - `temas_de(conn, lei_id: str) -> list[str]`

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_db.py`:

```python
import datetime as _dt

from app.db import (
    leis_entre,
    temas_de,
    upsert_lei_temas,
    upsert_leis,
    upsert_vetos,
    vetos_entre,
)
from app.models import Lei, Veto


def _lei(id="camara_1", ano=2023, mes=6) -> Lei:
    return Lei(id=id, tipo="LO", numero="14.500", ano=ano,
               data=_dt.date(ano, mes, 1), ementa="e", url="https://x")


def test_upsert_e_consulta_leis_por_intervalo():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [_lei("a", 2023), _lei("b", 2019)])
    dentro = leis_entre(conn, _dt.date(2023, 1, 1), _dt.date(2026, 12, 31))
    assert [x.id for x in dentro] == ["a"]


def test_upsert_leis_idempotente():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [_lei("a")])
    upsert_leis(conn, [_lei("a")])
    assert len(leis_entre(conn, _dt.date(2023, 1, 1), _dt.date(2023, 12, 31))) == 1


def test_temas_roundtrip():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [_lei("a")])
    upsert_lei_temas(conn, "a", ["Saúde", "Economia"])
    upsert_lei_temas(conn, "a", ["Saúde", "Economia"])  # idempotente
    assert sorted(temas_de(conn, "a")) == ["Economia", "Saúde"]


def test_vetos_por_intervalo():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_vetos(conn, [
        Veto(id="v1", data=_dt.date(2023, 5, 1), tipo="parcial",
             descricao="d", materia="Lei X", url="https://x"),
        Veto(id="v2", data=_dt.date(2018, 5, 1), tipo="total",
             descricao="d", materia="Lei Y", url="https://y"),
    ])
    dentro = vetos_entre(conn, _dt.date(2023, 1, 1), _dt.date(2026, 12, 31))
    assert [v.id for v in dentro] == ["v1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -k "leis or temas or vetos" -v`
Expected: FAIL com `ImportError: cannot import name 'upsert_leis'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/models.py`, ao final:

```python
class Lei(BaseModel):
    id: str
    tipo: str            # LO | LC | MP | EC
    numero: str
    ano: int
    data: datetime.date
    ementa: str
    url: str


class Veto(BaseModel):
    id: str
    data: datetime.date
    tipo: str            # total | parcial
    descricao: str
    materia: str
    url: str
```

Adicione ao `_SCHEMA` em `app/db.py`:

```sql
CREATE TABLE IF NOT EXISTS leis (
    id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, ano INTEGER,
    data TEXT, ementa TEXT, url TEXT
);
CREATE TABLE IF NOT EXISTS vetos (
    id TEXT PRIMARY KEY, data TEXT, tipo TEXT, descricao TEXT, materia TEXT, url TEXT
);
CREATE TABLE IF NOT EXISTS lei_temas (
    lei_id TEXT, tema TEXT,
    PRIMARY KEY (lei_id, tema),
    FOREIGN KEY (lei_id) REFERENCES leis(id)
);
```

Adicione ao final de `app/db.py`:

```python
def upsert_leis(conn: sqlite3.Connection, leis) -> int:
    rows = [(x.id, x.tipo, x.numero, x.ano, x.data.isoformat(), x.ementa, x.url) for x in leis]
    conn.executemany(
        """INSERT INTO leis (id, tipo, numero, ano, data, ementa, url)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET tipo=excluded.tipo, numero=excluded.numero,
             ano=excluded.ano, data=excluded.data, ementa=excluded.ementa, url=excluded.url""",
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_vetos(conn: sqlite3.Connection, vetos) -> int:
    rows = [(v.id, v.data.isoformat(), v.tipo, v.descricao, v.materia, v.url) for v in vetos]
    conn.executemany(
        """INSERT INTO vetos (id, data, tipo, descricao, materia, url)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET data=excluded.data, tipo=excluded.tipo,
             descricao=excluded.descricao, materia=excluded.materia, url=excluded.url""",
        rows,
    )
    conn.commit()
    return len(rows)


def upsert_lei_temas(conn: sqlite3.Connection, lei_id: str, temas) -> int:
    rows = [(lei_id, t) for t in temas]
    conn.executemany(
        "INSERT OR IGNORE INTO lei_temas (lei_id, tema) VALUES (?, ?)", rows
    )
    conn.commit()
    return len(rows)


def _lei_de_row(r: tuple):
    from app.models import Lei
    return Lei(id=r[0], tipo=r[1], numero=r[2], ano=r[3],
               data=datetime.date.fromisoformat(r[4]), ementa=r[5], url=r[6])


def leis_entre(conn: sqlite3.Connection, inicio, fim):
    cur = conn.execute(
        """SELECT id, tipo, numero, ano, data, ementa, url FROM leis
           WHERE data >= ? AND data <= ? ORDER BY data""",
        (inicio.isoformat(), fim.isoformat()),
    )
    return [_lei_de_row(r) for r in cur.fetchall()]


def vetos_entre(conn: sqlite3.Connection, inicio, fim):
    from app.models import Veto
    cur = conn.execute(
        """SELECT id, data, tipo, descricao, materia, url FROM vetos
           WHERE data >= ? AND data <= ? ORDER BY data""",
        (inicio.isoformat(), fim.isoformat()),
    )
    return [
        Veto(id=r[0], data=datetime.date.fromisoformat(r[1]), tipo=r[2],
             descricao=r[3], materia=r[4], url=r[5])
        for r in cur.fetchall()
    ]


def temas_de(conn: sqlite3.Connection, lei_id: str) -> list[str]:
    cur = conn.execute("SELECT tema FROM lei_temas WHERE lei_id = ?", (lei_id,))
    return [r[0] for r in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -k "leis or temas or vetos" -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/db.py tests/test_db.py
git commit -m "feat: DTOs Lei/Veto + tabelas leis/vetos/lei_temas + storage"
```

---

### Task 3: Fetcher de leis da Câmara (`app/fetchers/camara.py`)

**Files:**
- Create: `app/fetchers/camara.py`
- Test: `tests/test_fetchers_camara.py`

**Interfaces:**
- Consumes: fixtures da Task 1; `Lei` de `app/models.py`.
- Produces:
  - `MAPA_TIPO: dict[str, str]` = `{"PL": "LO", "PLP": "LC", "MPV": "MP", "PEC": "EC"}`.
  - `normalizar_leis(prop_json: dict, temas_json: dict) -> tuple[list[Lei], dict[str, list[str]]]`
    (filtra "Transformada em Norma Jurídica"; mapeia tipo; retorna leis + temas por lei_id).

> O fetcher é dividido em uma função **pura** `normalizar_leis` (testável com fixtures, sem
> rede) e um método `fetch` fino que baixa via httpx. Só a parte pura é testada.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_fetchers_camara.py`:

```python
import json
import pathlib

from app.fetchers.camara import normalizar_leis

FIX = pathlib.Path("tests/fixtures/legislativo")


def test_normalizar_leis_filtra_e_mapeia():
    prop = json.loads((FIX / "camara_proposicoes_2023.json").read_text(encoding="utf-8"))
    temas = json.loads((FIX / "camara_temas_2023.json").read_text(encoding="utf-8"))
    leis, temas_por_lei = normalizar_leis(prop, temas)
    # toda lei retornada deve ter tipo mapeado e id
    assert all(x.tipo in {"LO", "LC", "MP", "EC"} for x in leis)
    assert all(x.id.startswith("camara_") for x in leis)
    # nenhuma proposição NÃO-transformada deve aparecer
    assert len(leis) >= 1
    # temas_por_lei só referencia ids de leis retornadas
    ids = {x.id for x in leis}
    assert set(temas_por_lei).issubset(ids)
```

> **Nota:** ajuste as asserções aos dados reais congelados na Task 1 se necessário (ex.: o
> número exato de leis na fixture). Mantenha o invariante "tipo mapeado + filtro aplicado".

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetchers_camara.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.fetchers.camara'`.

- [ ] **Step 3: Write minimal implementation**

Crie `app/fetchers/camara.py` (ajuste os nomes de campo conforme as notas da Task 1):

```python
"""Fetcher de leis sancionadas a partir dos arquivos anuais da Câmara."""
from __future__ import annotations

import datetime

import httpx

from app.models import Lei

URL_PROP = "https://dadosabertos.camara.leg.br/arquivos/proposicoes/json/proposicoes-{ano}.json"
URL_TEMAS = "https://dadosabertos.camara.leg.br/arquivos/proposicoesTemas/json/proposicoesTemas-{ano}.json"
MAPA_TIPO = {"PL": "LO", "PLP": "LC", "MPV": "MP", "PEC": "EC"}
SITUACAO_LEI = "Transformada em Norma Jurídica"


def _data(s: str) -> datetime.date:
    # ISO com ou sem hora: "2023-06-01" ou "2023-06-01T10:00"
    return datetime.date.fromisoformat(s[:10])


def normalizar_leis(prop_json: dict, temas_json: dict):
    dados = prop_json.get("dados", prop_json)
    temas_dados = temas_json.get("dados", temas_json)

    leis: list[Lei] = []
    ids_ok: set[str] = set()
    for p in dados:
        status = p.get("ultimoStatus") or {}
        situacao = status.get("descricaoSituacao") or ""
        sigla = p.get("siglaTipo")
        if SITUACAO_LEI.lower() not in situacao.lower() or sigla not in MAPA_TIPO:
            continue
        lid = f"camara_{p['id']}"
        ids_ok.add(lid)
        leis.append(Lei(
            id=lid,
            tipo=MAPA_TIPO[sigla],
            numero=str(p.get("numero", "")),
            ano=int(p.get("ano", 0)),
            data=_data(status.get("dataHora") or p.get("dataApresentacao") or "1900-01-01"),
            ementa=p.get("ementa") or "",
            url=p.get("uri") or "",
        ))

    temas_por_lei: dict[str, list[str]] = {}
    for t in temas_dados:
        pid = t.get("idProposicao") or t.get("uriProposicao", "").rstrip("/").split("/")[-1]
        lid = f"camara_{pid}"
        if lid in ids_ok and t.get("tema"):
            temas_por_lei.setdefault(lid, []).append(t["tema"])
    return leis, temas_por_lei


class CamaraLeisFetcher:
    def fetch(self, ano: int, client: httpx.Client):
        prop = client.get(URL_PROP.format(ano=ano), timeout=60).json()
        temas = client.get(URL_TEMAS.format(ano=ano), timeout=60).json()
        leis, temas_por_lei = normalizar_leis(prop, temas)
        return {"prop": prop, "temas": temas}, leis, temas_por_lei
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fetchers_camara.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/fetchers/camara.py tests/test_fetchers_camara.py
git commit -m "feat: fetcher de leis sancionadas da Câmara (normalização pura + fetch)"
```

---

### Task 4: Fetcher de vetos do Senado (`app/fetchers/senado_vetos.py`)

**Files:**
- Create: `app/fetchers/senado_vetos.py`
- Test: `tests/test_fetchers_senado_vetos.py`

**Interfaces:**
- Consumes: fixture `senado_vetos_2023.json`; `Veto` de `app/models.py`.
- Produces: `normalizar_vetos(veto_json: dict) -> list[Veto]`.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_fetchers_senado_vetos.py`:

```python
import json
import pathlib

from app.fetchers.senado_vetos import normalizar_vetos

FIX = pathlib.Path("tests/fixtures/legislativo")


def test_normalizar_vetos():
    raw = json.loads((FIX / "senado_vetos_2023.json").read_text(encoding="utf-8"))
    vetos = normalizar_vetos(raw)
    assert len(vetos) >= 1
    assert all(v.tipo in {"total", "parcial"} for v in vetos)
    assert all(v.id for v in vetos)
```

> Ajuste os nomes de campo em `normalizar_vetos` aos confirmados na Task 1.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetchers_senado_vetos.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Crie `app/fetchers/senado_vetos.py` (ajuste caminho/campos conforme a Task 1):

```python
"""Fetcher dos vetos do Congresso Nacional (Dados Abertos do Senado)."""
from __future__ import annotations

import datetime

import httpx

from app.models import Veto

URL_VETOS = "https://legis.senado.leg.br/dadosabertos/dados/VetoList.json?ano={ano}"


def _tipo(bruto: str) -> str:
    return "parcial" if "parcial" in (bruto or "").lower() else "total"


def normalizar_vetos(veto_json: dict) -> list[Veto]:
    # o caminho exato do array é confirmado na Task 1; tentativa robusta:
    dados = veto_json
    for chave in ("ListaVetos", "Vetos", "dados"):
        if isinstance(dados, dict) and chave in dados:
            dados = dados[chave]
    if isinstance(dados, dict) and "Veto" in dados:
        dados = dados["Veto"]
    if isinstance(dados, dict):
        dados = [dados]

    vetos: list[Veto] = []
    for v in dados:
        vid = str(v.get("id") or v.get("codigoMateria") or v.get("numero") or "")
        if not vid:
            continue
        data_str = (v.get("data") or v.get("dataVeto") or "1900-01-01")[:10]
        vetos.append(Veto(
            id=f"senado_{vid}",
            data=datetime.date.fromisoformat(data_str),
            tipo=_tipo(v.get("tipo") or v.get("descricaoTipo")),
            descricao=v.get("descricao") or v.get("ementa") or "",
            materia=v.get("materia") or v.get("identificacao") or "",
            url=v.get("url") or v.get("uri") or "",
        ))
    return vetos


class SenadoVetosFetcher:
    def fetch(self, ano: int, client: httpx.Client):
        raw = client.get(URL_VETOS.format(ano=ano), timeout=60).json()
        return raw, normalizar_vetos(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fetchers_senado_vetos.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/fetchers/senado_vetos.py tests/test_fetchers_senado_vetos.py
git commit -m "feat: fetcher de vetos do Congresso (Senado dados abertos)"
```

---

### Task 5: Orquestração de ingestão (`app/ingest_legislativo.py`)

**Files:**
- Create: `app/ingest_legislativo.py`
- Test: `tests/test_ingest_legislativo.py`

**Interfaces:**
- Consumes: `CamaraLeisFetcher`, `SenadoVetosFetcher`, storage da Task 2, `salvar_raw`/
  `registrar_ingestao` de `app/ingest.py` e `app/db.py`.
- Produces:
  - `anos_dos_mandatos(mandatos) -> list[int]` (todos os anos cobertos).
  - `ingerir_legislativo(conn, anos, client, agora, *, camara=None, vetos=None) -> dict[str, int]`
    (injeção de fetchers para teste; retorna `{"leis": n, "vetos": m}`).

- [ ] **Step 1: Write the failing test**

Crie `tests/test_ingest_legislativo.py`:

```python
import datetime

from app.db import conectar, criar_schema, leis_entre, temas_de, vetos_entre
from app.ingest_legislativo import anos_dos_mandatos, ingerir_legislativo
from app.models import Lei, Mandato, Veto


def test_anos_dos_mandatos():
    ms = [
        Mandato(nome="A", inicio=datetime.date(2003, 1, 1), fim=datetime.date(2004, 12, 31)),
    ]
    assert anos_dos_mandatos(ms) == [2003, 2004]


class _CamaraFake:
    def fetch(self, ano, client):
        lei = Lei(id=f"camara_{ano}", tipo="LO", numero="1", ano=ano,
                  data=datetime.date(ano, 6, 1), ementa="e", url="u")
        return {"raw": ano}, [lei], {f"camara_{ano}": ["Saúde"]}


class _VetosFake:
    def fetch(self, ano, client):
        v = Veto(id=f"senado_{ano}", data=datetime.date(ano, 7, 1), tipo="parcial",
                 descricao="d", materia="m", url="u")
        return {"raw": ano}, [v]


def test_ingerir_legislativo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # raw/ vai para o tmp
    conn = conectar(":memory:")
    criar_schema(conn)
    agora = "2026-06-21T10:00:00"
    out = ingerir_legislativo(conn, [2023], None, agora,
                              camara=_CamaraFake(), vetos=_VetosFake())
    assert out == {"leis": 1, "vetos": 1}
    assert temas_de(conn, "camara_2023") == ["Saúde"]
    assert len(leis_entre(conn, datetime.date(2023, 1, 1), datetime.date(2023, 12, 31))) == 1
    assert len(vetos_entre(conn, datetime.date(2023, 1, 1), datetime.date(2023, 12, 31))) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_legislativo.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Crie `app/ingest_legislativo.py`:

```python
"""Ingestão da camada legislativa: leis (Câmara) + vetos (Senado)."""
from __future__ import annotations

import datetime

import httpx

from app.config_loader import carregar_mandatos
from app.db import (
    conectar,
    criar_schema,
    registrar_ingestao,
    upsert_lei_temas,
    upsert_leis,
    upsert_vetos,
)
from app.fetchers.camara import CamaraLeisFetcher
from app.fetchers.senado_vetos import SenadoVetosFetcher
from app.ingest import salvar_raw


def anos_dos_mandatos(mandatos) -> list[int]:
    anos: set[int] = set()
    for m in mandatos:
        for a in range(m.inicio.year, m.fim.year + 1):
            anos.add(a)
    return sorted(anos)


def ingerir_legislativo(conn, anos, client, agora, *, camara=None, vetos=None) -> dict:
    camara = camara or CamaraLeisFetcher()
    vetos = vetos or SenadoVetosFetcher()
    total_leis = total_vetos = 0
    for ano in anos:
        try:
            raw, leis, temas_por_lei = camara.fetch(ano, client)
            salvar_raw("CAMARA", f"leis_{ano}", raw, agora)
            total_leis += upsert_leis(conn, leis)
            for lid, temas in temas_por_lei.items():
                upsert_lei_temas(conn, lid, temas)
            registrar_ingestao(conn, f"camara_leis_{ano}", agora, "ok", len(leis), None)
        except Exception as exc:  # noqa: BLE001 - um ano quebrado não derruba o pipeline
            registrar_ingestao(conn, f"camara_leis_{ano}", agora, "erro", 0, str(exc))
        try:
            raw_v, vs = vetos.fetch(ano, client)
            salvar_raw("SENADO", f"vetos_{ano}", raw_v, agora)
            total_vetos += upsert_vetos(conn, vs)
            registrar_ingestao(conn, f"senado_vetos_{ano}", agora, "ok", len(vs), None)
        except Exception as exc:  # noqa: BLE001
            registrar_ingestao(conn, f"senado_vetos_{ano}", agora, "erro", 0, str(exc))
    return {"leis": total_leis, "vetos": total_vetos}


def main() -> None:  # pragma: no cover - smoke manual com rede
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    conn = conectar()
    criar_schema(conn)
    anos = anos_dos_mandatos(carregar_mandatos())
    with httpx.Client(headers={"User-Agent": "finance_politics/0.1"}) as client:
        out = ingerir_legislativo(conn, anos, client, agora)
    print(f"leis: {out['leis']} | vetos: {out['vetos']}")


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_legislativo.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add app/ingest_legislativo.py tests/test_ingest_legislativo.py
git commit -m "feat: orquestração da ingestão legislativa (leis + vetos por ano)"
```

---

### Task 6: Agregação (`app/legislativo.py`)

**Files:**
- Create: `app/legislativo.py`
- Test: `tests/test_legislativo.py`

**Interfaces:**
- Consumes: `leis_entre`, `vetos_entre`, `temas_de` de `app/db.py`; `Mandato` de `app/models.py`.
- Produces:
  - `leis_no_mandato(conn, mandato) -> list[Lei]`
  - `vetos_no_mandato(conn, mandato) -> list[Veto]`
  - `agregar_por_tipo(leis) -> dict[str, int]`
  - `agregar_por_tema(conn, leis) -> dict[str, int]`
  - `agregar_vetos_por_tipo(vetos) -> dict[str, int]`

- [ ] **Step 1: Write the failing test**

Crie `tests/test_legislativo.py`:

```python
import datetime

from app.db import conectar, criar_schema, upsert_lei_temas, upsert_leis, upsert_vetos
from app.legislativo import (
    agregar_por_tema,
    agregar_por_tipo,
    agregar_vetos_por_tipo,
    leis_no_mandato,
    vetos_no_mandato,
)
from app.models import Lei, Mandato, Veto


def _mandato() -> Mandato:
    return Mandato(nome="Lula 3", inicio=datetime.date(2023, 1, 1), fim=datetime.date(2026, 12, 31))


def test_atribuicao_por_data_e_agregacoes():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [
        Lei(id="a", tipo="LO", numero="1", ano=2023, data=datetime.date(2023, 1, 1),
            ementa="e", url="u"),                                     # borda inicial: dentro
        Lei(id="b", tipo="MP", numero="2", ano=2024, data=datetime.date(2024, 5, 1),
            ementa="e", url="u"),
        Lei(id="c", tipo="LO", numero="3", ano=2022, data=datetime.date(2022, 12, 31),
            ementa="e", url="u"),                                     # fora (mandato anterior)
    ])
    upsert_lei_temas(conn, "a", ["Saúde"])
    upsert_lei_temas(conn, "b", ["Saúde", "Economia"])
    upsert_vetos(conn, [
        Veto(id="v1", data=datetime.date(2023, 3, 1), tipo="parcial",
             descricao="d", materia="m", url="u"),
    ])
    m = _mandato()
    leis = leis_no_mandato(conn, m)
    assert {x.id for x in leis} == {"a", "b"}
    assert agregar_por_tipo(leis) == {"LO": 1, "MP": 1}
    assert agregar_por_tema(conn, leis) == {"Saúde": 2, "Economia": 1}
    assert agregar_vetos_por_tipo(vetos_no_mandato(conn, m)) == {"parcial": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_legislativo.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Crie `app/legislativo.py`:

```python
"""Agregações determinísticas da camada legislativa (por mandato)."""
from __future__ import annotations

from collections import Counter

from app.db import leis_entre, temas_de, vetos_entre


def leis_no_mandato(conn, mandato):
    return leis_entre(conn, mandato.inicio, mandato.fim)


def vetos_no_mandato(conn, mandato):
    return vetos_entre(conn, mandato.inicio, mandato.fim)


def agregar_por_tipo(leis) -> dict[str, int]:
    return dict(Counter(x.tipo for x in leis))


def agregar_por_tema(conn, leis) -> dict[str, int]:
    c: Counter = Counter()
    for lei in leis:
        for tema in temas_de(conn, lei.id):
            c[tema] += 1
    return dict(c)


def agregar_vetos_por_tipo(vetos) -> dict[str, int]:
    return dict(Counter(v.tipo for v in vetos))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_legislativo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/legislativo.py tests/test_legislativo.py
git commit -m "feat: agregações legislativas por mandato (tipo/tema/vetos)"
```

---

### Task 7: Payload + guard + descrever_payload + resumo legislativo

**Files:**
- Modify: `app/models.py`, `app/payload.py`, `app/guard.py`, `app/resumo.py`
- Test: `tests/test_payload.py`, `tests/test_guard.py`

**Interfaces:**
- Produces:
  - `PayloadLegislativoMandato(BaseModel)`: `mandato: str, ano_inicio: int, ano_fim: int, total_leis: int, por_tipo: dict[str,int], por_tema: dict[str,int], total_vetos: int, vetos_por_tipo: dict[str,int]`.
  - `construir_payload_legislativo(conn, mandato) -> PayloadLegislativoMandato`.
  - `descrever_payload(PayloadLegislativoMandato) -> ("legislativo", mandato)`.
  - `guard.numeros_permitidos`/`verificar` aceitam o payload legislativo (contagens + anos).
  - `resumo._REGRAS_LEGISLATIVO`.

- [ ] **Step 1: Write the failing test**

Adicione a `tests/test_payload.py`:

```python
def test_payload_legislativo_e_descricao():
    import datetime as d

    from app.db import conectar, criar_schema, upsert_lei_temas, upsert_leis, upsert_vetos
    from app.models import Lei, Mandato, PayloadLegislativoMandato, Veto
    from app.payload import construir_payload_legislativo, descrever_payload

    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_leis(conn, [Lei(id="a", tipo="LO", numero="1", ano=2023,
                           data=d.date(2023, 2, 1), ementa="e", url="u")])
    upsert_lei_temas(conn, "a", ["Saúde"])
    upsert_vetos(conn, [Veto(id="v", data=d.date(2023, 3, 1), tipo="total",
                             descricao="x", materia="m", url="u")])
    m = Mandato(nome="Lula 3", inicio=d.date(2023, 1, 1), fim=d.date(2026, 12, 31))
    p = construir_payload_legislativo(conn, m)
    assert isinstance(p, PayloadLegislativoMandato)
    assert p.total_leis == 1 and p.por_tipo == {"LO": 1}
    assert p.por_tema == {"Saúde": 1}
    assert p.total_vetos == 1 and p.vetos_por_tipo == {"total": 1}
    assert descrever_payload(p) == ("legislativo", "Lula 3")
```

Adicione a `tests/test_guard.py`:

```python
def test_guard_legislativo_permite_contagens():
    from app.guard import GuardError, verificar
    from app.models import Afirmacao, PayloadLegislativoMandato, ResumoFactual

    p = PayloadLegislativoMandato(
        mandato="Lula 3", ano_inicio=2023, ano_fim=2026, total_leis=5,
        por_tipo={"LO": 5}, por_tema={"Saúde": 2}, total_vetos=3, vetos_por_tipo={"total": 3},
    )
    ok = ResumoFactual(
        paragrafos_por_eixo={"producao": "Foram 5 leis e 3 vetos."},
        afirmacoes=[Afirmacao(texto="leis", valor_citado=5, fonte="Câmara")],
    )
    verificar(ok, p)  # não levanta
    ruim = ResumoFactual(paragrafos_por_eixo={"producao": "Foram 99 leis."}, afirmacoes=[])
    try:
        verificar(ruim, p)
        raise AssertionError("deveria levantar")
    except GuardError:
        pass
```

> Nota: o guard de texto livre só barra números "rate-like" (com decimal/%). Para barrar a
> contagem inteira `99`, o teste usa uma afirmação? Não — `99` aparece como inteiro no texto e
> NÃO é rate-like, então não seria barrado pelo texto livre. Ajuste o teste `ruim` para usar
> uma afirmação estruturada com `valor_citado=99` (que o guard barra):
> `afirmacoes=[Afirmacao(texto="x", valor_citado=99, fonte="f")]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payload.py -k legislativo tests/test_guard.py -k legislativo -v`
Expected: FAIL (`PayloadLegislativoMandato` inexistente).

- [ ] **Step 3: Write minimal implementation**

Em `app/models.py`, ao final:

```python
class PayloadLegislativoMandato(BaseModel):
    mandato: str
    ano_inicio: int
    ano_fim: int
    total_leis: int
    por_tipo: dict[str, int]
    por_tema: dict[str, int]
    total_vetos: int
    vetos_por_tipo: dict[str, int]
```

Em `app/payload.py`, adicione:

```python
def construir_payload_legislativo(conn, mandato):
    from app.legislativo import (
        agregar_por_tema,
        agregar_por_tipo,
        agregar_vetos_por_tipo,
        leis_no_mandato,
        vetos_no_mandato,
    )
    from app.models import PayloadLegislativoMandato

    leis = leis_no_mandato(conn, mandato)
    vetos = vetos_no_mandato(conn, mandato)
    return PayloadLegislativoMandato(
        mandato=mandato.nome,
        ano_inicio=mandato.inicio.year,
        ano_fim=mandato.fim.year,
        total_leis=len(leis),
        por_tipo=agregar_por_tipo(leis),
        por_tema=agregar_por_tema(conn, leis),
        total_vetos=len(vetos),
        vetos_por_tipo=agregar_vetos_por_tipo(vetos),
    )
```

E no `descrever_payload`, adicione antes do `return ("comparacao", ...)`:

```python
    from app.models import PayloadLegislativoMandato
    if isinstance(payload, PayloadLegislativoMandato):
        return ("legislativo", payload.mandato)
```

Em `app/guard.py`:
- Importe `PayloadLegislativoMandato`.
- Em `numeros_permitidos`, adicione antes do `else`:

```python
    if isinstance(payload, PayloadLegislativoMandato):
        nums.add(float(payload.ano_inicio))
        nums.add(float(payload.ano_fim))
        nums.add(float(payload.total_leis))
        nums.add(float(payload.total_vetos))
        for d in (payload.por_tipo, payload.por_tema, payload.vetos_por_tipo):
            for v in d.values():
                nums.add(float(v))
        return nums
```

- Atualize as anotações de tipo de `numeros_permitidos`/`verificar`.

Em `app/resumo.py`, adicione e amplie a união de tipos:

```python
_REGRAS_LEGISLATIVO = (
    "Você redige um resumo FACTUAL e NEUTRO sobre a produção legislativa de um governo. "
    "REGRAS: (1) use SOMENTE as contagens fornecidas no payload (total de leis, por tipo, "
    "por tema, vetos); NUNCA invente ou calcule outros números. (2) Cite a fonte (Câmara/"
    "Senado). (3) Tom neutro, sem juízo de valor. (4) Emenda Constitucional é promulgada pelo "
    "Congresso, não sancionada pelo presidente — registre isso. Responda APENAS com JSON no "
    'schema: {"paragrafos_por_eixo": {"producao": str, "temas": str, "vetos": str}, '
    '"afirmacoes": [{"texto": str, "valor_citado": number, "fonte": str}]}.'
)
```

(Reuse `gerar_resumo(client, payload, regras=_REGRAS_LEGISLATIVO)`; o parâmetro `regras` é
adicionado pelo plano ministerial Task 5 — se este plano rodar antes, adicione `regras` aqui
conforme aquela Task 5.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payload.py tests/test_guard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/payload.py app/guard.py app/resumo.py tests/test_payload.py tests/test_guard.py
git commit -m "feat: payload/guard/resumo legislativos + descrever_payload"
```

---

### Task 8: Aba "Legislativo" na UI + smoke + tracker

**Files:**
- Modify: `app/ui.py`
- Test: `tests/test_ui_smoke.py`
- Modify: `IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: `construir_payload_legislativo`, `leis_no_mandato`, `vetos_no_mandato`,
  `_mostrar_resumo`, `_REGRAS_LEGISLATIVO`, `ClaudeCodeClient`.

- [ ] **Step 1: Write the failing test**

Adicione a `tests/test_ui_smoke.py`:

```python
def test_ui_tem_aba_legislativo():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "Legislativo" in src
    assert "construir_payload_legislativo" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_ui_tem_aba_legislativo -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Em `app/ui.py`, adicione "Legislativo" às abas e o bloco (com imports locais):

```python
    aba_ano, aba_mandato, aba_comp, aba_leg = st.tabs(
        ["Por ano", "Por mandato", "Comparação", "Legislativo"]
    )
```

```python
    with aba_leg:
        from app.legislativo import leis_no_mandato, vetos_no_mandato
        from app.payload import construir_payload_legislativo

        nome_l = st.selectbox("Mandato", [m.nome for m in mandatos], key="mand_leg")
        mandato_l = next(m for m in mandatos if m.nome == nome_l)
        payload_l = construir_payload_legislativo(conn, mandato_l)

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
        st.dataframe(pd.DataFrame([
            {"tipo": x.tipo, "número": x.numero, "data": x.data, "ementa": x.ementa, "url": x.url}
            for x in leis_no_mandato(conn, mandato_l)
        ]))
        st.subheader("Vetos")
        st.dataframe(pd.DataFrame([
            {"data": v.data, "tipo": v.tipo, "matéria": v.materia, "descrição": v.descricao}
            for v in vetos_no_mandato(conn, mandato_l)
        ]))

        st.subheader("Resumo legislativo")
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_l)
```

Em `_mostrar_resumo`, garanta o roteamento de regras: importe `_REGRAS_LEGISLATIVO` e
`PayloadLegislativoMandato` e escolha as regras por tipo de payload (estendendo a lógica
introduzida pelo plano ministerial). Ex.:

```python
        from app.models import PayloadLegislativoMandato, PayloadMinisterialGoverno
        from app.resumo import _REGRAS_LEGISLATIVO, _REGRAS_MINISTERIAL
        if isinstance(payload, PayloadLegislativoMandato):
            resumo = gerar_resumo(client, payload, regras=_REGRAS_LEGISLATIVO)
        elif isinstance(payload, PayloadMinisterialGoverno):
            resumo = gerar_resumo(client, payload, regras=_REGRAS_MINISTERIAL)
        else:
            resumo = gerar_resumo(client, payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite + typecheck + lint**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: tudo verde.

- [ ] **Step 6: Smoke manual + tracker**

Run: `uv run python -m app.ingest_legislativo` (popula leis/vetos; requer rede), depois
`PYTHONPATH=. uv run streamlit run app/ui.py` e confira a aba "Legislativo" (KPIs, gráficos,
tabelas, resumo). Encerre com Ctrl+C.

Em `IMPLEMENTATION_PLAN.md`, "Feito", adicione:
`- Camada legislativa (leis sancionadas + vetos por mandato) — spec/plano 2026-06-21.`

- [ ] **Step 7: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py IMPLEMENTATION_PLAN.md
git commit -m "feat: aba Legislativo (KPIs, gráficos, tabelas, resumo) + tracker"
```

---

## Notas de verificação do plano

- **Cobertura do spec:** fontes confirmadas via spike + fixtures (T1); tabelas leis/vetos/
  lei_temas + storage (T2); fetcher Câmara com filtro "Transformada em Norma Jurídica" e mapa
  de tipos (T3); fetcher vetos do Senado (T4); ingestão resiliente por ano com raw + log (T5);
  agregação por mandato/tipo/tema (T6); payload + guard (contagens) + descrever_payload +
  regras de resumo (T7); UI navegável com KPIs/gráficos/tabelas/resumo (T8).
- **Princípio "LLM nunca calcula":** guard inclui todas as contagens do payload no conjunto
  permitido (T7); resumo só cita o que recebe.
- **Consistência de tipos:** `Lei`/`Veto`/`PayloadLegislativoMandato` definidos em T2/T7 e
  usados igualmente em T3–T8; fetchers retornam a tupla consumida pela ingestão (T5).
- **Dependências:** persistência de resumos (descrever_payload, _mostrar_resumo, salvar_resumo);
  o parâmetro `regras` de `gerar_resumo` vem do plano ministerial T5 — se este plano rodar
  antes, introduza `regras` aqui.
- **Risco principal:** formato exato das duas APIs — mitigado pelo spike (T1) que congela
  fixtures reais; os fetchers têm parsing defensivo de chaves.
- **YAGNI:** sem votações nominais, autoria, TSE, ou join formal veto↔lei.
```
