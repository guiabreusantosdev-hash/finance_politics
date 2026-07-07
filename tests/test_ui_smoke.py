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


def test_ui_importa_helpers_de_persistencia():
    import app.ui as ui

    src = __import__("inspect").getsource(ui)
    assert "buscar_resumo_cache" in src
    assert "salvar_resumo" in src
    assert "historico_resumos" in src


def test_ui_tem_aba_ministros():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "Ministros" in src
    assert "construir_payload_ministerial" in src
    assert "rascunhar_medidas" in src


def test_ui_tem_aba_legislativo():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "Legislativo" in src
    assert "construir_payload_legislativo" in src


def test_ui_aba_por_periodo_usa_slider_e_payload_periodo():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "Por período" in src
    assert "st.slider" in src
    assert "construir_payload_periodo" in src
    assert "observacoes_entre" in src


def test_grafico_barras_usa_bar_e_titulo():
    from app.ui import grafico_barras

    fig = grafico_barras(_obs(), titulo="PIB", unidade="%", fonte="IBGE")
    d = fig.to_dict()
    assert d["data"][0]["type"] == "bar"
    assert "PIB" in d["layout"]["title"]["text"]
    assert "IBGE" in d["layout"]["title"]["text"]


def test_ui_aba_por_periodo_usa_tipo_grafico_e_aviso_sem_dados():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "tipo_grafico" in src
    assert "grafico_barras" in src
    assert "sem dados no período" in src


def test_ui_legislativo_tem_legenda_e_filtros():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    # legenda dos tipos
    assert "Emenda Constitucional" in src
    assert "Lei Complementar" in src
    assert "Lei Ordinária" in src
    assert "Medida Provisória" in src
    # filtros e temas
    assert "filtrar_leis" in src
    assert "st.multiselect" in src
    assert "temas_de" in src


def test_grafico_comparacao_indicador_tem_duas_barras_e_titulo():
    from app.ui import grafico_comparacao_indicador

    fig = grafico_comparacao_indicador(
        "Meta Selic", "% a.a.", 13.75, 10.5, "Bolsonaro", "Lula 3"
    )
    d = fig.to_dict()
    assert d["data"][0]["type"] == "bar"
    assert list(d["data"][0]["y"]) == [13.75, 10.5]
    assert list(d["data"][0]["x"]) == ["Bolsonaro", "Lula 3"]
    assert "Meta Selic" in d["layout"]["title"]["text"]
    assert "% a.a." in d["layout"]["title"]["text"]


def test_ui_aba_comparacao_usa_grafico_por_indicador():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "grafico_comparacao_indicador" in src


def test_ui_ministros_tem_expander_pastas_e_msg_medidas():
    import inspect

    import app.ui as ui

    src = inspect.getsource(ui)
    assert "carregar_pastas" in src
    assert "O que faz cada pasta" in src
    # a mensagem de medidas vazias virou explicativa e cita o botao de IA
    assert "Sugerir medidas (IA)" in src
    assert "Nenhuma medida aprovada ainda" in src
