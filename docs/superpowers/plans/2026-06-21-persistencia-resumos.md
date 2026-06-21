# Persistência de Resumos (cache + histórico) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gravar todo resumo gerado pela IA num SQLite, reusando por hash de payload (cache) e mantendo o histórico de todas as versões.

**Architecture:** Funções puras em `app/payload.py` derivam hash + identificação do payload. A camada `app/db.py` ganha uma tabela `resumos` e funções de salvar/buscar/listar. Um DTO `ResumoRegistro` em `app/models.py` carrega registros lidos. A UI (`app/ui.py`) passa a exibir o cache automaticamente, com botão "Regerar" e um expander de histórico.

**Tech Stack:** Python 3.12, SQLite (`sqlite3`), Pydantic v2, pytest, hashlib (stdlib).

## Global Constraints

- Python `>=3.12`; type-checking modo `standard` (pyright) sobre `app` e `tests`.
- Ruff `line-length = 100`.
- **O LLM nunca calcula números** — esta feature só persiste o que já foi gerado.
- **Zero rede nos testes:** `LLMClient` e HTTP sempre mockados; estes testes nem chamam LLM.
- SQLite em long format; conexões de teste usam `conectar(":memory:")`.
- Commits pequenos, um por tarefa; mensagem descreve a tarefa concluída; TDD (teste antes).
- Não adicionar dependências novas (tudo é stdlib + libs já presentes).

---

### Task 1: Hash e descrição de payload (`app/payload.py`)

**Files:**
- Modify: `app/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Consumes: `PayloadAno`, `PayloadMandato`, `PayloadComparacao` de `app/models.py`.
- Produces:
  - `hash_payload(payload: PayloadAno | PayloadMandato | PayloadComparacao) -> str`
    (sha256 hex de `payload.model_dump_json()`).
  - `descrever_payload(payload: PayloadAno | PayloadMandato | PayloadComparacao) -> tuple[str, str]`
    retornando `(tipo, identificador)`:
    - `PayloadAno` → `("ano", str(payload.ano))`
    - `PayloadMandato` → `("mandato", payload.mandato)`
    - `PayloadComparacao` → `("comparacao", f"{payload.mandato_a} × {payload.mandato_b}")`

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_payload.py`:

```python
from app.models import PayloadAno, PayloadComparacao, PayloadMandato
from app.payload import descrever_payload, hash_payload


def _payload_ano(ano: int = 2024) -> PayloadAno:
    return PayloadAno(ano=ano, indicadores=[], faltantes=[])


def test_hash_payload_deterministico():
    p = _payload_ano()
    assert hash_payload(p) == hash_payload(_payload_ano())


def test_hash_payload_muda_com_os_dados():
    assert hash_payload(_payload_ano(2024)) != hash_payload(_payload_ano(2023))


def test_descrever_payload_ano():
    assert descrever_payload(_payload_ano(2024)) == ("ano", "2024")


def test_descrever_payload_mandato():
    p = PayloadMandato(
        mandato="Lula 3", ano_inicio=2023, ano_fim=2026, indicadores=[], faltantes=[]
    )
    assert descrever_payload(p) == ("mandato", "Lula 3")


def test_descrever_payload_comparacao():
    p = PayloadComparacao(
        mandato_a="Lula 3", mandato_b="Bolsonaro",
        ano_inicio_a=2023, ano_fim_a=2026, ano_inicio_b=2019, ano_fim_b=2022,
        deltas=[],
    )
    assert descrever_payload(p) == ("comparacao", "Lula 3 × Bolsonaro")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_payload.py -k "hash_payload or descrever" -v`
Expected: FAIL com `ImportError: cannot import name 'hash_payload'`.

- [ ] **Step 3: Write minimal implementation**

No topo de `app/payload.py`, adicione aos imports stdlib:

```python
import hashlib
```

E ao final do arquivo:

```python
def hash_payload(payload: PayloadAno | PayloadMandato | PayloadComparacao) -> str:
    return hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()


def descrever_payload(
    payload: PayloadAno | PayloadMandato | PayloadComparacao,
) -> tuple[str, str]:
    if isinstance(payload, PayloadAno):
        return ("ano", str(payload.ano))
    if isinstance(payload, PayloadMandato):
        return ("mandato", payload.mandato)
    return ("comparacao", f"{payload.mandato_a} × {payload.mandato_b}")
```

