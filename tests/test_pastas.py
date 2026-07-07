def test_carregar_pastas_cobre_as_oito_pastas():
    from app.pastas import carregar_pastas

    pastas = carregar_pastas()
    esperadas = {
        "Casa Civil", "Fazenda", "Economia", "Educação", "Justiça",
        "Justiça e Segurança Pública", "Relações Exteriores", "Secretaria-Geral",
    }
    assert esperadas <= set(pastas.keys())
    assert all(isinstance(v, str) and v.strip() for v in pastas.values())


def test_carregar_pastas_retorna_dict():
    from app.pastas import carregar_pastas

    pastas = carregar_pastas()
    assert isinstance(pastas, dict)
    assert "coordena" in pastas["Casa Civil"].lower()
