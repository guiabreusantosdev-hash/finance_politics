from app.config_loader import carregar_indicadores, carregar_mandatos


def test_carrega_indicadores_reais():
    inds = carregar_indicadores()
    assert len(inds) >= 8
    ids = {i.id for i in inds}
    assert "bcb_432_selic" in ids
    assert all(i.eixo in {"macro", "fiscal", "social"} for i in inds)


def test_carrega_mandatos_reais():
    mandatos = carregar_mandatos()
    nomes = {m.nome for m in mandatos}
    assert {"Lula 1", "Bolsonaro", "Lula 3"} <= nomes
    for m in mandatos:
        assert m.inicio < m.fim


def test_indicador_aceita_variavel_e_classificacao_opcionais():
    from app.models import Indicador

    ind = Indicador(
        id="x", fonte="IBGE", codigo_fonte="6784", nome="PIB",
        unidade="%", periodicidade="anual", eixo="macro",
        metodo_anual="fim_periodo", variavel="9808", classificacao="c11255/90707",
    )
    assert ind.variavel == "9808"
    assert ind.classificacao == "c11255/90707"

    ind2 = Indicador(
        id="y", fonte="BCB", codigo_fonte="432", nome="Selic",
        unidade="% a.a.", periodicidade="mensal", eixo="macro",
        metodo_anual="fim_periodo",
    )
    assert ind2.variavel is None
    assert ind2.classificacao is None