Confirme que `PayloadAno`, `PayloadMandato` e `PayloadComparacao` estão no bloco
`from app.models import (...)` já existente; adicione os que faltarem.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_payload.py -k "hash_payload or descrever" -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Commit**

```bash
git add app/payload.py tests/test_payload.py
git commit -m "feat: hash_payload + descrever_payload (chave de cache de resumos)"
```

---

### Task 2: DTO `ResumoRegistro` (`app/models.py`)

**Files:**
- Modify: `app/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `ResumoFactual` (já em `app/models.py`).
- Produces:
  ```python
  class ResumoRegistro(BaseModel):
      id: int
      tipo: str
      identificador: str
      payload_hash: str
      resumo: ResumoFactual
      veredito: dict | None
      modelo: str
      criado_em: str
  ```
  `veredito` é `dict | None` (não `Veredito`) para evitar import cíclico com `app/judge.py`.

- [ ] **Step 1: Write the failing test**

Em `tests/test_models.py`, adicione `ResumoRegistro` à linha de import existente
(`from app.models import Indicador, Observacao, PayloadAno, ResumoFactual, ResumoRegistro, ValorIndicador`)
— não crie uma segunda linha de import (evita ruff F811). Depois adicione ao final:

```python
def test_resumo_registro_aceita_veredito_none():
    reg = ResumoRegistro(
        id=1,
        tipo="ano",
        identificador="2024",
        payload_hash="abc",
        resumo=ResumoFactual(paragrafos_por_eixo={"macro": "x"}, afirmacoes=[]),
        veredito=None,
        modelo="claude-code-default",
        criado_em="2026-06-21T00:00:00",
    )
    assert reg.veredito is None
    assert reg.resumo.paragrafos_por_eixo["macro"] == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_resumo_registro_aceita_veredito_none -v`
Expected: FAIL com `ImportError: cannot import name 'ResumoRegistro'`.

- [ ] **Step 3: Write minimal implementation**

Ao final de `app/models.py`:

```python
class ResumoRegistro(BaseModel):
    id: int
    tipo: str
    identificador: str
    payload_hash: str
    resumo: ResumoFactual
    veredito: dict | None
    modelo: str
    criado_em: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::test_resumo_registro_aceita_veredito_none -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: DTO ResumoRegistro para registros de resumo persistidos"
```

---

### Task 3: Tabela `resumos` + storage (`app/db.py`)

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes:
  - `hash_payload`, `descrever_payload` de `app/payload.py`.
  - `ResumoRegistro`, `ResumoFactual`, `PayloadAno|PayloadMandato|PayloadComparacao` de `app/models.py`.
  - `Veredito` de `app/judge.py` (apenas como tipo opcional de entrada).
- Produces:
  - `salvar_resumo(conn, *, payload, resumo: ResumoFactual, veredito, modelo: str, criado_em: str | None = None) -> int`
    (`veredito`: `Veredito | None`; retorna o `id` inserido).
  - `buscar_resumo_cache(conn, payload_hash: str) -> ResumoRegistro | None`
    (registro mais recente daquele hash, ou `None`).
  - `historico_resumos(conn, tipo: str, identificador: str) -> list[ResumoRegistro]`
    (mais recente primeiro).

> **Nota de import cíclico:** `app/payload.py` importa de `app/db.py` (`observacoes_da_serie`).
> Para evitar ciclo, importe `hash_payload`/`descrever_payload` **dentro** de `salvar_resumo`
> (import local), não no topo de `db.py`. O tipo `Veredito` deve entrar só sob
> `if TYPE_CHECKING:` para não criar ciclo em runtime (`judge.py` importa de `models`, não de `db`,
> então não há ciclo real, mas mantemos o import de runtime fora para robustez — serializamos via
> `.model_dump_json()` por duck-typing).

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_db.py`:

