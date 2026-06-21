"""Camada ministerial: carrega ministros (YAML) e helpers de governo."""
from __future__ import annotations

import yaml

from app.models import Mandato, Ministro


def carregar_ministros(
    path: str = "config/ministros.yaml",
    mandatos_path: str = "config/mandatos.yaml",
) -> list[Ministro]:
    with open(mandatos_path, encoding="utf-8") as fh:
        mandatos = [Mandato.model_validate(m) for m in yaml.safe_load(fh)]
    nomes_validos = {m.nome for m in mandatos}

    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []

    ministros: list[Ministro] = []
    for bloco in raw:
        governo = bloco["governo"]
        if governo not in nomes_validos:
            raise ValueError(
                f"governo '{governo}' em {path} não existe em {mandatos_path}"
            )
        for item in bloco.get("ministros", []):
            ministros.append(Ministro.model_validate({**item, "governo": governo}))
    return ministros


def ministros_do_governo(
    ministros: list[Ministro], governo: str
) -> list[Ministro]:
    return [m for m in ministros if m.governo == governo]
