# Camada Ministerial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar a camada ministerial — ministros (YAML) e suas medidas (SQLite, com workflow rascunho→aprovação + assistente de rascunho por IA), com payload e resumo factual por governo.

**Architecture:** Ministros vêm de `config/ministros.yaml` (factual, estático). Medidas vivem no SQLite com `status` (rascunho|aprovada) e `origem` (curada|ia); a IA só **rascunha** (sempre com fonte) e nada entra em resumo até ser aprovado. Payload e resumo reutilizam o guard, o juiz e a persistência de resumos já existentes.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, SQLite (`sqlite3`), pytest, Streamlit.

## Global Constraints

- Python `>=3.12`; pyright modo `standard`; ruff `line-length = 100`.
- **O LLM nunca apresenta fato não verificado:** rascunho exige `fonte_url`; rascunho nunca entra em payload/resumo; resumo usa SOMENTE medidas `status="aprovada"`.
- **Zero rede nos testes:** `LLMClient` e I/O sempre mockados/fixtures; conexões de teste usam `conectar(":memory:")`.
- Não adicionar dependências novas (tudo é stdlib + libs já presentes).
- Commits pequenos, um por tarefa; TDD (teste antes).

## Dependência de ordem

> Este plano **assume que o plano `2026-06-21-persistencia-resumos.md` já foi implementado**.
> Ele depende de: `descrever_payload` existir em `app/payload.py`; `app/db.py` ter
> `salvar_resumo`/`buscar_resumo_cache`/`historico_resumos`; `app/ui.py` ter
> `_mostrar_resumo(st, conn, client, payload)`. A Task 6 estende `descrever_payload` e a Task 7
> reusa `_mostrar_resumo`.

---

### Task 1: DTOs `Ministro`/`Medida` + loader de ministros

**Files:**
- Modify: `app/models.py`
- Create: `app/ministros.py`
- Create: `config/ministros.yaml`
- Test: `tests/test_ministros.py`

**Interfaces:**
- Produces:
  - `Ministro(BaseModel)`: `governo: str, pasta: str, nome: str, inicio: datetime.date, fim: datetime.date | None, fonte: str`.
  - `Medida(BaseModel)`: `id: int | None = None, governo: str, pasta: str, ministro: str, titulo: str, descricao: str, fonte_url: str, status: str, origem: str, criado_em: str | None = None`.
  - `carregar_ministros(path: str = "config/ministros.yaml", mandatos_path: str = "config/mandatos.yaml") -> list[Ministro]`
  - `ministros_do_governo(ministros: list[Ministro], governo: str) -> list[Ministro]`

- [ ] **Step 1: Write the failing test**

Crie `tests/test_ministros.py`:

```python
import datetime

import pytest

from app.ministros import carregar_ministros, ministros_do_governo


def _escrever(tmp_path, ministros_yaml: str):
    mandatos = tmp_path / "mandatos.yaml"
    mandatos.write_text(
        "- nome: Lula 3\n  inicio: 2023-01-01\n  fim: 2026-12-31\n", encoding="utf-8"
    )
    ministros = tmp_path / "ministros.yaml"
    ministros.write_text(ministros_yaml, encoding="utf-8")
    return str(ministros), str(mandatos)


def test_carregar_ministros_ok(tmp_path):
    mp, mdp = _escrever(
        tmp_path,
        "- governo: Lula 3\n"
        "  ministros:\n"
        "    - pasta: Fazenda\n"
        "      nome: Fernando Haddad\n"
        "      inicio: 2023-01-01\n"
        "      fim: null\n"
        "      fonte: https://exemplo\n",
    )
    ms = carregar_ministros(mp, mdp)
    assert len(ms) == 1
    assert ms[0].nome == "Fernando Haddad"
    assert ms[0].pasta == "Fazenda"
    assert ms[0].fim is None
    assert ms[0].inicio == datetime.date(2023, 1, 1)


def test_carregar_ministros_rejeita_governo_desconhecido(tmp_path):
    mp, mdp = _escrever(
        tmp_path,
        "- governo: Governo Inexistente\n"
        "  ministros:\n"
        "    - pasta: Fazenda\n"
        "      nome: X\n"
        "      inicio: 2023-01-01\n"
        "      fim: null\n"
        "      fonte: https://exemplo\n",
    )
    with pytest.raises(ValueError, match="Governo Inexistente"):
        carregar_ministros(mp, mdp)


def test_ministros_do_governo_filtra():
    from app.models import Ministro

    a = Ministro(governo="Lula 3", pasta="Fazenda", nome="A",
                 inicio=datetime.date(2023, 1, 1), fim=None, fonte="x")
    b = Ministro(governo="Bolsonaro", pasta="Economia", nome="B",
                 inicio=datetime.date(2019, 1, 1), fim=None, fonte="x")
    assert ministros_do_governo([a, b], "Lula 3") == [a]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ministros.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.ministros'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/models.py`, ao final, adicione:

