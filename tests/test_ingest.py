import datetime

from app.db import conectar, criar_schema, observacoes_da_serie
from app.ingest import fetch_com_retry, ingerir_indicador
from app.models import Indicador, Observacao


def _ind() -> Indicador:
    return Indicador(
        id="bcb_432_selic", fonte="BCB", codigo_fonte="432", nome="Meta Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro", metodo_anual="fim_periodo",
    )


class _FlakyFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, ind, client):
        self.calls += 1
        if self.calls < 2:
            raise RuntimeError("API instável")
        return [Observacao(serie_id=ind.id, data=datetime.date(2024, 1, 1), valor=11.75)]


class _DeadFetcher:
    def fetch(self, ind, client):
        raise RuntimeError("fonte fora do ar")


def test_retry_eventually_succeeds(monkeypatch):
    monkeypatch.setattr("app.ingest.time.sleep", lambda _s: None)
    obs = fetch_com_retry(_FlakyFetcher(), _ind(), client=None, tentativas=3)
    assert len(obs) == 1


def test_ingerir_indicador_logs_failure_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr("app.ingest.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.ingest.FETCHERS", {"BCB": _DeadFetcher()})
    conn = conectar(":memory:")
    criar_schema(conn)
    n = ingerir_indicador(conn, _ind(), client=None, agora="2026-06-20T00:00:00")
    assert n == 0
    log = conn.execute("SELECT status FROM ingestao_log").fetchall()
    assert log and log[0][0] == "erro"


def test_ingerir_indicador_success_persists(monkeypatch, tmp_path):
    monkeypatch.setattr("app.ingest.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.ingest.FETCHERS", {"BCB": _FlakyFetcher()})
    monkeypatch.setattr("app.ingest.salvar_raw", lambda *a, **k: str(tmp_path / "r.json"))
    conn = conectar(":memory:")
    criar_schema(conn)
    n = ingerir_indicador(conn, _ind(), client=None, agora="2026-06-20T00:00:00")
    assert n == 1
    assert len(observacoes_da_serie(conn, "bcb_432_selic")) == 1
