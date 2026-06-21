import datetime

from app.db import conectar, criar_schema, leis_entre, temas_de, vetos_entre
from app.ingest_legislativo import anos_dos_mandatos, ingerir_legislativo
from app.models import Lei, Mandato, Veto


def test_anos_dos_mandatos():
    ms = [
        Mandato(nome="A", inicio=datetime.date(2003, 1, 1), fim=datetime.date(2004, 12, 31)),
    ]
    assert anos_dos_mandatos(ms) == [2003, 2004]


class _CamaraFake:
    def fetch(self, ano, client):
        lei = Lei(id=f"camara_{ano}", tipo="LO", numero="1", ano=ano,
                  data=datetime.date(ano, 6, 1), ementa="e", url="u")
        return {"raw": ano}, [lei], {f"camara_{ano}": ["Saúde"]}


class _VetosFake:
    def fetch(self, ano, client):
        v = Veto(id=f"senado_{ano}", data=datetime.date(ano, 7, 1), tipo="parcial",
                 descricao="d", materia="m", url="u")
        return {"raw": ano}, [v]


class _CamaraRaising:
    def fetch(self, ano, client):
        raise RuntimeError("network error")


def test_ingerir_legislativo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # raw/ vai para o tmp
    conn = conectar(":memory:")
    criar_schema(conn)
    agora = "2026-06-21T10:00:00"
    out = ingerir_legislativo(conn, [2023], None, agora,
                              camara=_CamaraFake(), vetos=_VetosFake())
    assert out == {"leis": 1, "vetos": 1}
    assert temas_de(conn, "camara_2023") == ["Saúde"]
    assert len(leis_entre(conn, datetime.date(2023, 1, 1), datetime.date(2023, 12, 31))) == 1
    assert len(vetos_entre(conn, datetime.date(2023, 1, 1), datetime.date(2023, 12, 31))) == 1


def test_ingerir_legislativo_resiliente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = conectar(":memory:")
    criar_schema(conn)
    agora = "2026-06-21T10:00:00"
    out = ingerir_legislativo(conn, [2023], None, agora,
                              camara=_CamaraRaising(), vetos=_VetosFake())
    assert out == {"leis": 0, "vetos": 1}
    cur = conn.execute(
        "SELECT status FROM ingestao_log WHERE serie_id = 'camara_leis_2023'"
    )
    assert cur.fetchone()[0] == "erro"