```python
class Ministro(BaseModel):
    governo: str
    pasta: str
    nome: str
    inicio: datetime.date
    fim: datetime.date | None
    fonte: str


class Medida(BaseModel):
    id: int | None = None
    governo: str
    pasta: str
    ministro: str
    titulo: str
    descricao: str
    fonte_url: str
    status: str   # 'rascunho' | 'aprovada'
    origem: str   # 'curada' | 'ia'
    criado_em: str | None = None
```

Crie `app/ministros.py`:

```python
"""Camada ministerial: carrega ministros (YAML) e helpers de governo."""
from __future__ import annotations

import yaml

from app.models import Mandato, Ministro


def carregar_ministros(
    path: str = "config/ministros.yaml",
    mandatos_path: str = "config/mandatos.yaml",
) -> list[Ministro]:
    with open(mandatos_path, encoding="utf-8") as fh:
        mandatos = [Mandato.model_validate(m) for m in yaml.safe_load(fh)]
    nomes_validos = {m.nome for m in mandatos}

    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []

    ministros: list[Ministro] = []
    for bloco in raw:
        governo = bloco["governo"]
        if governo not in nomes_validos:
            raise ValueError(
                f"governo '{governo}' em {path} não existe em {mandatos_path}"
            )
        for item in bloco.get("ministros", []):
            ministros.append(Ministro.model_validate({**item, "governo": governo}))
    return ministros


def ministros_do_governo(
    ministros: list[Ministro], governo: str
) -> list[Ministro]:
    return [m for m in ministros if m.governo == governo]
```

Crie `config/ministros.yaml` (conjunto-semente verificável; expanda à vontade):

```yaml
# Conjunto-semente de ministros por governo. Expanda conforme sua pesquisa.
# 'governo' deve casar com config/mandatos.yaml. 'fim: null' = até o fim do mandato.
- governo: "Lula 1"
  ministros:
    - pasta: "Fazenda"
      nome: "Antonio Palocci"
      inicio: 2003-01-01
      fim: 2006-03-27
      fonte: "https://pt.wikipedia.org/wiki/Antonio_Palocci"
- governo: "Lula 2"
  ministros:
    - pasta: "Fazenda"
      nome: "Guido Mantega"
      inicio: 2006-03-27
      fim: 2010-12-31
      fonte: "https://pt.wikipedia.org/wiki/Guido_Mantega"
- governo: "Dilma 1"
  ministros:
    - pasta: "Fazenda"
      nome: "Guido Mantega"
      inicio: 2011-01-01
      fim: 2014-12-31
      fonte: "https://pt.wikipedia.org/wiki/Guido_Mantega"
- governo: "Dilma/Temer"
  ministros:
    - pasta: "Fazenda"
      nome: "Henrique Meirelles"
      inicio: 2016-05-12
      fim: 2018-12-31
      fonte: "https://pt.wikipedia.org/wiki/Henrique_Meirelles"
- governo: "Bolsonaro"
  ministros:
    - pasta: "Economia"
      nome: "Paulo Guedes"
      inicio: 2019-01-01
      fim: 2022-12-31
      fonte: "https://pt.wikipedia.org/wiki/Paulo_Guedes"
- governo: "Lula 3"
  ministros:
    - pasta: "Fazenda"
      nome: "Fernando Haddad"
      inicio: 2023-01-01
      fim: null
      fonte: "https://pt.wikipedia.org/wiki/Fernando_Haddad"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ministros.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/ministros.py config/ministros.yaml tests/test_ministros.py
git commit -m "feat: DTOs Ministro/Medida + loader de ministros + seed YAML"
```

---

