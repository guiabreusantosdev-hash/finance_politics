# Núcleo Econômico (Spec 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal Streamlit app that ingests Brazilian economic/fiscal/social indicators, computes derived figures deterministically, and generates factual AI summaries (by year, by mandate, and comparing mandates) where the LLM only writes prose and never computes numbers.

**Architecture:** Layered Python app, one direction of data flow: ETL fetchers → SQLite (long format) → deterministic calculation → Pydantic payload → `LLMClient` (Claude Code subscription) → Streamlit UI. Verification is two-layer: a deterministic factuality guard (runs in the loop, no network) plus an LLM-as-judge subagent.

**Tech Stack:** Python 3.12 · uv · pytest · ruff · pyright · pydantic · httpx · pyyaml · streamlit · plotly · claude-agent-sdk (Claude Code subscription).

## Global Constraints

- Python 3.12; dependency management via `uv` (`pyproject.toml`).
- **The LLM never computes numbers** — the backend computes every figure; the model only writes narrative citing values from the payload.
- Every number appearing in a generated summary MUST exist in the payload (enforced by the factuality guard).
- Tests NEVER hit the network and NEVER make real LLM calls: HTTP and `LLMClient` are always mocked. Zero network in the loop.
- SQLite stored in long format: `series`, `observacoes`, `ingestao_log`.
- Raw JSON from each API call is persisted to `raw/<fonte>/...` before normalization. `raw/` is git-ignored.
- Indicators and mandates are defined in `config/*.yaml`; adding a series = editing config, not code.
- Lint (`ruff`) and typecheck (`pyright`) must stay clean at every commit.

---

## File Structure

```
finance_politics/
├── pyproject.toml              # uv project, deps, ruff + pyright config
├── config/
│   ├── indicadores.yaml        # indicator registry
│   └── mandatos.yaml           # presidential mandate windows
├── app/
│   ├── __init__.py
│   ├── models.py               # Pydantic DTOs (Observacao, Indicador, Mandato, payloads, ResumoFactual)
│   ├── config_loader.py        # load + validate config/*.yaml
│   ├── db.py                   # SQLite schema, connection, upsert, queries
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── base.py             # Fetcher protocol + raw-json helper
│   │   ├── bcb.py
│   │   ├── sidra.py
│   │   ├── ipea.py
│   │   └── tesouro.py
│   ├── ingest.py               # orchestration: retry/backoff, raw persistence, upsert, ingestao_log
│   ├── calculo.py              # deterministic: valor_no_periodo, variacao, resumo_ano/mandato, comparacao
│   ├── payload.py              # PayloadAno / PayloadComparacao builders
│   ├── llm.py                  # LLMClient protocol + ClaudeCodeClient
│   ├── resumo.py               # prompt build + generate + schema-validate + retry
│   ├── guard.py                # deterministic factuality guard
│   ├── judge.py                # LLM-as-judge
│   └── ui.py                   # Streamlit (3 tabs)
├── tests/
│   ├── conftest.py
│   ├── fixtures/               # captured raw JSON samples
│   ├── test_config_loader.py
│   ├── test_db.py
│   ├── test_fetchers_bcb.py
│   ├── test_fetchers_sidra.py
│   ├── test_fetchers_ipea.py
│   ├── test_fetchers_tesouro.py
│   ├── test_ingest.py
│   ├── test_calculo.py
│   ├── test_payload.py
│   ├── test_llm.py
│   ├── test_guard.py
│   ├── test_resumo.py
│   └── test_judge.py
└── raw/                        # git-ignored runtime cache
```

---

### Task 1: Project scaffold + first green test

**Files:**
- Create: `pyproject.toml`, `app/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`, `.gitignore` (modify)

**Interfaces:**
- Consumes: nothing.
- Produces: a working `uv` project; `uv run pytest` exits 0.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
import app


def test_package_importable():
    assert app is not None
```

- [ ] **Step 2: Create the package + project files**

`app/__init__.py`:
```python
"""finance_politics — personal government-performance analysis tool."""
```

`tests/__init__.py`: (empty file)

`pyproject.toml`:
```toml
[project]
name = "finance-politics"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "streamlit>=1.36",
    "plotly>=5.22",
    "claude-agent-sdk>=0.1",
]