```python
from app.db import (
    buscar_resumo_cache,
    historico_resumos,
    salvar_resumo,
)
from app.models import PayloadAno, ResumoFactual
from app.payload import hash_payload


def _payload(ano: int = 2024) -> PayloadAno:
    return PayloadAno(ano=ano, indicadores=[], faltantes=[])


def _resumo(txt: str = "x") -> ResumoFactual:
    return ResumoFactual(paragrafos_por_eixo={"macro": txt}, afirmacoes=[])


def test_salvar_e_buscar_cache_roundtrip():
    conn = conectar(":memory:")
    criar_schema(conn)
    p = _payload()
    rid = salvar_resumo(
        conn, payload=p, resumo=_resumo("v1"), veredito=None,
        modelo="claude-code-default", criado_em="2026-06-21T10:00:00",
    )
    assert isinstance(rid, int)
    reg = buscar_resumo_cache(conn, hash_payload(p))
    assert reg is not None
    assert reg.resumo.paragrafos_por_eixo["macro"] == "v1"
    assert reg.veredito is None
    assert reg.tipo == "ano" and reg.identificador == "2024"


def test_buscar_cache_retorna_o_mais_recente():
    conn = conectar(":memory:")
    criar_schema(conn)
    p = _payload()
    salvar_resumo(conn, payload=p, resumo=_resumo("v1"), veredito=None,
                  modelo="m", criado_em="2026-06-21T10:00:00")
    salvar_resumo(conn, payload=p, resumo=_resumo("v2"), veredito=None,
                  modelo="m", criado_em="2026-06-21T11:00:00")
    reg = buscar_resumo_cache(conn, hash_payload(p))
    assert reg is not None
    assert reg.resumo.paragrafos_por_eixo["macro"] == "v2"


def test_buscar_cache_miss_retorna_none():
    conn = conectar(":memory:")
    criar_schema(conn)
    assert buscar_resumo_cache(conn, "inexistente") is None


def test_historico_ordena_e_filtra():
    conn = conectar(":memory:")
    criar_schema(conn)
    p2024, p2023 = _payload(2024), _payload(2023)
    salvar_resumo(conn, payload=p2024, resumo=_resumo("a"), veredito=None,
                  modelo="m", criado_em="2026-06-21T10:00:00")
    salvar_resumo(conn, payload=p2024, resumo=_resumo("b"), veredito=None,
                  modelo="m", criado_em="2026-06-21T11:00:00")
    salvar_resumo(conn, payload=p2023, resumo=_resumo("c"), veredito=None,
                  modelo="m", criado_em="2026-06-21T12:00:00")
    hist = historico_resumos(conn, "ano", "2024")
    assert [r.resumo.paragrafos_por_eixo["macro"] for r in hist] == ["b", "a"]


def test_salvar_resumo_persiste_veredito_dict():
    conn = conectar(":memory:")
    criar_schema(conn)
    p = _payload()

    class _Vd:
        def model_dump_json(self) -> str:
            return '{"ancorado": true, "neutro": true, "numeros_fora_do_payload": [], "observacoes": "ok"}'

    salvar_resumo(conn, payload=p, resumo=_resumo(), veredito=_Vd(),
                  modelo="m", criado_em="2026-06-21T10:00:00")
    reg = buscar_resumo_cache(conn, hash_payload(p))
    assert reg is not None
    assert reg.veredito == {
        "ancorado": True, "neutro": True,
        "numeros_fora_do_payload": [], "observacoes": "ok",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -k "cache or historico or veredito" -v`
Expected: FAIL com `ImportError: cannot import name 'salvar_resumo'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/db.py`, adicione `import json` ao bloco de imports stdlib (junto de `datetime`/`sqlite3`).

Adicione a tabela ao `_SCHEMA` (antes do fechamento `"""`):

```sql
CREATE TABLE IF NOT EXISTS resumos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT, identificador TEXT, payload_hash TEXT,
    payload_json TEXT, resumo_json TEXT, veredito_json TEXT,
    modelo TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_resumos_lookup
    ON resumos (tipo, identificador, criado_em);
```

Adicione as funções ao final de `app/db.py`:

