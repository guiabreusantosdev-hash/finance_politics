"""Load and validate the indicator and mandate registries."""
from __future__ import annotations

import yaml

from app.models import Indicador, Mandato


def carregar_indicadores(path: str = "config/indicadores.yaml") -> list[Indicador]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return [Indicador.model_validate(item) for item in raw]


def carregar_mandatos(path: str = "config/mandatos.yaml") -> list[Mandato]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return [Mandato.model_validate(item) for item in raw]
