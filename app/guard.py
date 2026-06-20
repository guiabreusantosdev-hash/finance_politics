"""Deterministic factuality guard: every cited number must exist in the payload."""
from __future__ import annotations

import re

from app.models import PayloadAno, PayloadComparacao, PayloadMandato, ResumoFactual

_NUM = re.compile(r"(?<![.\d])-?\d+(?:[.\s]\d{3})*(?:[.,]\d+)?")


class GuardError(ValueError):
    pass


def _parse_match(m: str) -> float:
    """Parse a raw regex match string to float (handles pt-BR comma decimals)."""
    limpo = m.replace(" ", "")
    if "," in limpo:  # pt-BR decimal comma; dots are thousands
        limpo = limpo.replace(".", "").replace(",", ".")
    return float(limpo)


def _extrair_numeros_com_tipo(texto: str) -> list[tuple[float, bool]]:
    """Return (value, is_rate_like) for every number matched in texto.

    is_rate_like is True when:
    - the matched substring contains a decimal separator followed by digits
      (e.g. "11,75" or "6.5"), OR
    - the character immediately after the match is '%'.

    Bare integers with no decimal and no trailing '%' are NOT rate-like.
    """
    results: list[tuple[float, bool]] = []
    for match in _NUM.finditer(texto):
        raw = match.group()
        try:
            value = _parse_match(raw)
        except ValueError:
            continue

        # Check for decimal/fractional part in the matched string
        has_decimal = bool(re.search(r"[.,]\d", raw))

        # Check if immediately followed by '%'
        end_pos = match.end()
        followed_by_percent = end_pos < len(texto) and texto[end_pos] == "%"

        is_rate_like = has_decimal or followed_by_percent
        results.append((value, is_rate_like))
    return results


def extrair_numeros(texto: str) -> list[float]:
    """Return list of float values for all numbers in texto. Preserves original behaviour."""
    return [v for v, _ in _extrair_numeros_com_tipo(texto)]


def numeros_permitidos(payload: PayloadAno | PayloadComparacao | PayloadMandato) -> set[float]:
    """Return ONLY genuine payload numbers — no small-integer allowlist."""
    nums: set[float] = set()
    if isinstance(payload, PayloadAno):
        nums.add(float(payload.ano))
        for vi in payload.indicadores:
            if vi.valor is not None:
                nums.add(vi.valor)
    elif isinstance(payload, PayloadMandato):
        nums.add(float(payload.ano_inicio))
        nums.add(float(payload.ano_fim))
        for vi in payload.indicadores:
            for v in (vi.valor_inicio, vi.valor_fim, vi.variacao):
                if v is not None:
                    nums.add(v)
    else:
        nums.add(float(payload.ano_inicio_a))
        nums.add(float(payload.ano_fim_a))
        nums.add(float(payload.ano_inicio_b))
        nums.add(float(payload.ano_fim_b))
        for d in payload.deltas:
            for v in (d.valor_a, d.valor_b, d.delta):
                if v is not None:
                    nums.add(v)
    return nums


def _proximo(alvo: float, permitidos: set[float], tol: float) -> bool:
    return any(abs(alvo - p) <= tol for p in permitidos)


def verificar(
    resumo: ResumoFactual,
    payload: PayloadAno | PayloadComparacao | PayloadMandato,
    tolerancia: float = 0.05,
) -> None:
    permitidos = numeros_permitidos(payload)
    # Structured check: every valor_citado must be in the strict payload set
    for af in resumo.afirmacoes:
        if not _proximo(af.valor_citado, permitidos, tolerancia):
            raise GuardError(f"valor_citado {af.valor_citado} não existe no payload")
    # Free-text check: only enforce rate-like numbers (decimal or %-suffixed)
    for texto in resumo.paragrafos_por_eixo.values():
        for valor, is_rate_like in _extrair_numeros_com_tipo(texto):
            if is_rate_like and not _proximo(valor, permitidos, tolerancia):
                raise GuardError(f"número {valor} no texto não existe no payload")