[dependency-groups]
dev = ["pytest>=8.2", "ruff>=0.5", "pyright>=1.1"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pyright]
include = ["app", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "standard"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Append to `.gitignore`:
```
raw/
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Sync and run the test**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS (`test_package_importable`). If `claude-agent-sdk` version is unavailable, relax the pin to `claude-agent-sdk` (no version) and re-sync.

- [ ] **Step 4: Verify lint + typecheck clean**

Run: `uv run ruff check . && uv run pyright`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app/__init__.py tests/ .gitignore uv.lock
git commit -m "chore: scaffold uv project with pytest/ruff/pyright"
```

---

### Task 2: Core DTOs (`app/models.py`)

**Files:**
- Create: `app/models.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Observacao(serie_id: str, data: datetime.date, valor: float)`
  - `Indicador(id: str, fonte: str, codigo_fonte: str, nome: str, unidade: str, periodicidade: Literal["mensal","trimestral","anual","diaria"], eixo: Literal["macro","fiscal","social"], metodo_anual: Literal["fim_periodo","media","acumulado_12m"])`
  - `Mandato(nome: str, inicio: datetime.date, fim: datetime.date)`
  - `ValorIndicador(nome: str, valor: float | None, unidade: str, fonte: str, data_ref: datetime.date | None)`
  - `PayloadAno(ano: int, indicadores: list[ValorIndicador], faltantes: list[str])`
  - `DeltaIndicador(nome: str, valor_a: float | None, valor_b: float | None, delta: float | None, unidade: str, fonte: str)`
  - `PayloadComparacao(mandato_a: str, mandato_b: str, deltas: list[DeltaIndicador])`
  - `Afirmacao(texto: str, valor_citado: float, fonte: str)`
  - `ResumoFactual(paragrafos_por_eixo: dict[str, str], afirmacoes: list[Afirmacao])`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
import datetime

from app.models import Indicador, Observacao, PayloadAno, ResumoFactual, ValorIndicador


def test_observacao_roundtrip():
    o = Observacao(serie_id="bcb_432_selic", data=datetime.date(2024, 1, 1), valor=11.75)
    assert o.valor == 11.75


def test_indicador_rejects_bad_eixo():
    import pytest

    with pytest.raises(ValueError):
        Indicador(
            id="x", fonte="BCB", codigo_fonte="1", nome="X", unidade="%",
            periodicidade="mensal", eixo="invalido", metodo_anual="media",
        )


def test_payload_ano_holds_faltantes():
    p = PayloadAno(
        ano=2024,
        indicadores=[ValorIndicador(nome="Selic", valor=11.75, unidade="% a.a.",
                                    fonte="BCB", data_ref=datetime.date(2024, 12, 1))],
        faltantes=["IDH-M"],
    )
    assert p.faltantes == ["IDH-M"]


def test_resumo_factual_structure():
    r = ResumoFactual(paragrafos_por_eixo={"macro": "txt"}, afirmacoes=[])
    assert r.paragrafos_por_eixo["macro"] == "txt"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL (`ModuleNotFoundError: app.models`).

- [ ] **Step 3: Implement `app/models.py`**

```python
"""Pydantic DTOs shared across layers."""
from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel

Periodicidade = Literal["mensal", "trimestral", "anual", "diaria"]
Eixo = Literal["macro", "fiscal", "social"]
MetodoAnual = Literal["fim_periodo", "media", "acumulado_12m"]


class Observacao(BaseModel):
    serie_id: str
    data: datetime.date
    valor: float


class Indicador(BaseModel):
    id: str
    fonte: str
    codigo_fonte: str
    nome: str
    unidade: str
    periodicidade: Periodicidade
    eixo: Eixo
    metodo_anual: MetodoAnual


class Mandato(BaseModel):
    nome: str
    inicio: datetime.date
    fim: datetime.date


class ValorIndicador(BaseModel):
    nome: str
    valor: float | None
    unidade: str
    fonte: str
    data_ref: datetime.date | None


class PayloadAno(BaseModel):
    ano: int
    indicadores: list[ValorIndicador]
    faltantes: list[str]


class DeltaIndicador(BaseModel):
    nome: str
    valor_a: float | None
    valor_b: float | None
    delta: float | None
    unidade: str
    fonte: str


class PayloadComparacao(BaseModel):
    mandato_a: str
    mandato_b: str
    deltas: list[DeltaIndicador]


class Afirmacao(BaseModel):
    texto: str
    valor_citado: float
    fonte: str


class ResumoFactual(BaseModel):
    paragrafos_por_eixo: dict[str, str]
    afirmacoes: list[Afirmacao]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_models.py -v && uv run pyright`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: core pydantic DTOs"
```

---

### Task 3: Config registry + loader (`config/*.yaml`, `app/config_loader.py`)

**Files:**
- Create: `config/indicadores.yaml`, `config/mandatos.yaml`, `app/config_loader.py`, `tests/test_config_loader.py`

**Interfaces:**
- Consumes: `Indicador`, `Mandato` from `app.models`.
- Produces:
  - `carregar_indicadores(path: str = "config/indicadores.yaml") -> list[Indicador]`
  - `carregar_mandatos(path: str = "config/mandatos.yaml") -> list[Mandato]`

- [ ] **Step 1: Create the config files**

`config/indicadores.yaml` (starter set — **verify each `codigo_fonte` against the official portal before ingesting**, per spec):
```yaml
# id, fonte, codigo_fonte, nome, unidade, periodicidade, eixo, metodo_anual
- id: bcb_432_selic
  fonte: BCB
  codigo_fonte: "432"
  nome: Meta Selic
  unidade: "% a.a."
  periodicidade: mensal
  eixo: macro
  metodo_anual: fim_periodo
- id: bcb_433_ipca
  fonte: BCB
  codigo_fonte: "433"
  nome: IPCA
  unidade: "% (12m)"
  periodicidade: mensal
  eixo: macro
  metodo_anual: acumulado_12m
- id: bcb_1_cambio
  fonte: BCB
  codigo_fonte: "1"
  nome: Câmbio R$/US$ (venda)
  unidade: R$/US$
  periodicidade: diaria
  eixo: macro
  metodo_anual: fim_periodo
- id: sidra_6468_desemprego
  fonte: IBGE
  codigo_fonte: "6468"
  nome: Taxa de desocupação (PNAD)
  unidade: "%"
  periodicidade: trimestral
  eixo: macro
  metodo_anual: media
- id: ipea_pib_real_var
  fonte: IPEA
  codigo_fonte: "PIB_real_var"
  nome: PIB real (variação anual)
  unidade: "%"
  periodicidade: anual
  eixo: macro
  metodo_anual: fim_periodo
- id: bcb_13762_dbgg
  fonte: BCB
  codigo_fonte: "13762"
  nome: Dívida Bruta do Governo Geral (% PIB)
  unidade: "% do PIB"
  periodicidade: mensal
  eixo: fiscal
  metodo_anual: fim_periodo
- id: bcb_5793_primario
  fonte: BCB
  codigo_fonte: "5793"
  nome: Resultado primário (% PIB, 12m)
  unidade: "% do PIB"
  periodicidade: mensal
  eixo: fiscal
  metodo_anual: fim_periodo
- id: ipea_gini
  fonte: IPEA
  codigo_fonte: "GINI"
  nome: Índice de Gini
  unidade: índice
  periodicidade: anual
  eixo: social
  metodo_anual: fim_periodo
```

`config/mandatos.yaml`:
```yaml
- nome: Lula 1
  inicio: 2003-01-01
  fim: 2006-12-31
- nome: Lula 2
  inicio: 2007-01-01
  fim: 2010-12-31
- nome: Dilma 1
  inicio: 2011-01-01
  fim: 2014-12-31
- nome: Dilma/Temer
  inicio: 2015-01-01
  fim: 2018-12-31
- nome: Bolsonaro
  inicio: 2019-01-01
  fim: 2022-12-31
- nome: Lula 3
  inicio: 2023-01-01
  fim: 2026-12-31
```

- [ ] **Step 2: Write the failing test**

`tests/test_config_loader.py`:
```python
from app.config_loader import carregar_indicadores, carregar_mandatos


def test_carrega_indicadores_reais():
    inds = carregar_indicadores()
    assert len(inds) >= 8
    ids = {i.id for i in inds}
    assert "bcb_432_selic" in ids
    assert all(i.eixo in {"macro", "fiscal", "social"} for i in inds)


def test_carrega_mandatos_reais():
    mandatos = carregar_mandatos()
    nomes = {m.nome for m in mandatos}
    assert {"Lula 1", "Bolsonaro", "Lula 3"} <= nomes
    for m in mandatos:
        assert m.inicio < m.fim
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: FAIL (`ModuleNotFoundError: app.config_loader`).

- [ ] **Step 4: Implement `app/config_loader.py`**

```python
"""Load and validate the indicator and mandate registries."""
from __future__ import annotations

import yaml

from app.models import Indicador, Mandato


def carregar_indicadores(path: str = "config/indicadores.yaml") -> list[Indicador]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return [Indicador.model_validate(item) for item in raw]


def carregar_mandatos(path: str = "config/mandatos.yaml") -> list[Mandato]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return [Mandato.model_validate(item) for item in raw]
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/ app/config_loader.py tests/test_config_loader.py
git commit -m "feat: indicator + mandate config registry and loader"
```

---

### Task 4: SQLite storage layer (`app/db.py`)

**Files:**
- Create: `app/db.py`, `tests/test_db.py`

**Interfaces:**
- Consumes: `Indicador`, `Observacao` from `app.models`.
- Produces:
  - `conectar(path: str = "finance.db") -> sqlite3.Connection`
  - `criar_schema(conn) -> None`
  - `upsert_serie(conn, ind: Indicador) -> None`
  - `upsert_observacoes(conn, obs: list[Observacao]) -> int` (returns rows written)
  - `registrar_ingestao(conn, serie_id: str, executado_em: str, status: str, n: int, erro: str | None) -> None`
  - `observacoes_da_serie(conn, serie_id: str) -> list[Observacao]`

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
import datetime

from app.db import (
    conectar,
    criar_schema,
    observacoes_da_serie,
    upsert_observacoes,
    upsert_serie,
)
from app.models import Indicador, Observacao


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


def test_upsert_is_idempotent():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_serie(conn, _ind())
    obs = [Observacao(serie_id="bcb_432_selic", data=datetime.date(2024, 1, 1), valor=11.75)]
    upsert_observacoes(conn, obs)
    upsert_observacoes(conn, obs)  # second time must not duplicate
    stored = observacoes_da_serie(conn, "bcb_432_selic")
    assert len(stored) == 1
    assert stored[0].valor == 11.75


def test_upsert_updates_value():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_serie(conn, _ind())
    d = datetime.date(2024, 1, 1)
    upsert_observacoes(conn, [Observacao(serie_id="bcb_432_selic", data=d, valor=10.0)])
    upsert_observacoes(conn, [Observacao(serie_id="bcb_432_selic", data=d, valor=11.0)])
    stored = observacoes_da_serie(conn, "bcb_432_selic")
    assert len(stored) == 1
    assert stored[0].valor == 11.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL (`ModuleNotFoundError: app.db`).

- [ ] **Step 3: Implement `app/db.py`**

```python
"""SQLite storage: schema, upserts, queries (long format)."""
from __future__ import annotations

import datetime
import sqlite3

from app.models import Indicador, Observacao

_SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY, fonte TEXT, codigo_fonte TEXT, nome TEXT,
    unidade TEXT, periodicidade TEXT, eixo TEXT
);
CREATE TABLE IF NOT EXISTS observacoes (
    serie_id TEXT, data TEXT, valor REAL,
    PRIMARY KEY (serie_id, data),
    FOREIGN KEY (serie_id) REFERENCES series(id)
);
CREATE TABLE IF NOT EXISTS ingestao_log (
    serie_id TEXT, executado_em TEXT, status TEXT, n_registros INTEGER, erro TEXT
);
"""


def conectar(path: str = "finance.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def upsert_serie(conn: sqlite3.Connection, ind: Indicador) -> None:
    conn.execute(
        """INSERT INTO series (id, fonte, codigo_fonte, nome, unidade, periodicidade, eixo)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             fonte=excluded.fonte, codigo_fonte=excluded.codigo_fonte, nome=excluded.nome,
             unidade=excluded.unidade, periodicidade=excluded.periodicidade, eixo=excluded.eixo""",
        (ind.id, ind.fonte, ind.codigo_fonte, ind.nome, ind.unidade, ind.periodicidade, ind.eixo),
    )
    conn.commit()


def upsert_observacoes(conn: sqlite3.Connection, obs: list[Observacao]) -> int:
    rows = [(o.serie_id, o.data.isoformat(), o.valor) for o in obs]
    conn.executemany(
        """INSERT INTO observacoes (serie_id, data, valor) VALUES (?, ?, ?)
           ON CONFLICT(serie_id, data) DO UPDATE SET valor=excluded.valor""",
        rows,
    )
    conn.commit()
    return len(rows)


def registrar_ingestao(
    conn: sqlite3.Connection, serie_id: str, executado_em: str, status: str,
    n: int, erro: str | None,
) -> None:
    conn.execute(
        "INSERT INTO ingestao_log (serie_id, executado_em, status, n_registros, erro) VALUES (?, ?, ?, ?, ?)",
        (serie_id, executado_em, status, n, erro),
    )
    conn.commit()


def observacoes_da_serie(conn: sqlite3.Connection, serie_id: str) -> list[Observacao]:
    cur = conn.execute(
        "SELECT serie_id, data, valor FROM observacoes WHERE serie_id = ? ORDER BY data", (serie_id,)
    )
    return [
        Observacao(serie_id=r[0], data=datetime.date.fromisoformat(r[1]), valor=r[2])
        for r in cur.fetchall()
    ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_db.py -v && uv run pyright`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: sqlite storage layer with idempotent upserts"
```

---

### Task 5: Fetcher base + BCB fetcher (`app/fetchers/base.py`, `app/fetchers/bcb.py`)

**Files:**
- Create: `app/fetchers/__init__.py`, `app/fetchers/base.py`, `app/fetchers/bcb.py`, `tests/test_fetchers_bcb.py`, `tests/fixtures/bcb_432.json`

**Interfaces:**
- Consumes: `Indicador`, `Observacao`.
- Produces:
  - `class Fetcher(Protocol)` with `def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]`
  - `class BCBFetcher` implementing `Fetcher`
  - `URL_BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"`

- [ ] **Step 1: Create the fixture**

`tests/fixtures/bcb_432.json`:
```json
[
  {"data": "01/01/2024", "valor": "11.75"},
  {"data": "01/02/2024", "valor": "11.25"}
]
```

- [ ] **Step 2: Write the failing test**

`tests/test_fetchers_bcb.py`:
```python
import datetime
import json
import pathlib

import httpx

from app.fetchers.bcb import BCBFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "bcb_432.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


def test_bcb_parses_brazilian_dates_and_floats():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = BCBFetcher().fetch(_ind(), client)
    assert obs[0].data == datetime.date(2024, 1, 1)
    assert obs[0].valor == 11.75
    assert obs[1].valor == 11.25
    assert all(o.serie_id == "bcb_432_selic" for o in obs)
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_fetchers_bcb.py -v`
Expected: FAIL (`ModuleNotFoundError: app.fetchers.bcb`).

- [ ] **Step 4: Implement base + BCB**

`app/fetchers/__init__.py`: (empty file)

`app/fetchers/base.py`:
```python
"""Fetcher protocol shared by all source adapters."""
from __future__ import annotations

from typing import Protocol

import httpx

from app.models import Indicador, Observacao


class Fetcher(Protocol):
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]: ...
```

`app/fetchers/bcb.py`:
```python
"""BCB/SGS REST adapter."""
from __future__ import annotations

import datetime

import httpx

from app.models import Indicador, Observacao

URL_BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"


class BCBFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]:
        resp = client.get(URL_BCB.format(codigo=ind.codigo_fonte), timeout=30)
        resp.raise_for_status()
        out: list[Observacao] = []
        for row in resp.json():
            data = datetime.datetime.strptime(row["data"], "%d/%m/%Y").date()
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["valor"])))
        return out
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_fetchers_bcb.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/fetchers/ tests/test_fetchers_bcb.py tests/fixtures/bcb_432.json
git commit -m "feat: fetcher protocol + BCB/SGS adapter"
```

---

### Task 6: SIDRA fetcher (`app/fetchers/sidra.py`)

**Files:**
- Create: `app/fetchers/sidra.py`, `tests/test_fetchers_sidra.py`, `tests/fixtures/sidra_6468.json`

**Interfaces:**
- Consumes: `Indicador`, `Observacao`.
- Produces: `class SIDRAFetcher` implementing `Fetcher`; `URL_SIDRA` template.

- [ ] **Step 1: Create the fixture** (SIDRA returns a header row then data rows)

`tests/fixtures/sidra_6468.json`:
```json
[
  {"D2C": "Trimestre", "V": "Valor"},
  {"D2C": "202401", "V": "7.9"},
  {"D2C": "202402", "V": "6.9"}
]
```

- [ ] **Step 2: Write the failing test**

`tests/test_fetchers_sidra.py`:
```python
import datetime
import json
import pathlib

import httpx

from app.fetchers.sidra import SIDRAFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "sidra_6468.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="sidra_6468_desemprego", fonte="IBGE", codigo_fonte="6468",
        nome="Taxa de desocupação", unidade="%", periodicidade="trimestral",
        eixo="macro", metodo_anual="media",
    )


def test_sidra_skips_header_and_parses_quarter():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = SIDRAFetcher().fetch(_ind(), client)
    assert len(obs) == 2  # header row skipped
    assert obs[0].data == datetime.date(2024, 1, 1)   # 2024 Q1 -> Jan
    assert obs[0].valor == 7.9
    assert obs[1].data == datetime.date(2024, 4, 1)   # 2024 Q2 -> Apr
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_fetchers_sidra.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement SIDRA fetcher**

`app/fetchers/sidra.py`:
```python
"""IBGE/SIDRA aggregate-table adapter (quarterly headline series)."""
from __future__ import annotations

import datetime

import httpx

from app.models import Indicador, Observacao

URL_SIDRA = (
    "https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/allxp/p/all?formato=json"
)


def _periodo_para_data(p: str) -> datetime.date:
    ano = int(p[:4])
    if len(p) == 6:  # YYYYNN quarter or month code
        nn = int(p[4:])
        mes = (nn - 1) * 3 + 1 if nn <= 4 else nn  # treat as quarter
        return datetime.date(ano, mes, 1)
    return datetime.date(ano, 1, 1)


class SIDRAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]:
        resp = client.get(URL_SIDRA.format(tabela=ind.codigo_fonte), timeout=60)
        resp.raise_for_status()
        rows = resp.json()
        out: list[Observacao] = []
        for row in rows[1:]:  # first row is the header / labels
            try:
                valor = float(row["V"])
            except (TypeError, ValueError):
                continue  # "..." / "-" -> missing, skip
            out.append(Observacao(serie_id=ind.id, data=_periodo_para_data(row["D2C"]), valor=valor))
        return out
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_fetchers_sidra.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/fetchers/sidra.py tests/test_fetchers_sidra.py tests/fixtures/sidra_6468.json
git commit -m "feat: SIDRA adapter (header skip + quarter parsing)"
```

---

### Task 7: IPEA + Tesouro fetchers (`app/fetchers/ipea.py`, `app/fetchers/tesouro.py`)

**Files:**
- Create: `app/fetchers/ipea.py`, `app/fetchers/tesouro.py`, `tests/test_fetchers_ipea.py`, `tests/test_fetchers_tesouro.py`, `tests/fixtures/ipea_gini.json`, `tests/fixtures/tesouro_sample.json`

**Interfaces:**
- Consumes: `Indicador`, `Observacao`.
- Produces: `class IPEAFetcher`, `class TesouroFetcher` implementing `Fetcher`.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/ipea_gini.json` (IPEADATA OData v4 shape):
```json
{"value": [
  {"SERCODIGO": "GINI", "VALDATA": "2014-01-01T00:00:00-02:00", "VALVALOR": 0.518},
  {"SERCODIGO": "GINI", "VALDATA": "2015-01-01T00:00:00-02:00", "VALVALOR": 0.524}
]}
```

`tests/fixtures/tesouro_sample.json`:
```json
{"data": [
  {"referencia": "2023-12-01", "valor": 74.3},
  {"referencia": "2024-12-01", "valor": 76.1}
]}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_fetchers_ipea.py`:
```python
import datetime
import json
import pathlib

import httpx

from app.fetchers.ipea import IPEAFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "ipea_gini.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="ipea_gini", fonte="IPEA", codigo_fonte="GINI", nome="Índice de Gini",
        unidade="índice", periodicidade="anual", eixo="social", metodo_anual="fim_periodo",
    )


def test_ipea_odata_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = IPEAFetcher().fetch(_ind(), client)
    assert obs[0].data == datetime.date(2014, 1, 1)
    assert obs[0].valor == 0.518
    assert obs[1].valor == 0.524
```

`tests/test_fetchers_tesouro.py`:
```python
import datetime
import json
import pathlib

import httpx

from app.fetchers.tesouro import TesouroFetcher
from app.models import Indicador

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "tesouro_sample.json").read_text())


def _ind() -> Indicador:
    return Indicador(
        id="tesouro_dpf", fonte="TESOURO", codigo_fonte="dpf", nome="DPF",
        unidade="% do PIB", periodicidade="mensal", eixo="fiscal", metodo_anual="fim_periodo",
    )


def test_tesouro_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    obs = TesouroFetcher().fetch(_ind(), client)
    assert obs[0].data == datetime.date(2023, 12, 1)
    assert obs[1].valor == 76.1
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_fetchers_ipea.py tests/test_fetchers_tesouro.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement both fetchers**

`app/fetchers/ipea.py`:
```python
"""IPEADATA OData v4 adapter."""
from __future__ import annotations

import datetime

import httpx

from app.models import Indicador, Observacao

URL_IPEA = "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"


class IPEAFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]:
        resp = client.get(URL_IPEA.format(codigo=ind.codigo_fonte), timeout=60)
        resp.raise_for_status()
        out: list[Observacao] = []
        for row in resp.json()["value"]:
            if row.get("VALVALOR") is None:
                continue
            data = datetime.date.fromisoformat(row["VALDATA"][:10])
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["VALVALOR"])))
        return out
```

`app/fetchers/tesouro.py`:
```python
"""Tesouro Nacional CKAN/datalake adapter (generic referencia/valor shape)."""
from __future__ import annotations

import datetime

import httpx

from app.models import Indicador, Observacao

URL_TESOURO = "https://apidatalake.tesouro.gov.br/ords/custom/{codigo}"


class TesouroFetcher:
    def fetch(self, ind: Indicador, client: httpx.Client) -> list[Observacao]:
        resp = client.get(URL_TESOURO.format(codigo=ind.codigo_fonte), timeout=60)
        resp.raise_for_status()
        out: list[Observacao] = []
        for row in resp.json()["data"]:
            data = datetime.date.fromisoformat(row["referencia"][:10])
            out.append(Observacao(serie_id=ind.id, data=data, valor=float(row["valor"])))
        return out
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_fetchers_ipea.py tests/test_fetchers_tesouro.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/fetchers/ipea.py app/fetchers/tesouro.py tests/test_fetchers_ipea.py tests/test_fetchers_tesouro.py tests/fixtures/ipea_gini.json tests/fixtures/tesouro_sample.json
git commit -m "feat: IPEA (OData) + Tesouro adapters"
```

---

### Task 8: Ingestion orchestration (`app/ingest.py`)

**Files:**
- Create: `app/ingest.py`, `tests/test_ingest.py`

**Interfaces:**
- Consumes: `carregar_indicadores`, db functions, all fetchers.
- Produces:
  - `FETCHERS: dict[str, Fetcher]` keyed by `fonte` ("BCB","IBGE","IPEA","TESOURO")
  - `salvar_raw(fonte: str, serie_id: str, payload: object, agora: str, base: str = "raw") -> str`
  - `fetch_com_retry(fetcher, ind, client, tentativas: int = 3) -> list[Observacao]` (exponential backoff via `time.sleep`)
  - `ingerir_indicador(conn, ind, client, agora: str) -> int` (persists raw, upserts, logs; on failure logs error and returns 0 without raising)
  - `main() -> None` (CLI entrypoint; loads config, opens db + httpx client, iterates)

- [ ] **Step 1: Write the failing test**

`tests/test_ingest.py`:
```python
import datetime

from app.db import conectar, criar_schema, observacoes_da_serie
from app.ingest import fetch_com_retry, ingerir_indicador
from app.models import Indicador, Observacao


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


class _FlakyFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, ind, client):
        self.calls += 1
        if self.calls < 2:
            raise RuntimeError("API instável")
        return [Observacao(serie_id=ind.id, data=datetime.date(2024, 1, 1), valor=11.75)]


class _DeadFetcher:
    def fetch(self, ind, client):
        raise RuntimeError("fonte fora do ar")


def test_retry_eventually_succeeds(monkeypatch):
    monkeypatch.setattr("app.ingest.time.sleep", lambda _s: None)
    obs = fetch_com_retry(_FlakyFetcher(), _ind(), client=None, tentativas=3)
    assert len(obs) == 1


def test_ingerir_indicador_logs_failure_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr("app.ingest.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.ingest.FETCHERS", {"BCB": _DeadFetcher()})
    conn = conectar(":memory:")
    criar_schema(conn)
    n = ingerir_indicador(conn, _ind(), client=None, agora="2026-06-20T00:00:00")
    assert n == 0
    log = conn.execute("SELECT status FROM ingestao_log").fetchall()
    assert log and log[0][0] == "erro"


def test_ingerir_indicador_success_persists(monkeypatch, tmp_path):
    monkeypatch.setattr("app.ingest.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.ingest.FETCHERS", {"BCB": _FlakyFetcher()})
    monkeypatch.setattr("app.ingest.salvar_raw", lambda *a, **k: str(tmp_path / "r.json"))
    conn = conectar(":memory:")
    criar_schema(conn)
    n = ingerir_indicador(conn, _ind(), client=None, agora="2026-06-20T00:00:00")
    assert n == 1
    assert len(observacoes_da_serie(conn, "bcb_432_selic")) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: FAIL (`ModuleNotFoundError: app.ingest`).

- [ ] **Step 3: Implement `app/ingest.py`**

```python
"""Ingestion orchestration: retry/backoff, raw persistence, upsert, logging."""
from __future__ import annotations

import datetime
import json
import pathlib
import time

import httpx

from app.config_loader import carregar_indicadores
from app.db import (
    conectar,
    criar_schema,
    registrar_ingestao,
    upsert_observacoes,
    upsert_serie,
)
from app.fetchers.base import Fetcher
from app.fetchers.bcb import BCBFetcher
from app.fetchers.ipea import IPEAFetcher
from app.fetchers.sidra import SIDRAFetcher
from app.fetchers.tesouro import TesouroFetcher
from app.models import Indicador, Observacao

FETCHERS: dict[str, Fetcher] = {
    "BCB": BCBFetcher(),
    "IBGE": SIDRAFetcher(),
    "IPEA": IPEAFetcher(),
    "TESOURO": TesouroFetcher(),
}


def salvar_raw(fonte: str, serie_id: str, payload: object, agora: str, base: str = "raw") -> str:
    pasta = pathlib.Path(base) / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{serie_id}_{agora.replace(':', '-')}.json"
    caminho.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return str(caminho)


def fetch_com_retry(
    fetcher: Fetcher, ind: Indicador, client: httpx.Client | None, tentativas: int = 3
) -> list[Observacao]:
    erro: Exception | None = None
    for i in range(tentativas):
        try:
            return fetcher.fetch(ind, client)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - APIs públicas instáveis, tentar de novo
            erro = exc
            time.sleep(2**i)
    raise erro if erro else RuntimeError("falha desconhecida")


def ingerir_indicador(
    conn, ind: Indicador, client: httpx.Client | None, agora: str
) -> int:
    upsert_serie(conn, ind)
    fetcher = FETCHERS[ind.fonte]
    try:
        obs = fetch_com_retry(fetcher, ind, client)
    except Exception as exc:  # noqa: BLE001 - registra falha e segue, não derruba o pipeline
        registrar_ingestao(conn, ind.id, agora, "erro", 0, str(exc))
        return 0
    salvar_raw(ind.fonte, ind.id, [o.model_dump() for o in obs], agora)
    n = upsert_observacoes(conn, obs)
    registrar_ingestao(conn, ind.id, agora, "ok", n, None)
    return n


def main() -> None:
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    conn = conectar()
    criar_schema(conn)
    with httpx.Client(headers={"User-Agent": "finance_politics/0.1"}) as client:
        for ind in carregar_indicadores():
            n = ingerir_indicador(conn, ind, client, agora)
            print(f"{ind.id}: {n} observações")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ingest.py -v && uv run pyright`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/ingest.py tests/test_ingest.py
git commit -m "feat: ingestion orchestration with retry, raw cache, error logging"
```

---

### Task 9: Deterministic calculation (`app/calculo.py`)

**Files:**
- Create: `app/calculo.py`, `tests/test_calculo.py`

**Interfaces:**
- Consumes: `Indicador`, `Observacao`, `Mandato`.
- Produces:
  - `valor_no_periodo(obs: list[Observacao], ind: Indicador, ano: int) -> float | None`
  - `variacao(de: float | None, ate: float | None) -> float | None` (percentage change; None if either side None)
  - `valor_no_mandato(obs, ind, mandato, ponta: Literal["inicio","fim"]) -> float | None`

- [ ] **Step 1: Write the failing test**

`tests/test_calculo.py`:
```python
import datetime

from app.calculo import valor_no_periodo, variacao
from app.models import Indicador, Observacao


def _ind(metodo: str, periodicidade: str = "mensal") -> Indicador:
    return Indicador(
        id="s", fonte="BCB", codigo_fonte="1", nome="S", unidade="u",
        periodicidade=periodicidade, eixo="macro", metodo_anual=metodo,
    )


def _serie(pares):
    return [Observacao(serie_id="s", data=d, valor=v) for d, v in pares]


def test_fim_periodo_pega_ultimo_do_ano():
    obs = _serie([
        (datetime.date(2024, 1, 1), 10.0),
        (datetime.date(2024, 12, 1), 12.0),
        (datetime.date(2025, 1, 1), 13.0),
    ])
    assert valor_no_periodo(obs, _ind("fim_periodo"), 2024) == 12.0


def test_media_calcula_media_do_ano():
    obs = _serie([
        (datetime.date(2024, 3, 1), 8.0),
        (datetime.date(2024, 6, 1), 6.0),
    ])
    assert valor_no_periodo(obs, _ind("media"), 2024) == 7.0


def test_acumulado_12m_compoe_variacoes_mensais():
    # dois meses de 1% cada -> (1.01*1.01 - 1) ~ 2.01%
    obs = _serie([(datetime.date(2024, 11, 1), 1.0), (datetime.date(2024, 12, 1), 1.0)])
    got = valor_no_periodo(obs, _ind("acumulado_12m"), 2024)
    assert got is not None
    assert abs(got - 2.01) < 1e-6


def test_valor_no_periodo_sem_dado_retorna_none():
    assert valor_no_periodo([], _ind("media"), 2024) is None


def test_variacao_percentual():
    assert variacao(100.0, 110.0) == 10.0
    assert variacao(None, 110.0) is None
    assert variacao(0.0, 5.0) is None  # evita divisão por zero
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_calculo.py -v`
Expected: FAIL (`ModuleNotFoundError: app.calculo`).

- [ ] **Step 3: Implement `app/calculo.py`**

```python
"""Deterministic indicator math. The LLM never runs anything here."""
from __future__ import annotations

from typing import Literal

from app.models import Indicador, Mandato, Observacao


def _do_ano(obs: list[Observacao], ano: int) -> list[Observacao]:
    return sorted((o for o in obs if o.data.year == ano), key=lambda o: o.data)


def valor_no_periodo(obs: list[Observacao], ind: Indicador, ano: int) -> float | None:
    do_ano = _do_ano(obs, ano)
    if not do_ano:
        return None
    if ind.metodo_anual == "fim_periodo":
        return do_ano[-1].valor
    if ind.metodo_anual == "media":
        return sum(o.valor for o in do_ano) / len(do_ano)
    if ind.metodo_anual == "acumulado_12m":
        acc = 1.0
        for o in do_ano:
            acc *= 1 + o.valor / 100
        return (acc - 1) * 100
    return None


def variacao(de: float | None, ate: float | None) -> float | None:
    if de is None or ate is None or de == 0:
        return None
    return (ate - de) / de * 100


def valor_no_mandato(
    obs: list[Observacao], ind: Indicador, mandato: Mandato, ponta: Literal["inicio", "fim"]
) -> float | None:
    ano = mandato.inicio.year if ponta == "inicio" else mandato.fim.year
    return valor_no_periodo(obs, ind, ano)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_calculo.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add app/calculo.py tests/test_calculo.py
git commit -m "feat: deterministic annual aggregation + variation"
```

---

### Task 10: Payload builders (`app/payload.py`)

**Files:**
- Create: `app/payload.py`, `tests/test_payload.py`

**Interfaces:**
- Consumes: `calculo`, db `observacoes_da_serie`, `Indicador`, `Mandato`, payload DTOs.
- Produces:
  - `construir_payload_ano(conn, indicadores: list[Indicador], ano: int) -> PayloadAno`
  - `construir_payload_comparacao(conn, indicadores, mand_a: Mandato, mand_b: Mandato) -> PayloadComparacao`

- [ ] **Step 1: Write the failing test**

`tests/test_payload.py`:
```python
import datetime

from app.db import conectar, criar_schema, upsert_observacoes, upsert_serie
from app.models import Indicador, Mandato, Observacao
from app.payload import construir_payload_ano, construir_payload_comparacao


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


def _conn_com_dados():
    conn = conectar(":memory:")
    criar_schema(conn)
    upsert_serie(conn, _ind())
    upsert_observacoes(conn, [
        Observacao(serie_id="bcb_432_selic", data=datetime.date(2014, 12, 1), valor=11.75),
        Observacao(serie_id="bcb_432_selic", data=datetime.date(2018, 12, 1), valor=6.5),
    ])
    return conn


def test_payload_ano_marca_faltante():
    conn = _conn_com_dados()
    p = construir_payload_ano(conn, [_ind()], 2014)
    assert p.indicadores[0].valor == 11.75
    assert p.indicadores[0].fonte == "BCB"
    p_vazio = construir_payload_ano(conn, [_ind()], 2099)
    assert "Meta Selic" in p_vazio.faltantes


def test_payload_comparacao_calcula_delta():
    conn = _conn_com_dados()
    a = Mandato(nome="Dilma 1", inicio=datetime.date(2011, 1, 1), fim=datetime.date(2014, 12, 31))
    b = Mandato(nome="Dilma/Temer", inicio=datetime.date(2015, 1, 1), fim=datetime.date(2018, 12, 31))
    p = construir_payload_comparacao(conn, [_ind()], a, b)
    d = p.deltas[0]
    assert d.valor_a == 11.75
    assert d.valor_b == 6.5
    assert abs(d.delta - (-5.25)) < 1e-9
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_payload.py -v`
Expected: FAIL (`ModuleNotFoundError: app.payload`).

- [ ] **Step 3: Implement `app/payload.py`**

```python
"""Build structured payloads the LLM will narrate (never compute)."""
from __future__ import annotations

import datetime

from app.calculo import valor_no_mandato, valor_no_periodo
from app.db import observacoes_da_serie
from app.models import (
    DeltaIndicador,
    Indicador,
    Mandato,
    PayloadAno,
    PayloadComparacao,
    ValorIndicador,
)


def _data_ref_do_ano(obs, ano: int) -> datetime.date | None:
    do_ano = sorted((o.data for o in obs if o.data.year == ano))
    return do_ano[-1] if do_ano else None


def construir_payload_ano(conn, indicadores: list[Indicador], ano: int) -> PayloadAno:
    valores: list[ValorIndicador] = []
    faltantes: list[str] = []
    for ind in indicadores:
        obs = observacoes_da_serie(conn, ind.id)
        v = valor_no_periodo(obs, ind, ano)
        if v is None:
            faltantes.append(ind.nome)
        valores.append(ValorIndicador(
            nome=ind.nome, valor=v, unidade=ind.unidade, fonte=ind.fonte,
            data_ref=_data_ref_do_ano(obs, ano),
        ))
    return PayloadAno(ano=ano, indicadores=valores, faltantes=faltantes)


def construir_payload_comparacao(
    conn, indicadores: list[Indicador], mand_a: Mandato, mand_b: Mandato
) -> PayloadComparacao:
    deltas: list[DeltaIndicador] = []
    for ind in indicadores:
        obs = observacoes_da_serie(conn, ind.id)
        va = valor_no_mandato(obs, ind, mand_a, "fim")
        vb = valor_no_mandato(obs, ind, mand_b, "fim")
        delta = vb - va if va is not None and vb is not None else None
        deltas.append(DeltaIndicador(
            nome=ind.nome, valor_a=va, valor_b=vb, delta=delta,
            unidade=ind.unidade, fonte=ind.fonte,
        ))
    return PayloadComparacao(mandato_a=mand_a.nome, mandato_b=mand_b.nome, deltas=deltas)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_payload.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/payload.py tests/test_payload.py
git commit -m "feat: payload builders for year and mandate comparison"
```

---

### Task 11: Factuality guard (`app/guard.py`)

**Files:**
- Create: `app/guard.py`, `tests/test_guard.py`

**Interfaces:**
- Consumes: `PayloadAno`, `PayloadComparacao`, `ResumoFactual`.
- Produces:
  - `class GuardError(ValueError)`
  - `numeros_permitidos(payload: PayloadAno | PayloadComparacao) -> set[float]`
  - `extrair_numeros(texto: str) -> list[float]`
  - `verificar(resumo: ResumoFactual, payload, tolerancia: float = 0.05) -> None` (raises `GuardError` on hallucinated number)

- [ ] **Step 1: Write the failing test**

`tests/test_guard.py`:
```python
import pytest

from app.guard import GuardError, extrair_numeros, verificar
from app.models import Afirmacao, PayloadAno, ResumoFactual, ValorIndicador


def _payload() -> PayloadAno:
    return PayloadAno(
        ano=2024,
        indicadores=[ValorIndicador(nome="Selic", valor=11.75, unidade="% a.a.",
                                    fonte="BCB", data_ref=None)],
        faltantes=[],
    )


def test_extrai_numeros_pt_br():
    assert 11.75 in extrair_numeros("A Selic foi de 11,75% ao ano.")
    assert 11.75 in extrair_numeros("A Selic foi de 11.75%.")


def test_resumo_fiel_passa():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic encerrou 2024 em 11,75% (fonte: BCB)."},
        afirmacoes=[Afirmacao(texto="Selic 11,75%", valor_citado=11.75, fonte="BCB")],
    )
    verificar(resumo, _payload())  # não levanta


def test_numero_alucinado_no_texto_falha():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "A Selic encerrou 2024 em 9,00%."},
        afirmacoes=[],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())


def test_valor_citado_fora_do_payload_falha():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"macro": "texto sem números"},
        afirmacoes=[Afirmacao(texto="Selic", valor_citado=9.0, fonte="BCB")],
    )
    with pytest.raises(GuardError):
        verificar(resumo, _payload())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_guard.py -v`
Expected: FAIL (`ModuleNotFoundError: app.guard`).

- [ ] **Step 3: Implement `app/guard.py`**

```python
"""Deterministic factuality guard: every cited number must exist in the payload."""
from __future__ import annotations

import re

from app.models import PayloadAno, PayloadComparacao, ResumoFactual

_NUM = re.compile(r"-?\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d+)?")


class GuardError(ValueError):
    pass


def extrair_numeros(texto: str) -> list[float]:
    out: list[float] = []
    for m in _NUM.findall(texto):
        limpo = m.replace(" ", "")
        if "," in limpo:  # pt-BR decimal comma; dots are thousands
            limpo = limpo.replace(".", "").replace(",", ".")
        try:
            out.append(float(limpo))
        except ValueError:
            continue
    return out


def numeros_permitidos(payload: PayloadAno | PayloadComparacao) -> set[float]:
    nums: set[float] = set()
    if isinstance(payload, PayloadAno):
        nums.add(float(payload.ano))
        for vi in payload.indicadores:
            if vi.valor is not None:
                nums.add(vi.valor)
    else:
        for d in payload.deltas:
            for v in (d.valor_a, d.valor_b, d.delta):
                if v is not None:
                    nums.add(v)
    return nums


def _proximo(alvo: float, permitidos: set[float], tol: float) -> bool:
    return any(abs(alvo - p) <= tol for p in permitidos)


def verificar(
    resumo: ResumoFactual, payload: PayloadAno | PayloadComparacao, tolerancia: float = 0.05
) -> None:
    permitidos = numeros_permitidos(payload)
    for af in resumo.afirmacoes:
        if not _proximo(af.valor_citado, permitidos, tolerancia):
            raise GuardError(f"valor_citado {af.valor_citado} não existe no payload")
    for texto in resumo.paragrafos_por_eixo.values():
        for n in extrair_numeros(texto):
            if not _proximo(n, permitidos, tolerancia):
                raise GuardError(f"número {n} no texto não existe no payload")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_guard.py -v`
Expected: PASS (all 4).

- [ ] **Step 5: Commit**

```bash
git add app/guard.py tests/test_guard.py
git commit -m "feat: deterministic factuality guard"
```

---

### Task 12: LLM client interface + Claude Code adapter (`app/llm.py`)

**Files:**
- Create: `app/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: nothing (stdlib + claude-agent-sdk).
- Produces:
  - `class LLMClient(Protocol)` with `def gerar(self, prompt: str) -> str` (returns raw model text, expected to be JSON)
  - `class ClaudeCodeClient` implementing it via `claude -p --output-format json` subprocess (uses the Claude Code subscription)
  - `extrair_texto_json(stdout: str) -> str` (pulls the assistant text out of `claude -p` json envelope)

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:
```python
import json

from app.llm import ClaudeCodeClient, extrair_texto_json


def test_extrai_texto_do_envelope_claude():
    envelope = json.dumps({"type": "result", "result": '{"ok": true}'})
    assert extrair_texto_json(envelope) == '{"ok": true}'


def test_claude_code_client_usa_subprocess(monkeypatch):
    captured = {}

    class _CP:
        stdout = json.dumps({"type": "result", "result": '{"x": 1}'})
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _CP()

    monkeypatch.setattr("app.llm.subprocess.run", fake_run)
    out = ClaudeCodeClient().gerar("olá")
    assert out == '{"x": 1}'
    assert "claude" in captured["cmd"][0]
    assert "-p" in captured["cmd"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_llm.py -v`
Expected: FAIL (`ModuleNotFoundError: app.llm`).

- [ ] **Step 3: Implement `app/llm.py`**

```python
"""LLM access behind a swappable interface, default = Claude Code subscription."""
from __future__ import annotations

import json
import subprocess
from typing import Protocol


class LLMClient(Protocol):
    def gerar(self, prompt: str) -> str: ...


def extrair_texto_json(stdout: str) -> str:
    """Pull the assistant result text out of `claude -p --output-format json`."""
    envelope = json.loads(stdout)
    if isinstance(envelope, dict) and "result" in envelope:
        return envelope["result"]
    return stdout


class ClaudeCodeClient:
    """Calls the local Claude Code CLI headless; auth = the user's subscription."""

    def __init__(self, modelo: str | None = None) -> None:
        self.modelo = modelo

    def gerar(self, prompt: str) -> str:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if self.modelo:
            cmd += ["--model", self.modelo]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if cp.returncode != 0:
            raise RuntimeError(f"claude -p falhou: {cp.stdout}")
        return extrair_texto_json(cp.stdout)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_llm.py -v && uv run pyright`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/llm.py tests/test_llm.py
git commit -m "feat: LLMClient interface + Claude Code subscription adapter"
```

---

### Task 13: Summary generation with validate + retry (`app/resumo.py`)

**Files:**
- Create: `app/resumo.py`, `tests/test_resumo.py`

**Interfaces:**
- Consumes: `LLMClient`, `PayloadAno`/`PayloadComparacao`, `ResumoFactual`, `guard.verificar`.
- Produces:
  - `montar_prompt(payload: PayloadAno | PayloadComparacao) -> str`
  - `gerar_resumo(client: LLMClient, payload, tentativas: int = 3) -> ResumoFactual` (parse → Pydantic validate → guard; retries on failure)

- [ ] **Step 1: Write the failing test**

`tests/test_resumo.py`:
```python
import json

import pytest

from app.models import PayloadAno, ValorIndicador
from app.resumo import gerar_resumo, montar_prompt


def _payload() -> PayloadAno:
    return PayloadAno(
        ano=2024,
        indicadores=[ValorIndicador(nome="Selic", valor=11.75, unidade="% a.a.",
                                    fonte="BCB", data_ref=None)],
        faltantes=[],
    )


class _ClientFixo:
    def __init__(self, resposta: str):
        self.resposta = resposta
        self.chamadas = 0

    def gerar(self, prompt: str) -> str:
        self.chamadas += 1
        return self.resposta


def test_prompt_inclui_valores_e_regra():
    p = montar_prompt(_payload())
    assert "11.75" in p or "11,75" in p
    assert "Selic" in p


def test_gerar_resumo_valido():
    resposta = json.dumps({
        "paragrafos_por_eixo": {"macro": "A Selic encerrou 2024 em 11,75% (fonte: BCB)."},
        "afirmacoes": [{"texto": "Selic", "valor_citado": 11.75, "fonte": "BCB"}],
    })
    r = gerar_resumo(_ClientFixo(resposta), _payload())
    assert r.afirmacoes[0].valor_citado == 11.75


def test_gerar_resumo_rejeita_alucinacao_e_esgota_tentativas():
    resposta = json.dumps({
        "paragrafos_por_eixo": {"macro": "A Selic foi de 9,00%."},
        "afirmacoes": [],
    })
    client = _ClientFixo(resposta)
    with pytest.raises(ValueError):
        gerar_resumo(client, _payload(), tentativas=2)
    assert client.chamadas == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_resumo.py -v`
Expected: FAIL (`ModuleNotFoundError: app.resumo`).

- [ ] **Step 3: Implement `app/resumo.py`**

```python
"""Generate factual summaries: prompt -> LLM -> validate schema -> factuality guard."""
from __future__ import annotations

import json

from app.guard import GuardError, verificar
from app.llm import LLMClient
from app.models import PayloadAno, PayloadComparacao, ResumoFactual

_REGRAS = (
    "Você redige um resumo FACTUAL e NEUTRO sobre indicadores de um governo. "
    "REGRAS: (1) use SOMENTE os números fornecidos no payload; NUNCA invente ou calcule "
    "valores. (2) Cite a fonte de cada afirmação. (3) Sem juízo de valor, sem dizer qual "
    "governo foi melhor, sem causação especulativa. (4) Para itens em 'faltantes', diga "
    "'sem dado disponível'. Responda APENAS com JSON no schema: "
    '{"paragrafos_por_eixo": {"macro": str, "fiscal": str, "social": str}, '
    '"afirmacoes": [{"texto": str, "valor_citado": number, "fonte": str}]}.'
)


def montar_prompt(payload: PayloadAno | PayloadComparacao) -> str:
    return f"{_REGRAS}\n\nPAYLOAD:\n{payload.model_dump_json(indent=2)}"


def gerar_resumo(
    client: LLMClient, payload: PayloadAno | PayloadComparacao, tentativas: int = 3
) -> ResumoFactual:
    prompt = montar_prompt(payload)
    erro: Exception | None = None
    for _ in range(tentativas):
        bruto = client.gerar(prompt)
        try:
            resumo = ResumoFactual.model_validate(json.loads(bruto))
            verificar(resumo, payload)
            return resumo
        except (json.JSONDecodeError, ValueError, GuardError) as exc:
            erro = exc
    raise ValueError(f"não foi possível gerar resumo válido em {tentativas} tentativas: {erro}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_resumo.py -v`
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```bash
git add app/resumo.py tests/test_resumo.py
git commit -m "feat: summary generation with schema validation + guard retry"
```

---

### Task 14: LLM-as-judge (`app/judge.py`)

**Files:**
- Create: `app/judge.py`, `tests/test_judge.py`

**Interfaces:**
- Consumes: `LLMClient`, `ResumoFactual`, payloads.
- Produces:
  - `class Veredito(BaseModel)` with `ancorado: bool`, `neutro: bool`, `numeros_fora_do_payload: list[float]`, `observacoes: str`
  - `julgar(client: LLMClient, payload, resumo: ResumoFactual) -> Veredito`

- [ ] **Step 1: Write the failing test**

`tests/test_judge.py`:
```python
import json

from app.judge import Veredito, julgar
from app.models import Afirmacao, PayloadAno, ResumoFactual, ValorIndicador


class _ClientFixo:
    def __init__(self, resposta: str):
        self.resposta = resposta

    def gerar(self, prompt: str) -> str:
        return self.resposta


def _payload() -> PayloadAno:
    return PayloadAno(ano=2024, indicadores=[ValorIndicador(
        nome="Selic", valor=11.75, unidade="% a.a.", fonte="BCB", data_ref=None)], faltantes=[])


def _resumo() -> ResumoFactual:
    return ResumoFactual(
        paragrafos_por_eixo={"macro": "Selic 11,75% (fonte: BCB)."},
        afirmacoes=[Afirmacao(texto="Selic", valor_citado=11.75, fonte="BCB")],
    )


def test_julgar_retorna_veredito():
    resposta = json.dumps({
        "ancorado": True, "neutro": True, "numeros_fora_do_payload": [], "observacoes": "ok"
    })
    v = julgar(_ClientFixo(resposta), _payload(), _resumo())
    assert isinstance(v, Veredito)
    assert v.ancorado is True
    assert v.numeros_fora_do_payload == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_judge.py -v`
Expected: FAIL (`ModuleNotFoundError: app.judge`).

- [ ] **Step 3: Implement `app/judge.py`**

```python
"""LLM-as-judge: a subagent checks grounding + neutrality of a generated summary."""
from __future__ import annotations

import json

from pydantic import BaseModel

from app.llm import LLMClient
from app.models import PayloadAno, PayloadComparacao, ResumoFactual

_INSTRUCAO = (
    "Você é um JUIZ rigoroso. Dado um PAYLOAD de dados e um RESUMO, verifique: "
    "(a) toda afirmação do resumo está ancorada em valores do payload; "
    "(b) o tom é neutro (sem juízo de valor, sem causação especulativa); "
    "(c) liste números citados que NÃO existem no payload. Responda APENAS JSON: "
    '{"ancorado": bool, "neutro": bool, "numeros_fora_do_payload": [number], "observacoes": str}.'
)


class Veredito(BaseModel):
    ancorado: bool
    neutro: bool
    numeros_fora_do_payload: list[float]
    observacoes: str


def julgar(
    client: LLMClient, payload: PayloadAno | PayloadComparacao, resumo: ResumoFactual
) -> Veredito:
    prompt = (
        f"{_INSTRUCAO}\n\nPAYLOAD:\n{payload.model_dump_json(indent=2)}"
        f"\n\nRESUMO:\n{resumo.model_dump_json(indent=2)}"
    )
    bruto = client.gerar(prompt)
    return Veredito.model_validate(json.loads(bruto))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_judge.py -v && uv run pyright`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/judge.py tests/test_judge.py
git commit -m "feat: LLM-as-judge for grounding + neutrality verification"
```

---

### Task 15: Streamlit UI (`app/ui.py`) + full-suite verification

**Files:**
- Create: `app/ui.py`, `tests/test_ui_smoke.py`

**Interfaces:**
- Consumes: config loader, db, payload builders, resumo, plotly.
- Produces:
  - `serie_para_df(obs: list[Observacao]) -> pandas.DataFrame` (helper, unit-testable without Streamlit)
  - `grafico_serie(obs, titulo, unidade, fonte) -> plotly.graph_objects.Figure`
  - `main() -> None` (Streamlit page; not unit-tested, exercised by smoke run)

- [ ] **Step 1: Write the failing test** (test the pure helpers, not Streamlit itself)

`tests/test_ui_smoke.py`:
```python
import datetime

from app.models import Observacao
from app.ui import grafico_serie, serie_para_df


def _obs():
    return [
        Observacao(serie_id="s", data=datetime.date(2024, 1, 1), valor=10.0),
        Observacao(serie_id="s", data=datetime.date(2024, 2, 1), valor=11.0),
    ]


def test_serie_para_df_tem_colunas():
    df = serie_para_df(_obs())
    assert list(df.columns) == ["data", "valor"]
    assert len(df) == 2


def test_grafico_serie_tem_titulo_com_fonte_e_unidade():
    fig = grafico_serie(_obs(), titulo="Selic", unidade="% a.a.", fonte="BCB")
    titulo = fig.layout.title.text
    assert "Selic" in titulo
    assert "BCB" in titulo
    assert "% a.a." in titulo
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: app.ui`).

- [ ] **Step 3: Implement `app/ui.py`**

```python
"""Streamlit UI: three tabs (por ano / por mandato / comparação)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from app.models import Observacao


def serie_para_df(obs: list[Observacao]) -> pd.DataFrame:
    return pd.DataFrame({"data": [o.data for o in obs], "valor": [o.valor for o in obs]})


def grafico_serie(obs: list[Observacao], titulo: str, unidade: str, fonte: str) -> go.Figure:
    df = serie_para_df(obs)
    fig = go.Figure(go.Scatter(x=df["data"], y=df["valor"], mode="lines+markers"))
    fig.update_layout(title=f"{titulo} ({unidade}) — fonte: {fonte}")
    return fig


def main() -> None:  # pragma: no cover - exercised by the manual smoke run
    import streamlit as st

    from app.config_loader import carregar_indicadores, carregar_mandatos
    from app.db import conectar, criar_schema, observacoes_da_serie
    from app.llm import ClaudeCodeClient
    from app.payload import construir_payload_ano, construir_payload_comparacao
    from app.resumo import gerar_resumo

    st.set_page_config(page_title="finance_politics", layout="wide")
    indicadores = carregar_indicadores()
    mandatos = carregar_mandatos()
    conn = conectar()
    criar_schema(conn)

    aba_ano, aba_mandato, aba_comp = st.tabs(["Por ano", "Por mandato", "Comparação"])

    with aba_ano:
        ano = st.number_input("Ano", min_value=2003, max_value=2026, value=2024, step=1)
        for ind in indicadores:
            obs = observacoes_da_serie(conn, ind.id)
            if obs:
                st.plotly_chart(grafico_serie(obs, ind.nome, ind.unidade, ind.fonte),
                                use_container_width=True)
        payload = construir_payload_ano(conn, indicadores, int(ano))
        if st.button("Gerar resumo do ano"):
            _mostrar_resumo(st, ClaudeCodeClient(), payload)

    with aba_mandato:
        nome = st.selectbox("Mandato", [m.nome for m in mandatos])
        st.write(f"Mandato selecionado: {nome}")

    with aba_comp:
        nomes = [m.nome for m in mandatos]
        col_a, col_b = st.columns(2)
        a = col_a.selectbox("Mandato A", nomes, index=0)
        b = col_b.selectbox("Mandato B", nomes, index=len(nomes) - 1)
        ma = next(m for m in mandatos if m.nome == a)
        mb = next(m for m in mandatos if m.nome == b)
        payload_c = construir_payload_comparacao(conn, indicadores, ma, mb)
        st.dataframe(pd.DataFrame([d.model_dump() for d in payload_c.deltas]))
        if st.button("Gerar resumo comparativo"):
            _mostrar_resumo(st, ClaudeCodeClient(), payload_c)


def _mostrar_resumo(st, client, payload) -> None:  # pragma: no cover
    from app.resumo import gerar_resumo

    try:
        resumo = gerar_resumo(client, payload)
        st.info("Resumo gerado por IA a partir dos dados acima:")
        for eixo, txt in resumo.paragrafos_por_eixo.items():
            st.markdown(f"**{eixo}** — {txt}")
    except ValueError as exc:
        st.error(f"Não foi possível gerar o resumo: {exc}")
```

- [ ] **Step 4: Run the full suite + lint + typecheck**

Run: `uv run pytest -q && uv run ruff check . && uv run pyright`
Expected: ALL tests PASS, lint clean, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: streamlit UI with year/mandate/comparison tabs"
```

- [ ] **Step 6: Manual E2E smoke (outside the loop — needs network + subscription)**

Run:
```bash
uv run python -m app.ingest          # confirm SQLite populated; verify codes if a source 404s
uv run streamlit run app/ui.py       # open browser; check charts render with source+unit
```
Expected: ≥8 series ingested; "Por ano" tab shows charts; "Gerar resumo do ano" produces a coherent, factually-correct summary. Record any indicator whose `codigo_fonte` needs fixing in `config/indicadores.yaml`.

---

## Self-Review

**1. Spec coverage:**
- Ingestion (BCB/SIDRA/IPEA/Tesouro, raw cache, retry, idempotency) → Tasks 5–8. ✓
- SQLite long-format schema → Task 4. ✓
- Deterministic calculation (year/mandate, métodos de agregação) → Task 9. ✓
- Payload builders (ano + comparação) → Task 10. ✓
- AI layer via `LLMClient`/Claude Code subscription → Tasks 12–13. ✓
- Factuality guard (deterministic) → Task 11. ✓
- LLM-as-judge → Task 14. ✓
- Streamlit UI (3 tabs, source+unit per chart, separated AI box, error handling) → Task 15. ✓
- Config registry (indicadores + mandatos) → Task 3. ✓
- Acceptance criteria (pytest green, guard rejects hallucination, LLMClient mocked, Pydantic validation, ruff+pyright, E2E smoke) → covered across tasks + Task 15 steps 4 & 6. ✓

**2. Placeholder scan:** No "TBD/TODO" in code steps; config `codigo_fonte` values are concrete with an explicit verify-against-portal step (data, not a code placeholder). ✓

**3. Type consistency:** `Observacao`, `Indicador`, `PayloadAno/Comparacao`, `ResumoFactual`, `Afirmacao` signatures match across tasks; `gerar`/`verificar`/`construir_payload_*` names consistent between definition and use. ✓

**Note on Ralph workflow:** this detailed plan is the source of truth for tasks; `IMPLEMENTATION_PLAN.md` is the lightweight progress tracker. If running headless via `./loop.sh build`, point the build prompt at this file.
