# Notas das fontes legislativas (spike — confirmado ao vivo em 2026-06-21)

Verificado contra as APIs reais. **Estes nomes de campo são a fonte da verdade** para os
fetchers das Tasks 3/4 — onde divergirem do código de exemplo do plano, **vale esta nota**.

## Câmara — leis sancionadas (arquivos anuais)

- Proposições: `https://dadosabertos.camara.leg.br/arquivos/proposicoes/json/proposicoes-{ano}.json`
  (~95 MB/ano; array em chave `dados`).
- Temas: `https://dadosabertos.camara.leg.br/arquivos/proposicoesTemas/json/proposicoesTemas-{ano}.json`
  (~6 MB/ano; array em chave `dados`).

### Registro de proposição (campos usados)
- `id` (int), `siglaTipo` (str), `numero` (int), `ano` (int), `ementa` (str), `uri` (str),
  `dataApresentacao` (ISO).
- `ultimoStatus`: objeto com `data` (ISO, ex. `"2025-10-03T00:00:00"`) e `descricaoSituacao` (str).

### ⚠️ Indicador de "virou lei" — CORREÇÃO do plano
- O valor real é **`"Transformado em Norma Jurídica"`** (masculino "Transformad**o**").
  O plano escreveu "Transformad**a**" — **errado**. Filtrar por
  `descricaoSituacao == "Transformado em Norma Jurídica"` (recomendo comparação
  case-insensitive por substring "transformado em norma").
- Em 2023 há 329 proposições com esse status.

### ⚠️ Campo de data — CORREÇÃO do plano
- A data do status fica em `ultimoStatus["data"]` (NÃO `dataHora`, que não existe).
  Use `ultimoStatus.get("data")` e caia para `dataApresentacao` se ausente.

### Mapa de tipos (siglaTipo → tipo)
- `PL`→`LO`, `PLP`→`LC`, `MPV`→`MP`, `PEC`→`EC`. Demais tipos transformados existem
  (PDL, PRC, PLV, REQ, PLN…) e **devem ser descartados** (não estão no escopo).

### Registro de tema (campos usados)
- `uriProposicao` (str — **não existe `idProposicao`**), `siglaTipo`, `numero`, `ano`,
  `codTema` (int), `tema` (str).
- Casar com a proposição pelo id no fim de `uriProposicao` (último segmento da URL).

## Senado/Congresso — vetos

- Canônico: `https://legis.senado.leg.br/dadosabertos/materia/vetos/{ano}` → **redireciona** para
  `https://legis.senado.leg.br/dadosabertos/dados/ListaVetosAnoCN{ano}.json` (use a URL direta;
  ~117 KB/ano). Mande header `Accept: application/json`.
- Caminho do array: `ListaVetosAnoCN` → `Vetos` → `Veto` (lista). Em 2023: 49 vetos.

### Registro de veto (campos usados)
- `Codigo` (str) → id `"senado_{Codigo}"`.
- `Total` (str): `"Sim"` = veto **total**; `"Não"` = veto **parcial**.
- `DataRecebimentoCongresso` (ISO `yyyy-mm-dd`) → **data para atribuição ao mandato**
  (fallback `DataPublicacao`).
- `Assunto` (str curto) → `descricao` (fallback `Materia.Ementa`).
- `Materia`: `{Sigla:"VET", Numero, Ano, Ementa, UrlMovimentacoes}`.
- `MateriaVetada`: `{Sigla, Numero, Ano, NormaGerada:{NomeNorma, DataAssinatura, ...}}`
  → `materia` = `f"{MateriaVetada.Sigla} {MateriaVetada.Numero}/{MateriaVetada.Ano}"`
  (fallback `MateriaVetada.NormaGerada.NomeNorma`).
- `url` = `Materia.UrlMovimentacoes` (fallback string vazia).

## Fixtures congeladas (em `tests/fixtures/legislativo/`)
- `camara_proposicoes_2023.json` — 11 proposições: 9 "Transformado em Norma Jurídica"
  (PL, PLP, MPV, PEC + PDL/PRC/PLV/REQ/PLN não-mapeados, que devem ser filtrados) + 2 não-transformadas.
- `camara_temas_2023.json` — 17 temas casando com as proposições da fixture.
- `senado_vetos_2023.json` — 4 vetos reais (estrutura ListaVetosAnoCN.Vetos.Veto preservada).