### Task 2: Tabela `medidas` + CRUD (`app/db.py`)

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Medida` de `app/models.py`.
- Produces (em `app/db.py`):
  - `salvar_medida(conn, medida: Medida) -> int` (insere; `criado_em=None` → agora; retorna id)
  - `medidas_do_governo(conn, governo: str, *, apenas_aprovadas: bool = False) -> list[Medida]`
  - `aprovar_medida(conn, medida_id: int) -> None`
  - `editar_medida(conn, medida_id: int, *, titulo: str, descricao: str, fonte_url: str) -> None`
  - `descartar_medida(conn, medida_id: int) -> None`

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_db.py`:

```python
from app.db import (
    aprovar_medida,
    descartar_medida,
    editar_medida,
    medidas_do_governo,
    salvar_medida,
)
from app.models import Medida


def _medida(status="rascunho", origem="curada", titulo="t") -> Medida:
    return Medida(
        governo="Lula 3", pasta="Fazenda", ministro="Haddad",
        titulo=titulo, descricao="d", fonte_url="https://x",
        status=status, origem=origem,
    )


def test_salvar_e_listar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida())
    assert isinstance(mid, int)
    todas = medidas_do_governo(conn, "Lula 3")
    assert len(todas) == 1
    assert todas[0].titulo == "t"
    assert todas[0].id == mid


def test_filtro_apenas_aprovadas():
    conn = conectar(":memory:")
    criar_schema(conn)
    salvar_medida(conn, _medida(status="rascunho", titulo="rasc"))
    salvar_medida(conn, _medida(status="aprovada", titulo="aprov"))
    aprovadas = medidas_do_governo(conn, "Lula 3", apenas_aprovadas=True)
    assert [m.titulo for m in aprovadas] == ["aprov"]


def test_aprovar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida(status="rascunho"))
    aprovar_medida(conn, mid)
    assert medidas_do_governo(conn, "Lula 3", apenas_aprovadas=True)[0].id == mid


def test_editar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida())
    editar_medida(conn, mid, titulo="novo", descricao="nd", fonte_url="https://y")
    m = medidas_do_governo(conn, "Lula 3")[0]
    assert m.titulo == "novo" and m.fonte_url == "https://y"


def test_descartar_medida():
    conn = conectar(":memory:")
    criar_schema(conn)
    mid = salvar_medida(conn, _medida())
    descartar_medida(conn, mid)
    assert medidas_do_governo(conn, "Lula 3") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -k "medida" -v`
Expected: FAIL com `ImportError: cannot import name 'salvar_medida'`.

- [ ] **Step 3: Write minimal implementation**

Adicione a tabela ao `_SCHEMA` em `app/db.py` (antes do `"""` final):

```sql
CREATE TABLE IF NOT EXISTS medidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    governo TEXT, pasta TEXT, ministro TEXT, titulo TEXT, descricao TEXT,
    fonte_url TEXT, status TEXT, origem TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_medidas_governo ON medidas (governo, status);
```

Adicione ao final de `app/db.py` (`import json`/`datetime` já estarão presentes após o plano de persistência; garanta que existam):

```python
_COLS_MEDIDA = (
    "id, governo, pasta, ministro, titulo, descricao, fonte_url, status, origem, criado_em"
)


def _medida_de_row(row: tuple) -> "Medida":
    from app.models import Medida

    return Medida(
        id=row[0], governo=row[1], pasta=row[2], ministro=row[3], titulo=row[4],
        descricao=row[5], fonte_url=row[6], status=row[7], origem=row[8], criado_em=row[9],
    )


def salvar_medida(conn: sqlite3.Connection, medida) -> int:
    quando = medida.criado_em or datetime.datetime.now().isoformat()
    cur = conn.execute(
        """INSERT INTO medidas (governo, pasta, ministro, titulo, descricao,
           fonte_url, status, origem, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            medida.governo, medida.pasta, medida.ministro, medida.titulo,
            medida.descricao, medida.fonte_url, medida.status, medida.origem, quando,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def medidas_do_governo(
    conn: sqlite3.Connection, governo: str, *, apenas_aprovadas: bool = False
) -> "list[Medida]":
    sql = f"SELECT {_COLS_MEDIDA} FROM medidas WHERE governo = ?"
    params: tuple = (governo,)
    if apenas_aprovadas:
        sql += " AND status = 'aprovada'"
    sql += " ORDER BY pasta, id"
    return [_medida_de_row(r) for r in conn.execute(sql, params).fetchall()]


def aprovar_medida(conn: sqlite3.Connection, medida_id: int) -> None:
    conn.execute("UPDATE medidas SET status = 'aprovada' WHERE id = ?", (medida_id,))
    conn.commit()


def editar_medida(
    conn: sqlite3.Connection, medida_id: int, *, titulo: str, descricao: str, fonte_url: str
) -> None:
    conn.execute(
        "UPDATE medidas SET titulo = ?, descricao = ?, fonte_url = ? WHERE id = ?",
        (titulo, descricao, fonte_url, medida_id),
    )
    conn.commit()


def descartar_medida(conn: sqlite3.Connection, medida_id: int) -> None:
    conn.execute("DELETE FROM medidas WHERE id = ?", (medida_id,))
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -k "medida" -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: tabela medidas + CRUD (salvar/listar/aprovar/editar/descartar)"
```

