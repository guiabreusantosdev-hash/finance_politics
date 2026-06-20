"""LLM access behind a swappable interface, default = Claude Code subscription."""
from __future__ import annotations

import json
import subprocess
from typing import Protocol


class LLMClient(Protocol):
    def gerar(self, prompt: str) -> str: ...


def extrair_texto_json(stdout: str) -> str:
    """Pull the assistant result text out of `claude -p --output-format json`."""
    envelope = json.loads(stdout)
    if isinstance(envelope, dict) and "result" in envelope:
        return envelope["result"]
    return stdout


class ClaudeCodeClient:
    """Calls the local Claude Code CLI headless; auth = the user's subscription."""

    def __init__(self, modelo: str | None = None) -> None:
        self.modelo = modelo

    def gerar(self, prompt: str) -> str:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if self.modelo:
            cmd += ["--model", self.modelo]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if cp.returncode != 0:
            raise RuntimeError(f"claude -p falhou: {cp.stdout}")
        return extrair_texto_json(cp.stdout)
