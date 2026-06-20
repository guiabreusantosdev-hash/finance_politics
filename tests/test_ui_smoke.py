import datetime

from app.models import Observacao
from app.ui import grafico_serie, serie_para_df


def _obs():
    return [
        Observacao(serie_id="s", data=datetime.date(2024, 1, 1), valor=10.0),
        Observacao(serie_id="s", data=datetime.date(2024, 2, 1), valor=11.0),
    ]


def test_serie_para_df_tem_colunas():
    df = serie_para_df(_obs())
    assert list(df.columns) == ["data", "valor"]
    assert len(df) == 2


def test_grafico_serie_tem_titulo_com_fonte_e_unidade():
    fig = grafico_serie(_obs(), titulo="Selic", unidade="% a.a.", fonte="BCB")
    titulo: str = fig.to_dict()["layout"]["title"]["text"]
    assert "Selic" in titulo
    assert "BCB" in titulo
    assert "% a.a." in titulo