---

### Task 3: Assistente de rascunho por IA (`app/medidas_ia.py`)

**Files:**
- Create: `app/medidas_ia.py`
- Test: `tests/test_medidas_ia.py`

**Interfaces:**
- Consumes: `LLMClient` de `app/llm.py`; `Ministro`, `Medida` de `app/models.py`.
- Produces: `rascunhar_medidas(client: LLMClient, ministro: Ministro, n: int = 3) -> list[Medida]`
  (cada item: `status="rascunho"`, `origem="ia"`; itens sem `fonte_url` são descartados;
  NÃO persiste — só retorna).

- [ ] **Step 1: Write the failing test**

Crie `tests/test_medidas_ia.py`:

```python
import datetime
import json

from app.medidas_ia import rascunhar_medidas
from app.models import Ministro


class _FakeClient:
    def __init__(self, resposta: str):
        self._r = resposta

    def gerar(self, prompt: str) -> str:
        return self._r


def _ministro() -> Ministro:
    return Ministro(governo="Lula 3", pasta="Fazenda", nome="Fernando Haddad",
                    inicio=datetime.date(2023, 1, 1), fim=None, fonte="x")


def test_rascunhar_medidas_monta_medidas_rascunho():
    resp = json.dumps({"medidas": [
        {"titulo": "Arcabouço fiscal", "descricao": "Nova regra fiscal",
         "fonte_url": "https://exemplo/lei"},
    ]})
    out = rascunhar_medidas(_FakeClient(resp), _ministro())
    assert len(out) == 1
    m = out[0]
    assert m.status == "rascunho" and m.origem == "ia"
    assert m.governo == "Lula 3" and m.pasta == "Fazenda"
    assert m.ministro == "Fernando Haddad"
    assert m.titulo == "Arcabouço fiscal"


def test_rascunhar_descarta_sem_fonte():
    resp = json.dumps({"medidas": [
        {"titulo": "Sem fonte", "descricao": "x", "fonte_url": ""},
        {"titulo": "Com fonte", "descricao": "y", "fonte_url": "https://ok"},
    ]})
    out = rascunhar_medidas(_FakeClient(resp), _ministro())
    assert [m.titulo for m in out] == ["Com fonte"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_medidas_ia.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.medidas_ia'`.

- [ ] **Step 3: Write minimal implementation**

Crie `app/medidas_ia.py`:

```python
"""Assistente de IA: rascunha medidas de um ministro (sempre com fonte)."""
from __future__ import annotations

import json

from app.llm import LLMClient
from app.models import Medida, Ministro

_REGRAS = (
    "Liste até {n} principais medidas/políticas do ministro abaixo. Para CADA medida "
    "forneça: titulo (curto), descricao (factual e neutra) e fonte_url (link verificável). "
    "NUNCA invente fontes; se não houver fonte confiável, OMITA a medida. "
    'Responda APENAS JSON no schema: {{"medidas": [{{"titulo": str, "descricao": str, '
    '"fonte_url": str}}]}}.'
)


def rascunhar_medidas(client: LLMClient, ministro: Ministro, n: int = 3) -> list[Medida]:
    prompt = (
        _REGRAS.format(n=n)
        + f"\n\nMINISTRO: {ministro.nome} — pasta {ministro.pasta} "
        + f"(governo {ministro.governo})."
    )
    dados = json.loads(client.gerar(prompt))
    medidas: list[Medida] = []
    for item in dados.get("medidas", []):
        fonte = (item.get("fonte_url") or "").strip()
        if not fonte:
            continue
        medidas.append(
            Medida(
                governo=ministro.governo,
                pasta=ministro.pasta,
                ministro=ministro.nome,
                titulo=item["titulo"],
                descricao=item["descricao"],
                fonte_url=fonte,
                status="rascunho",
                origem="ia",
            )
        )
    return medidas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_medidas_ia.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add app/medidas_ia.py tests/test_medidas_ia.py
git commit -m "feat: assistente de IA rascunha medidas (fonte obrigatória)"
```

