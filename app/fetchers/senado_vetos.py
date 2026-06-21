"""Fetcher dos vetos do Congresso Nacional (Dados Abertos do Senado)."""
from __future__ import annotations

import datetime

import httpx

from app.models import Veto

URL_VETOS = (
    "https://legis.senado.leg.br/dadosabertos/dados/ListaVetosAnoCN{ano}.json"
)
_HEADERS = {"Accept": "application/json"}


def _tipo(total: str) -> str:
    """Map Total field: 'Sim' → 'total', anything else → 'parcial'."""
    return "total" if (total or "").strip() == "Sim" else "parcial"


def normalizar_vetos(veto_json: dict) -> list[Veto]:
    """Pure function: convert raw API JSON → list[Veto].

    Array path: veto_json["ListaVetosAnoCN"]["Vetos"]["Veto"]
    """
    lista = veto_json.get("ListaVetosAnoCN", {})
    vetos_wrapper = lista.get("Vetos", {})
    raw_vetos = vetos_wrapper.get("Veto", [])

    # API may return a single dict when there is only one veto
    if isinstance(raw_vetos, dict):
        raw_vetos = [raw_vetos]

    result: list[Veto] = []
    for v in raw_vetos:
        codigo = v.get("Codigo", "")
        if not codigo:
            continue

        vid = f"senado_{codigo}"

        # Date: prefer DataRecebimentoCongresso, fallback DataPublicacao
        data_str = v.get("DataRecebimentoCongresso") or v.get("DataPublicacao") or ""
        if not data_str:
            continue  # skip vetos with no usable date
        data: datetime.date = datetime.date.fromisoformat(data_str[:10])

        tipo = _tipo(v.get("Total", ""))

        # descricao: Assunto fallback Materia.Ementa
        descricao: str = v.get("Assunto") or ""
        if not descricao:
            materia_obj = v.get("Materia") or {}
            descricao = materia_obj.get("Ementa") or ""

        # materia: "SIGLA NUMERO/ANO" from MateriaVetada, fallback NormaGerada.NomeNorma
        materia_vetada = v.get("MateriaVetada") or {}
        sigla = materia_vetada.get("Sigla", "")
        numero = materia_vetada.get("Numero", "")
        ano = materia_vetada.get("Ano", "")
        if sigla and numero and ano:
            materia = f"{sigla} {numero}/{ano}"
        else:
            norma = materia_vetada.get("NormaGerada") or {}
            materia = norma.get("NomeNorma") or ""

        # url: Materia.UrlMovimentacoes fallback ""
        materia_obj = v.get("Materia") or {}
        url: str = materia_obj.get("UrlMovimentacoes") or ""

        result.append(
            Veto(
                id=vid,
                data=data,
                tipo=tipo,
                descricao=descricao,
                materia=materia,
                url=url,
            )
        )

    return result


class SenadoVetosFetcher:
    """Thin HTTP wrapper around normalizar_vetos."""

    def fetch(self, ano: int, client: httpx.Client) -> tuple[dict, list[Veto]]:
        raw: dict = client.get(
            URL_VETOS.format(ano=ano),
            headers=_HEADERS,
            timeout=60,
        ).json()
        return raw, normalizar_vetos(raw)
