"""Fetcher protocol shared by all source adapters."""
from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.models import Indicador, Observacao


class Fetcher(Protocol):
    def fetch(self, ind: Indicador, client: httpx.Client) -> tuple[Any, list[Observacao]]: ...
