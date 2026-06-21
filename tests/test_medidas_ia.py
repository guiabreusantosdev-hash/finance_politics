import datetime
import json

from app.medidas_ia import rascunhar_medidas
from app.models import Ministro


class _FakeClient:
    def __init__(self, resposta: str):
        self._r = resposta

    def gerar(self, prompt: str) -> str:
        return self._r


def _ministro() -> Ministro:
    return Ministro(governo="Lula 3", pasta="Fazenda", nome="Fernando Haddad",
                    inicio=datetime.date(2023, 1, 1), fim=None, fonte="x")


def test_rascunhar_medidas_monta_medidas_rascunho():
    resp = json.dumps({"medidas": [
        {"titulo": "Arcabouço fiscal", "descricao": "Nova regra fiscal",
         "fonte_url": "https://exemplo/lei"},
    ]})
    out = rascunhar_medidas(_FakeClient(resp), _ministro())
    assert len(out) == 1
    m = out[0]
    assert m.status == "rascunho" and m.origem == "ia"
    assert m.governo == "Lula 3" and m.pasta == "Fazenda"
    assert m.ministro == "Fernando Haddad"
    assert m.titulo == "Arcabouço fiscal"


def test_rascunhar_descarta_sem_fonte():
    resp = json.dumps({"medidas": [
        {"titulo": "Sem fonte", "descricao": "x", "fonte_url": ""},
        {"titulo": "Com fonte", "descricao": "y", "fonte_url": "https://ok"},
    ]})
    out = rascunhar_medidas(_FakeClient(resp), _ministro())
    assert [m.titulo for m in out] == ["Com fonte"]