---

### Task 4: Payload ministerial (`app/models.py` + `app/payload.py`)

**Files:**
- Modify: `app/models.py`
- Modify: `app/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Consumes: `medidas_do_governo` de `app/db.py`; `ministros_do_governo` de `app/ministros.py`;
  `Mandato` de `app/models.py`.
- Produces:
  - `MedidaResumo(BaseModel)`: `pasta, ministro, titulo, descricao, fonte_url` (todos `str`).
  - `PayloadMinisterialGoverno(BaseModel)`: `governo: str, ano_inicio: int, ano_fim: int, ministros: list[str], medidas: list[MedidaResumo]`.
  - `construir_payload_ministerial(conn, ministros: list[Ministro], mandato: Mandato) -> PayloadMinisterialGoverno`
    (usa SOMENTE medidas aprovadas).

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_payload.py`:

```python
import datetime as _dt

from app.db import salvar_medida
from app.models import Mandato, Medida, Ministro, PayloadMinisterialGoverno
from app.payload import construir_payload_ministerial


def _mandato_lula3() -> Mandato:
    return Mandato(nome="Lula 3", inicio=_dt.date(2023, 1, 1), fim=_dt.date(2026, 12, 31))


def _ministro_haddad() -> Ministro:
    return Ministro(governo="Lula 3", pasta="Fazenda", nome="Haddad",
                    inicio=_dt.date(2023, 1, 1), fim=None, fonte="x")


def test_payload_ministerial_so_aprovadas():
    conn = conectar(":memory:")
    criar_schema(conn)
    salvar_medida(conn, Medida(governo="Lula 3", pasta="Fazenda", ministro="Haddad",
                               titulo="aprov", descricao="d", fonte_url="https://a",
                               status="aprovada", origem="curada"))
    salvar_medida(conn, Medida(governo="Lula 3", pasta="Fazenda", ministro="Haddad",
                               titulo="rasc", descricao="d", fonte_url="https://b",
                               status="rascunho", origem="ia"))
    payload = construir_payload_ministerial(conn, [_ministro_haddad()], _mandato_lula3())
    assert isinstance(payload, PayloadMinisterialGoverno)
    assert payload.governo == "Lula 3"
    assert payload.ano_inicio == 2023 and payload.ano_fim == 2026
    assert payload.ministros == ["Fazenda — Haddad"]
    assert [m.titulo for m in payload.medidas] == ["aprov"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payload.py -k "ministerial" -v`
Expected: FAIL com `ImportError: cannot import name 'PayloadMinisterialGoverno'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/models.py`, ao final:

```python
class MedidaResumo(BaseModel):
    pasta: str
    ministro: str
    titulo: str
    descricao: str
    fonte_url: str


class PayloadMinisterialGoverno(BaseModel):
    governo: str
    ano_inicio: int
    ano_fim: int
    ministros: list[str]
    medidas: list[MedidaResumo]
```

Em `app/payload.py`, garanta os imports e adicione ao final:

```python
def construir_payload_ministerial(conn, ministros, mandato):
    from app.db import medidas_do_governo
    from app.ministros import ministros_do_governo
    from app.models import MedidaResumo, PayloadMinisterialGoverno

    do_gov = ministros_do_governo(ministros, mandato.nome)
    aprovadas = medidas_do_governo(conn, mandato.nome, apenas_aprovadas=True)
    return PayloadMinisterialGoverno(
        governo=mandato.nome,
        ano_inicio=mandato.inicio.year,
        ano_fim=mandato.fim.year,
        ministros=[f"{m.pasta} — {m.nome}" for m in do_gov],
        medidas=[
            MedidaResumo(
                pasta=m.pasta, ministro=m.ministro, titulo=m.titulo,
                descricao=m.descricao, fonte_url=m.fonte_url,
            )
            for m in aprovadas
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payload.py -k "ministerial" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/payload.py tests/test_payload.py
git commit -m "feat: PayloadMinisterialGoverno + builder (só medidas aprovadas)"
```

---

### Task 5: Guard + resumo aceitam payload ministerial

