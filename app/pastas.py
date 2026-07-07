"""Load the ministry-portfolio descriptions registry."""
from __future__ import annotations

import yaml


def carregar_pastas(path: str = "config/pastas.yaml") -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)
