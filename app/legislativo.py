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


def filtrar_leis(leis, temas_por_lei, tipos_sel, temas_sel):
    def ok(lei):
        if tipos_sel and lei.tipo not in tipos_sel:
            return False
        if temas_sel and not (set(temas_por_lei.get(lei.id, [])) & set(temas_sel)):
            return False
        return True

    return [lei for lei in leis if ok(lei)]