**Files:**
- Modify: `app/guard.py`
- Modify: `app/resumo.py`
- Test: `tests/test_guard.py`, `tests/test_resumo.py`

**Interfaces:**
- Consumes: `PayloadMinisterialGoverno` de `app/models.py`.
- Produces:
  - `guard.numeros_permitidos` e `guard.verificar` aceitam `PayloadMinisterialGoverno`
    (números permitidos = `{ano_inicio, ano_fim}`).
  - `resumo.gerar_resumo(client, payload, tentativas=3, regras=_REGRAS)` ganha o parâmetro
    `regras`; constante `_REGRAS_MINISTERIAL` exportada.

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_guard.py`:

```python
from app.models import MedidaResumo, PayloadMinisterialGoverno, ResumoFactual
from app.guard import GuardError, verificar


def _payload_min() -> PayloadMinisterialGoverno:
    return PayloadMinisterialGoverno(
        governo="Lula 3", ano_inicio=2023, ano_fim=2026,
        ministros=["Fazenda — Haddad"],
        medidas=[MedidaResumo(pasta="Fazenda", ministro="Haddad",
                              titulo="t", descricao="d", fonte_url="https://x")],
    )


def test_guard_ministerial_aceita_texto_sem_numeros():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"Fazenda": "O ministro conduziu a política fiscal."},
        afirmacoes=[],
    )
    verificar(resumo, _payload_min())  # não levanta


def test_guard_ministerial_rejeita_estatistica_inventada():
    resumo = ResumoFactual(
        paragrafos_por_eixo={"Fazenda": "Reduziu a inflação em 3,5%."},
        afirmacoes=[],
    )
    try:
        verificar(resumo, _payload_min())
        raise AssertionError("deveria ter levantado GuardError")
    except GuardError:
        pass
```

Adicione ao final de `tests/test_resumo.py`:

```python
from app.resumo import _REGRAS_MINISTERIAL, montar_prompt
from app.models import MedidaResumo, PayloadMinisterialGoverno


def test_montar_prompt_aceita_regras_ministeriais():
    p = PayloadMinisterialGoverno(governo="Lula 3", ano_inicio=2023, ano_fim=2026,
                                  ministros=[], medidas=[])
    prompt = montar_prompt(p, _REGRAS_MINISTERIAL)
    assert "ministro" in prompt.lower()
    assert "Lula 3" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_guard.py -k ministerial tests/test_resumo.py -k ministeriais -v`
Expected: FAIL (`PayloadMinisterialGoverno` não tratado no guard / `_REGRAS_MINISTERIAL` inexistente).

- [ ] **Step 3: Write minimal implementation**

Em `app/guard.py`:
- Atualize o import: `from app.models import (PayloadAno, PayloadComparacao, PayloadMandato, PayloadMinisterialGoverno, ResumoFactual)`.
- Em `numeros_permitidos`, ANTES do `else` final, trate o caso ministerial. Substitua o início da cadeia para incluir:

```python
    if isinstance(payload, PayloadMinisterialGoverno):
        nums.add(float(payload.ano_inicio))
        nums.add(float(payload.ano_fim))
        return nums
    if isinstance(payload, PayloadAno):
        ...  # (mantém o corpo existente)
```

- Atualize as anotações de tipo de `numeros_permitidos` e `verificar` para incluir
  `| PayloadMinisterialGoverno`.

Em `app/resumo.py`:
- Adicione a constante:

```python
_REGRAS_MINISTERIAL = (
    "Você redige um resumo FACTUAL e NEUTRO sobre os ministros de um governo e suas "
    "medidas. REGRAS: (1) use SOMENTE as medidas fornecidas no payload; NUNCA invente "
    "medidas, números ou fontes. (2) Cite a fonte (fonte_url) de cada afirmação. (3) Sem "
    "juízo de valor, sem dizer se foi bom ou ruim, sem causação especulativa. (4) Emenda "
    "Constitucional é promulgada pelo Congresso, não sancionada — não atribua ao ministro. "
    "(5) Deixe 'afirmacoes' como lista vazia (não há números a citar). Responda APENAS com "
    'JSON no schema: {"paragrafos_por_eixo": {<pasta>: str}, "afirmacoes": []}.'
)
```

- Modifique `montar_prompt` e `gerar_resumo` para aceitar `regras`:

```python
def montar_prompt(payload, regras: str = _REGRAS) -> str:
    return f"{regras}\n\nPAYLOAD:\n{payload.model_dump_json(indent=2)}"


