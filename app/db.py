"""SQLite storage: schema, upserts, queries (long format)."""
from __future__ import annotations

import datetime
import json
import sqlite3
from typing import TYPE_CHECKING

from app.models import Indicador, Observacao

if TYPE_CHECKING:
    from app.models import Medida, ResumoRegistro

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
CREATE TABLE IF NOT EXISTS resumos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT, identificador TEXT, payload_hash TEXT,
    payload_json TEXT, resumo_json TEXT, veredito_json TEXT,
    modelo TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_resumos_lookup
    ON resumos (tipo, identificador, criado_em);
CREATE TABLE IF NOT EXISTS medidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    governo TEXT, pasta TEXT, ministro TEXT, titulo TEXT, descricao TEXT,
    fonte_url TEXT, status TEXT, origem TEXT, criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_medidas_governo ON medidas (governo, status);
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
        """INSERT INTO series (id, fonte, codigo_fonte, nome, unidade,
           periodicidade, eixo)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             fonte=excluded.fonte, codigo_fonte=excluded.codigo_fonte,
             nome=excluded.nome, unidade=excluded.unidade,
             periodicidade=excluded.periodicidade, eixo=excluded.eixo""",
        (
            ind.id,
            ind.fonte,
            ind.codigo_fonte,
            ind.nome,
            ind.unidade,
            ind.periodicidade,
            ind.eixo,
        ),
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
    conn: sqlite3.Connection,
    serie_id: str,
    executado_em: str,
    status: str,
    n: int,
    erro: str | None,
) -> None:
    conn.execute(
        """INSERT INTO ingestao_log (serie_id, executado_em, status,
           n_registros, erro) VALUES (?, ?, ?, ?, ?)""",
        (serie_id, executado_em, status, n, erro),
    )
    conn.commit()


def observacoes_da_serie(
    conn: sqlite3.Connection, serie_id: str
) -> list[Observacao]:
    cur = conn.execute(
        """SELECT serie_id, data, valor FROM observacoes
           WHERE serie_id = ? ORDER BY data""",
        (serie_id,),
    )
    return [
        Observacao(
            serie_id=r[0], data=datetime.date.fromisoformat(r[1]), valor=r[2]
        )
        for r in cur.fetchall()
    ]


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
    assert cur.lastrowid is not None
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
    assert cur.lastrowid is not None
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
