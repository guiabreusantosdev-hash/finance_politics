"""SQLite storage: schema, upserts, queries (long format)."""
from __future__ import annotations

import datetime
import json
import sqlite3
from typing import TYPE_CHECKING

from app.models import Indicador, Observacao

if TYPE_CHECKING:
    from app.models import ResumoRegistro

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