def gerar_resumo(client, payload, tentativas: int = 3, regras: str = _REGRAS):
    prompt = montar_prompt(payload, regras)
    ...  # restante do corpo idêntico
```

- Atualize as anotações de tipo de `montar_prompt`/`gerar_resumo` para incluir
  `| PayloadMinisterialGoverno` no parâmetro `payload`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_guard.py tests/test_resumo.py -v`
Expected: PASS (incluindo os testes existentes).

- [ ] **Step 5: Commit**

```bash
git add app/guard.py app/resumo.py tests/test_guard.py tests/test_resumo.py
git commit -m "feat: guard e resumo aceitam payload ministerial (regras próprias)"
```

---

### Task 6: `descrever_payload` cobre o payload ministerial

**Files:**
- Modify: `app/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Produces: `descrever_payload(PayloadMinisterialGoverno) -> ("ministerial", governo)`.

> Depende do plano de persistência (que cria `descrever_payload`). Se `descrever_payload`
> ainda não existir, implemente primeiro a Task 1 daquele plano.

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_payload.py`:

```python
def test_descrever_payload_ministerial():
    from app.models import PayloadMinisterialGoverno
    from app.payload import descrever_payload

    p = PayloadMinisterialGoverno(governo="Lula 3", ano_inicio=2023, ano_fim=2026,
                                  ministros=[], medidas=[])
    assert descrever_payload(p) == ("ministerial", "Lula 3")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payload.py -k "descrever_payload_ministerial" -v`
Expected: FAIL (cai no ramo `comparacao` e retorna tupla errada, ou `AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Em `app/payload.py`, dentro de `descrever_payload`, adicione o caso ministerial ANTES do
`return ("comparacao", ...)` final:

```python
    from app.models import PayloadMinisterialGoverno  # se ainda não importado no topo
    if isinstance(payload, PayloadMinisterialGoverno):
        return ("ministerial", payload.governo)
```

(Atualize a anotação de tipo de `descrever_payload`/`hash_payload` para incluir
`| PayloadMinisterialGoverno`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payload.py -k "descrever_payload_ministerial" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/payload.py tests/test_payload.py
git commit -m "feat: descrever_payload cobre PayloadMinisterialGoverno (cache de resumo)"
```

---

### Task 7: Aba "Ministros" na UI + smoke + tracker

**Files:**
- Modify: `app/ui.py`
- Test: `tests/test_ui_smoke.py`
- Modify: `IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: `carregar_ministros`, `ministros_do_governo`, `construir_payload_ministerial`,
  `medidas_do_governo`, `salvar_medida`, `aprovar_medida`, `descartar_medida`,
  `rascunhar_medidas`, `_mostrar_resumo`, `ClaudeCodeClient`.
- Produces: aba "Ministros" (helpers `# pragma: no cover`).

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_ui_smoke.py`:

```python
def test_ui_tem_aba_ministros():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "Ministros" in src
    assert "construir_payload_ministerial" in src
    assert "rascunhar_medidas" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_ui_tem_aba_ministros -v`
Expected: FAIL no `assert "Ministros" in src`.

- [ ] **Step 3: Write minimal implementation**

Em `app/ui.py`, dentro de `main()`, adicione "Ministros" à lista de abas:

```python
    aba_ano, aba_mandato, aba_comp, aba_min = st.tabs(
        ["Por ano", "Por mandato", "Comparação", "Ministros"]
    )
```

E adicione o bloco da aba (após `aba_comp`), com imports locais (padrão do arquivo):

```python
    with aba_min:
        from app.db import (
            aprovar_medida,
            descartar_medida,
            medidas_do_governo,
            salvar_medida,
        )
        from app.medidas_ia import rascunhar_medidas
        from app.ministros import carregar_ministros, ministros_do_governo
        from app.payload import construir_payload_ministerial

        ministros = carregar_ministros()
        nome_g = st.selectbox("Governo", [m.nome for m in mandatos], key="gov_min")
        mandato_g = next(m for m in mandatos if m.nome == nome_g)
        do_gov = ministros_do_governo(ministros, nome_g)

        st.subheader("Ministros")
        st.dataframe(pd.DataFrame([
            {"pasta": m.pasta, "nome": m.nome, "início": m.inicio,
             "fim": m.fim, "fonte": m.fonte}
            for m in do_gov
        ]))

        st.subheader("Medidas aprovadas")
        aprovadas = medidas_do_governo(conn, nome_g, apenas_aprovadas=True)
        if aprovadas:
            st.dataframe(pd.DataFrame([
                {"pasta": m.pasta, "ministro": m.ministro, "título": m.titulo,
                 "descrição": m.descricao, "fonte": m.fonte_url}
                for m in aprovadas
            ]))
        else:
            st.caption("Nenhuma medida aprovada ainda.")

        st.subheader("Sugerir medidas (IA)")
        nomes_min = [f"{m.pasta} — {m.nome}" for m in do_gov]
        if nomes_min:
            escolha = st.selectbox("Ministro", nomes_min, key="min_ia")
            ministro_sel = do_gov[nomes_min.index(escolha)]
            if st.button("Sugerir medidas (IA)", key="btn_ia"):
                try:
                    rascunhos = rascunhar_medidas(ClaudeCodeClient(), ministro_sel)
                    for r in rascunhos:
                        st.warning(f"RASCUNHO (não verificado): {r.titulo}")
                        st.write(r.descricao)
                        st.write(r.fonte_url)
                        novo_id = salvar_medida(conn, r)
                        if st.button(f"Aprovar #{novo_id}", key=f"apr_{novo_id}"):
                            aprovar_medida(conn, novo_id)
                        if st.button(f"Descartar #{novo_id}", key=f"desc_{novo_id}"):
                            descartar_medida(conn, novo_id)
                except Exception as exc:
                    st.error(f"Não foi possível sugerir medidas: {exc}")

        st.subheader("Resumo do governo")
        payload_min = construir_payload_ministerial(conn, ministros, mandato_g)
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload_min)
```

> O `_mostrar_resumo` (do plano de persistência) chama `gerar_resumo(client, payload)` com as
> regras econômicas por padrão. Para o payload ministerial, ajuste `_mostrar_resumo` para
> passar `regras=_REGRAS_MINISTERIAL` quando `isinstance(payload, PayloadMinisterialGoverno)`:
> adicione no topo de `_mostrar_resumo`
> `from app.resumo import _REGRAS_MINISTERIAL` e
> `from app.models import PayloadMinisterialGoverno`, e troque a chamada por
> `resumo = gerar_resumo(client, payload, regras=_REGRAS_MINISTERIAL) if isinstance(payload, PayloadMinisterialGoverno) else gerar_resumo(client, payload)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite + typecheck + lint**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: tudo verde.