```python
def _registro_de_row(row: tuple) -> "ResumoRegistro":
    from app.models import ResumoFactual, ResumoRegistro

    return ResumoRegistro(
        id=row[0],
        tipo=row[1],
        identificador=row[2],
        payload_hash=row[3],
        resumo=ResumoFactual.model_validate_json(row[5]),
        veredito=json.loads(row[6]) if row[6] is not None else None,
        modelo=row[7],
        criado_em=row[8],
    )


def salvar_resumo(
    conn: sqlite3.Connection,
    *,
    payload,
    resumo,
    veredito,
    modelo: str,
    criado_em: str | None = None,
) -> int:
    from app.payload import descrever_payload, hash_payload

    tipo, identificador = descrever_payload(payload)
    quando = criado_em or datetime.datetime.now().isoformat()
    cur = conn.execute(
        """INSERT INTO resumos (tipo, identificador, payload_hash, payload_json,
           resumo_json, veredito_json, modelo, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tipo,
            identificador,
            hash_payload(payload),
            payload.model_dump_json(),
            resumo.model_dump_json(),
            veredito.model_dump_json() if veredito is not None else None,
            modelo,
            quando,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


_COLS_RESUMO = (
    "id, tipo, identificador, payload_hash, payload_json, "
    "resumo_json, veredito_json, modelo, criado_em"
)


def buscar_resumo_cache(
    conn: sqlite3.Connection, payload_hash: str
) -> "ResumoRegistro | None":
    cur = conn.execute(
        f"""SELECT {_COLS_RESUMO} FROM resumos WHERE payload_hash = ?
            ORDER BY criado_em DESC, id DESC LIMIT 1""",
        (payload_hash,),
    )
    row = cur.fetchone()
    return _registro_de_row(row) if row is not None else None


def historico_resumos(
    conn: sqlite3.Connection, tipo: str, identificador: str
) -> "list[ResumoRegistro]":
    cur = conn.execute(
        f"""SELECT {_COLS_RESUMO} FROM resumos
            WHERE tipo = ? AND identificador = ?
            ORDER BY criado_em DESC, id DESC""",
        (tipo, identificador),
    )
    return [_registro_de_row(r) for r in cur.fetchall()]
```

> Os tipos em string (`"ResumoRegistro | None"`) evitam import de runtime no topo;
> `_registro_de_row` faz o import local. `payload`/`resumo`/`veredito` são serializados
> por duck-typing (`.model_dump_json()`), o que mantém `db.py` sem depender de `judge.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -k "cache or historico or veredito" -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Run full suite + typecheck + lint**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: tabela resumos + salvar/buscar_cache/historico (storage)"
```

---

### Task 4: Wire na UI — cache automático, botão Regerar, histórico (`app/ui.py`)

**Files:**
- Modify: `app/ui.py`
- Test: `tests/test_ui_smoke.py` (smoke de import; `main`/helpers continuam `# pragma: no cover`)

**Interfaces:**
- Consumes: `buscar_resumo_cache`, `salvar_resumo`, `historico_resumos` de `app/db.py`;
  `hash_payload`, `descrever_payload` de `app/payload.py`; `gerar_resumo`, `julgar`,
  `ClaudeCodeClient` (já usados).
- Produces: nada importável novo (mudança interna de fluxo da UI).

- [ ] **Step 1: Write the failing test**

Adicione ao final de `tests/test_ui_smoke.py` (confirme primeiro o que o arquivo já importa
para não duplicar):

```python
def test_ui_importa_helpers_de_persistencia():
    import app.ui as ui

    src = __import__("inspect").getsource(ui)
    assert "buscar_resumo_cache" in src
    assert "salvar_resumo" in src
    assert "historico_resumos" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui_smoke.py::test_ui_importa_helpers_de_persistencia -v`
Expected: FAIL no `assert "buscar_resumo_cache" in src`.

- [ ] **Step 3: Write minimal implementation**

Em `app/ui.py`, reescreva `_mostrar_resumo` para receber a conexão e o payload-hash, exibir
cache, salvar após gerar, e renderizar o histórico. Substitua a função atual por:

