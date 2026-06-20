"""Ingestion orchestration: retry/backoff, raw persistence, upsert, logging."""
from __future__ import annotations

import datetime
import json
import pathlib
import time

import httpx

from app.config_loader import carregar_indicadores
from app.db import (
    conectar,
    criar_schema,
    registrar_ingestao,
    upsert_observacoes,
    upsert_serie,
)
from typing import Any

from app.fetchers.base import Fetcher
from app.fetchers.bcb import BCBFetcher
from app.fetchers.ipea import IPEAFetcher
from app.fetchers.sidra import SIDRAFetcher
from app.fetchers.tesouro import TesouroFetcher
from app.models import Indicador, Observacao

FETCHERS: dict[str, Fetcher] = {
    "BCB": BCBFetcher(),
    "IBGE": SIDRAFetcher(),
    "IPEA": IPEAFetcher(),
    "TESOURO": TesouroFetcher(),
}


def salvar_raw(fonte: str, serie_id: str, payload: object, agora: str, base: str = "raw") -> str:
    pasta = pathlib.Path(base) / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{serie_id}_{agora.replace(':', '-')}.json"
    caminho.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return str(caminho)


def fetch_com_retry(
    fetcher: Fetcher, ind: Indicador, client: httpx.Client | None, tentativas: int = 3
) -> tuple[Any, list[Observacao]]:
    erro: Exception | None = None
    for i in range(tentativas):
        try:
            return fetcher.fetch(ind, client)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - APIs públicas instáveis, tentar de novo
            erro = exc
            time.sleep(2**i)
    raise erro if erro else RuntimeError("falha desconhecida")


def ingerir_indicador(
    conn, ind: Indicador, client: httpx.Client | None, agora: str
) -> int:
    upsert_serie(conn, ind)
    try:
        fetcher = FETCHERS[ind.fonte]
        raw, obs = fetch_com_retry(fetcher, ind, client)
    except Exception as exc:  # noqa: BLE001 - registra falha e segue, não derruba o pipeline
        registrar_ingestao(conn, ind.id, agora, "erro", 0, str(exc))
        return 0
    salvar_raw(ind.fonte, ind.id, raw, agora)
    n = upsert_observacoes(conn, obs)
    registrar_ingestao(conn, ind.id, agora, "ok", n, None)
    return n


def main() -> None:
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    conn = conectar()
    criar_schema(conn)
    with httpx.Client(headers={"User-Agent": "finance_politics/0.1"}) as client:
        for ind in carregar_indicadores():
            n = ingerir_indicador(conn, ind, client, agora)
            print(f"{ind.id}: {n} observações")


if __name__ == "__main__":
    main()