- [ ] **Step 6: Smoke manual + tracker**

Run: `PYTHONPATH=. uv run streamlit run app/ui.py`
Verifique a aba "Ministros": tabela de ministros aparece; "Sugerir medidas (IA)" gera
rascunhos marcados como não verificados (requer auth do Claude Code); aprovar move a medida
para "Medidas aprovadas"; "Gerar resumo do governo" usa só aprovadas. Encerre com Ctrl+C.

Em `IMPLEMENTATION_PLAN.md`, seção "Feito", adicione:
`- Camada ministerial (ministros YAML + medidas com aprovação + resumo) — spec/plano 2026-06-21.`

- [ ] **Step 7: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py IMPLEMENTATION_PLAN.md
git commit -m "feat: aba Ministros (medidas, rascunho IA, resumo) + tracker"
```

---

## Notas de verificação do plano

- **Cobertura do spec:** config YAML + loader validado (T1); tabela `medidas` + CRUD/aprovação
  (T2); assistente de rascunho IA com fonte obrigatória (T3); payload só-aprovadas (T4);
  guard/resumo ministerial com regras próprias e afirmacoes vazias (T5); cache de resumo via
  `descrever_payload` (T6); UI navegável + rascunho + aprovação + resumo (T7).
- **Princípio anti-alucinação:** rascunho exige `fonte_url` (T3), nunca entra no payload
  (T4 filtra `aprovada`), guard barra estatística inventada no texto (T5).
- **Consistência de tipos:** `Medida`/`Ministro`/`MedidaResumo`/`PayloadMinisterialGoverno`
  definidos em T1/T4 e usados igualmente em T2–T7; `gerar_resumo(..., regras=...)` definido em
  T5 e consumido em T7.
- **Dependência:** assume o plano de persistência de resumos implementado (descrever_payload,
  _mostrar_resumo com `conn`, salvar_resumo).
- **YAGNI:** sem scraping de ministros, sem biografia, sem cruzamento medida↔indicador.
```