```python
def _mostrar_resumo(st, conn, client, payload) -> None:  # pragma: no cover
    from app.db import buscar_resumo_cache, historico_resumos, salvar_resumo
    from app.judge import julgar
    from app.payload import descrever_payload, hash_payload
    from app.resumo import gerar_resumo

    ph = hash_payload(payload)
    tipo, identificador = descrever_payload(payload)
    cache = buscar_resumo_cache(conn, ph)

    if cache is not None:
        st.success(f"✅ Em cache (gerado em {cache.criado_em} · {cache.modelo})")
        for eixo, txt in cache.resumo.paragrafos_por_eixo.items():
            st.markdown(f"**{eixo}** — {txt}")
    label = "Regerar resumo" if cache is not None else "Gerar resumo"

    if st.button(label, key=f"btn_{tipo}_{identificador}"):
        try:
            resumo = gerar_resumo(client, payload)
            veredito = None
            try:
                veredito = julgar(client, payload, resumo)
                if not veredito.ancorado or not veredito.neutro:
                    aviso = f"⚠️ O juiz de IA detectou problemas: {veredito.observacoes}"
                    if veredito.numeros_fora_do_payload:
                        aviso += f" Números fora do payload: {veredito.numeros_fora_do_payload}"
                    st.warning(aviso)
            except Exception:
                pass  # juiz é não-fatal
            salvar_resumo(
                conn,
                payload=payload,
                resumo=resumo,
                veredito=veredito,
                modelo=client.modelo or "claude-code-default",
            )
            st.info("Resumo gerado e salvo:")
            for eixo, txt in resumo.paragrafos_por_eixo.items():
                st.markdown(f"**{eixo}** — {txt}")
        except ValueError as exc:
            st.error(f"Não foi possível gerar o resumo: {exc}")

    hist = historico_resumos(conn, tipo, identificador)
    if hist:
        with st.expander(f"Histórico ({len(hist)})"):
            for reg in hist:
                flag = ""
                if reg.veredito is not None:
                    ok = reg.veredito.get("ancorado") and reg.veredito.get("neutro")
                    flag = " ✅" if ok else " ⚠️"
                st.markdown(f"- **{reg.criado_em}** · {reg.modelo}{flag}")
```

Atualize as 3 chamadas em `main()` para passar `conn`:
- `_mostrar_resumo(st, ClaudeCodeClient(), payload)` → `_mostrar_resumo(st, conn, ClaudeCodeClient(), payload)`
- `_mostrar_resumo(st, ClaudeCodeClient(), payload_m)` → `_mostrar_resumo(st, conn, ClaudeCodeClient(), payload_m)`
- `_mostrar_resumo(st, ClaudeCodeClient(), payload_c)` → `_mostrar_resumo(st, conn, ClaudeCodeClient(), payload_c)`

E remova os três `if st.button(...)` agora redundantes nas abas (o botão passou para dentro
de `_mostrar_resumo`): substitua cada bloco
```python
        if st.button("Gerar resumo do ano"):
            _mostrar_resumo(st, ClaudeCodeClient(), payload)
```
por uma chamada direta:
```python
        _mostrar_resumo(st, conn, ClaudeCodeClient(), payload)
```
(idem para mandato e comparação, com `payload_m` / `payload_c`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite + typecheck + lint**

Run: `uv run pytest -q && uv run pyright && uv run ruff check .`
Expected: tudo verde.

- [ ] **Step 6: Commit**

```bash
git add app/ui.py tests/test_ui_smoke.py
git commit -m "feat: UI exibe resumo em cache, botão Regerar e histórico"
```

---

### Task 5: Smoke manual + atualizar tracker

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Smoke manual do app**

Run: `PYTHONPATH=. uv run streamlit run app/ui.py`
Verifique: gerar um resumo numa aba; recarregar a página → aparece "✅ Em cache";
clicar "Regerar" cria nova entrada no expander "Histórico". Encerre com Ctrl+C.

> Requer auth do Claude Code ativa. Se não houver, valide só que o app sobe sem
> `ModuleNotFoundError` e que o expander de histórico renderiza.

- [ ] **Step 2: Atualizar o tracker**

Em `IMPLEMENTATION_PLAN.md`, adicione na seção "Feito":
`- Persistência de resumos (cache + histórico) — spec+plano 2026-06-21.`

- [ ] **Step 3: Commit**

```bash
git add IMPLEMENTATION_PLAN.md
git commit -m "docs: registra persistência de resumos no tracker"
```

---

## Notas de verificação do plano

- **Cobertura do spec:** tabela `resumos` (T3); hash como chave de cache (T1); cache reusa +
  regenera por hash (T3+T4); conteúdo (resumo/veredito/payload/modelo) (T3); UI cache+Regerar+
  histórico (T4); testes dos alvos puros/storage (T1–T3). `main`/`_mostrar_resumo` seguem
  `# pragma: no cover` conforme o spec.
- **Import cíclico:** `payload.py` ↔ `db.py` resolvido com imports locais dentro de
  `salvar_resumo`/`_registro_de_row`; `veredito` serializado por duck-typing, sem import de `judge`.
- **YAGNI:** sem purga, diff ou export (fora de escopo no spec).
