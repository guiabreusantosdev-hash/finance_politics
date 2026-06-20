"""Deterministic factuality guard: every cited number must exist in the payload."""
from __future__ import annotations

import re

from app.models import PayloadAno, PayloadComparacao, ResumoFactual

_NUM = re.compile(r"-?\d+(?:[.\s]\d{3})*(?:[.,]\d+)?")


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
