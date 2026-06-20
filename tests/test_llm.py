import json

from app.llm import ClaudeCodeClient, extrair_texto_json


def test_extrai_texto_do_envelope_claude():
    envelope = json.dumps({"type": "result", "result": '{"ok": true}'})
    assert extrair_texto_json(envelope) == '{"ok": true}'


def test_claude_code_client_usa_subprocess(monkeypatch):
    captured = {}

    class _CP:
        stdout = json.dumps({"type": "result", "result": '{"x": 1}'})
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _CP()

    monkeypatch.setattr("app.llm.subprocess.run", fake_run)
    out = ClaudeCodeClient().gerar("olá")
    assert out == '{"x": 1}'
    assert "claude" in captured["cmd"][0]
    assert "-p" in captured["cmd"]
