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
