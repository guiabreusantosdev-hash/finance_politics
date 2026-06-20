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
