"""Ingestão da camada legislativa: leis (Câmara) + vetos (Senado)."""
from __future__ import annotations

import datetime

import httpx

from app.config_loader import carregar_mandatos
from app.db import (
    conectar,
    criar_schema,
    registrar_ingestao,
    upsert_lei_temas,
    upsert_leis,
    upsert_vetos,
)
from app.fetchers.camara import CamaraLeisFetcher
from app.fetchers.senado_vetos import SenadoVetosFetcher
from app.ingest import salvar_raw


def anos_dos_mandatos(mandatos) -> list[int]:
    anos: set[int] = set()
    for m in mandatos:
        for a in range(m.inicio.year, m.fim.year + 1):
            anos.add(a)
    return sorted(anos)


def ingerir_legislativo(conn, anos, client, agora, *, camara=None, vetos=None) -> dict[str, int]:
    camara = camara or CamaraLeisFetcher()
    vetos = vetos or SenadoVetosFetcher()
    total_leis = total_vetos = 0
    for ano in anos:
        try:
            raw, leis, temas_por_lei = camara.fetch(ano, client)
            salvar_raw("CAMARA", f"leis_{ano}", raw, agora)
            total_leis += upsert_leis(conn, leis)
            for lid, temas in temas_por_lei.items():
                upsert_lei_temas(conn, lid, temas)
            registrar_ingestao(conn, f"camara_leis_{ano}", agora, "ok", len(leis), None)
        except Exception as exc:  # noqa: BLE001 - um ano quebrado não derruba o pipeline
            registrar_ingestao(conn, f"camara_leis_{ano}", agora, "erro", 0, str(exc))
        try:
            raw_v, vs = vetos.fetch(ano, client)
            salvar_raw("SENADO", f"vetos_{ano}", raw_v, agora)
            total_vetos += upsert_vetos(conn, vs)
            registrar_ingestao(conn, f"senado_vetos_{ano}", agora, "ok", len(vs), None)
        except Exception as exc:  # noqa: BLE001 - um ano quebrado não derruba o pipeline
            registrar_ingestao(conn, f"senado_vetos_{ano}", agora, "erro", 0, str(exc))
    return {"leis": total_leis, "vetos": total_vetos}


def main() -> None:  # pragma: no cover - smoke manual com rede
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    conn = conectar()
    criar_schema(conn)
    anos = anos_dos_mandatos(carregar_mandatos())
    with httpx.Client(headers={"User-Agent": "finance_politics/0.1"}) as client:
        out = ingerir_legislativo(conn, anos, client, agora)
    print(f"leis: {out['leis']} | vetos: {out['vetos']}")


if __name__ == "__main__":  # pragma: no cover
    main()
