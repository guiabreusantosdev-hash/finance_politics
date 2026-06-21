"""Fetcher de leis sancionadas a partir dos arquivos anuais da Câmara."""
from __future__ import annotations

import datetime

import httpx

from app.models import Lei

URL_PROP = "https://dadosabertos.camara.leg.br/arquivos/proposicoes/json/proposicoes-{ano}.json"
URL_TEMAS = "https://dadosabertos.camara.leg.br/arquivos/proposicoesTemas/json/proposicoesTemas-{ano}.json"

MAPA_TIPO: dict[str, str] = {"PL": "LO", "PLP": "LC", "MPV": "MP", "PEC": "EC"}

# Case-insensitive substring to match the REAL API value "Transformado em Norma Jurídica"
# (the brief erroneously wrote "Transformada"; the spike notes confirmed the masculine form)
_SITUACAO_SUBSTRING = "transformado em norma"


def _parse_date(value: str | None) -> datetime.date:
    """Parse ISO date string (with or without time component); fallback to epoch."""
    if not value:
        return datetime.date(1900, 1, 1)
    return datetime.date.fromisoformat(value[:10])


def normalizar_leis(
    prop_json: dict,
    temas_json: dict,
) -> tuple[list[Lei], dict[str, list[str]]]:
    """
    Filter and normalize Câmara proposições into Lei DTOs.

    Args:
        prop_json: JSON from proposicoes-{ano}.json (array under key 'dados').
        temas_json: JSON from proposicoesTemas-{ano}.json (array under key 'dados').

    Returns:
        A tuple (leis, temas_por_lei) where:
        - leis: list of Lei with tipo in {LO, LC, MP, EC}
        - temas_por_lei: dict mapping lei id → list of tema strings
    """
    dados: list[dict] = prop_json.get("dados", prop_json)
    temas_dados: list[dict] = temas_json.get("dados", temas_json)

    leis: list[Lei] = []
    ids_ok: set[str] = set()

    for p in dados:
        sigla: str | None = p.get("siglaTipo")
        if sigla not in MAPA_TIPO:
            continue  # non-mapped type — discard even if transformed

        status: dict = p.get("ultimoStatus") or {}
        situacao: str = status.get("descricaoSituacao") or ""
        if _SITUACAO_SUBSTRING not in situacao.lower():
            continue  # not transformed into law

        lid = f"camara_{p['id']}"
        ids_ok.add(lid)

        # Use ultimoStatus["data"] — NOT "dataHora" (field does not exist per spike notes)
        data_str: str | None = status.get("data") or p.get("dataApresentacao")
        leis.append(
            Lei(
                id=lid,
                tipo=MAPA_TIPO[sigla],
                numero=str(p.get("numero", "")),
                ano=int(p.get("ano", 0)),
                data=_parse_date(data_str),
                ementa=p.get("ementa") or "",
                url=p.get("uri") or "",
            )
        )

    # Build temas_por_lei: join by the id parsed from the end of uriProposicao
    # (spike notes confirm: field is 'uriProposicao', NOT 'idProposicao')
    temas_por_lei: dict[str, list[str]] = {}
    for t in temas_dados:
        uri: str = t.get("uriProposicao") or ""
        pid = uri.rstrip("/").split("/")[-1]
        lid = f"camara_{pid}"
        if lid in ids_ok and t.get("tema"):
            temas_por_lei.setdefault(lid, []).append(t["tema"])

    return leis, temas_por_lei


class CamaraLeisFetcher:
    """Thin network wrapper around normalizar_leis."""

    def fetch(
        self,
        ano: int,
        client: httpx.Client,
    ) -> tuple[dict, list[Lei], dict[str, list[str]]]:
        """Fetch annual proposicoes and temas files, return raw JSON + normalized data."""
        prop = client.get(URL_PROP.format(ano=ano), timeout=60).json()
        temas = client.get(URL_TEMAS.format(ano=ano), timeout=60).json()
        leis, temas_por_lei = normalizar_leis(prop, temas)
        return {"prop": prop, "temas": temas}, leis, temas_por_lei
