# Spec — Camada Legislativa (Spec 2)

> Segunda camada do app de análise de governos (BR). O Spec 1 (Núcleo Econômico) cobre
> indicadores econômicos/fiscais/sociais. Este spec adiciona a dimensão **legislativa**:
> as **leis sancionadas** e os **vetos presidenciais** de cada mandato presidencial.

## Job To Be Done

Como pesquisador analisando governos brasileiros, quero ver, por mandato presidencial,
as **leis sancionadas** (Leis Ordinárias, Complementares, Medidas Provisórias e Emendas
Constitucionais) e os **vetos** do período — tanto como **agregados + resumo factual**
quanto como **lista detalhada navegável** —, para avaliar a produção legislativa de cada
governo sem montar planilhas e sem risco de alucinação numérica.

## Vocabulário (correção conceitual)

No Brasil o presidente não "aprova" leis: o **Congresso aprova** e o presidente
**sanciona** (vira lei) **ou veta** (total/parcial). Logo:
- **Lei sancionada** = norma que completou o processo e foi sancionada no período do mandato.
- **Veto** = veto presidencial (total ou parcial) registrado no período.
- **Emenda Constitucional (EC)** é **promulgada pelo Congresso**, não sancionada pelo
  presidente. Entra no escopo por decisão do usuário, mas é marcada por `tipo` distinto e o
  resumo deve registrar essa diferença (não atribuir EC à "sanção presidencial").

## Princípio inegociável (herdado do Spec 1)

**O LLM nunca calcula números.** O backend conta tudo (leis por tipo, por tema, vetos) e
entrega ao modelo um payload estruturado; o modelo apenas **redige** o texto factual,
citando os valores recebidos. Todo número no texto tem que existir no payload.

---

## Decisões (do brainstorming)

| Tema | Decisão |
|---|---|
| Resultado | **Ambos**: agregados + resumo factual **e** lista detalhada navegável. |
| Tipos de norma | Lei Ordinária (LO), Lei Complementar (LC), Medida Provisória (MP), Emenda Constitucional (EC). |
| Quebra por tema | **Sim** — usar a classificação temática da Câmara. |
| Fonte de dados | **Abordagem A**: arquivos anuais da Câmara + endpoint de vetos do Senado/Congresso. |
| Cobertura | Câmara cobre proposições de 2001+; mandato mais antigo é Lula 1 (2003) → todos os 6 mandatos cobertos. |

## Arquitetura

Subsistema legislativo **paralelo** ao econômico, reusando o mesmo padrão em camadas, mas
com **tabelas relacionais/de evento** em vez de série temporal:

```
APIs (Câmara v2 / Senado-Congresso)
        │
        ▼
[1] Ingestão legislativa  ──grava JSON bruto──▶  raw/
        │  normaliza
        ▼
[2] SQLite: leis │ vetos │ lei_temas
        │
        ▼
[3] Agregação (determinística, pura): contagens por mandato / tipo / tema
        │
        ▼
[4] Payload builder → PayloadLegislativoMandato (DTO Pydantic)
        │
        ▼
[5] IA: payload → ResumoFactual (validado pelo guard + juiz já existentes)
        │
        ▼
[6] UI (Streamlit): aba "Legislativo" — KPIs, gráficos, tabela navegável, resumo
```

Disparo da ingestão: `python -m app.ingest_legislativo` (separado da ingestão econômica
`python -m app.ingest`, para que uma não derrube a outra). Agendamento fora de escopo.

---

## Componentes e decisões

### [1] Ingestão legislativa

Dois fetchers novos, cada um isolado por fonte:

- **`fetch_camara_leis`** — usa os **arquivos anuais** da Câmara:
  - Proposições: `https://dadosabertos.camara.leg.br/arquivos/proposicoes/json/proposicoes-{ano}.json`
  - Temas:       `https://dadosabertos.camara.leg.br/arquivos/proposicoesTemas/json/proposicoesTemas-{ano}.json`
  - Filtra proposições cujo `ultimoStatus`/situação indica **"Transformada em Norma Jurídica"**.
  - Mapeia `siglaTipo` → `tipo`: `PL`→`LO`, `PLP`→`LC`, `MPV`→`MP`, `PEC`→`EC`.
  - Extrai número/ano da norma, data, ementa, URL; junta os temas pelo id da proposição.
- **`fetch_senado_vetos`** — usa o conjunto **"Vetos do Congresso Nacional"** do Dados
  Abertos do Senado (base `https://legis.senado.leg.br/dadosabertos/`), por ano. Extrai
  data, tipo (total/parcial), descrição, matéria relacionada, URL.

Resiliência (herdada do Spec 1): retry com backoff + timeout; fonte fora do ar → usa o
último `raw/`; uma série/ano quebrado não derruba o pipeline. **JSON bruto gravado em
`raw/<fonte>/<conjunto>_{ano}_<timestamp>.json` antes de normalizar.** Idempotência por
chave primária (upsert).

> **Nota de implementação:** os caminhos/campos exatos das duas fontes serão confirmados
> contra a API ao vivo numa tarefa de verificação inicial do plano (os conjuntos existem e
> estão documentados; o formato exato de cada registro é validado na ingestão via fixtures
> reais reduzidas). A confirmação NÃO altera o escopo deste spec.

### [2] Armazenamento — esquema SQLite

```sql
CREATE TABLE IF NOT EXISTS leis (
    id      TEXT PRIMARY KEY,   -- ex.: "camara_2150394" (id da proposição de origem)
    tipo    TEXT,               -- LO | LC | MP | EC
    numero  TEXT,               -- número da norma
    ano     INTEGER,            -- ano da norma
    data    TEXT,               -- data da sanção/norma (ISO yyyy-mm-dd)
    ementa  TEXT,
    url     TEXT
);
CREATE TABLE IF NOT EXISTS vetos (
    id        TEXT PRIMARY KEY, -- id do veto na fonte
    data      TEXT,             -- data do veto (ISO)
    tipo      TEXT,             -- total | parcial
    descricao TEXT,
    materia   TEXT,             -- norma/projeto relacionado
    url       TEXT
);
CREATE TABLE IF NOT EXISTS lei_temas (
    lei_id TEXT,
    tema   TEXT,
    PRIMARY KEY (lei_id, tema),
    FOREIGN KEY (lei_id) REFERENCES leis(id)
);
```

**Atribuição ao mandato:** uma lei/veto pertence ao mandato cujo intervalo
`[inicio, fim]` (de `config/mandatos.yaml`) contém sua `data`. Sem heurística extra.

### [3] Agregação (determinística, pura — `app/legislativo.py`)

- `leis_no_mandato(conn, mandato) -> list[Lei]` — leis com `data` dentro do mandato.
- `vetos_no_mandato(conn, mandato) -> list[Veto]` — vetos com `data` dentro do mandato.
- `temas_de(conn, lei_id) -> list[str]`.
- `agregar_por_tipo(leis) -> dict[str, int]` — `{LO: n, LC: n, MP: n, EC: n}`.
- `agregar_por_tema(conn, leis) -> dict[str, int]` — contagem por tema.

### [4] Payload builder

DTO novo em `app/models.py`:

```python
class PayloadLegislativoMandato(BaseModel):
    mandato: str
    ano_inicio: int
    ano_fim: int
    total_leis: int
    por_tipo: dict[str, int]      # {LO, LC, MP, EC}
    por_tema: dict[str, int]      # {saúde: n, educação: n, ...}
    total_vetos: int
    vetos_por_tipo: dict[str, int]  # {total: n, parcial: n}
```

`construir_payload_legislativo(conn, mandato) -> PayloadLegislativoMandato` em
`app/payload.py`.

### [5] Camada de IA

- Prompt legislativo factual novo (em `app/resumo.py` ou módulo irmão): mesmas regras do
  Spec 1 (usar só os números do payload; citar fonte; tom neutro; sem juízo de valor; sem
  causação especulativa; registrar que EC é promulgada pelo Congresso). Saída no schema
  `ResumoFactual` já existente (`paragrafos_por_eixo` + `afirmacoes`); aqui os "eixos" são
  seções legislativas (ex.: `producao`, `vetos`, `temas`).
- O guard de factualidade e o LLM-as-judge existentes são reutilizados.
- **Persistência de resumos** (cache + histórico, do spec `2026-06-21-persistencia-resumos`)
  é reutilizada: `descrever_payload` ganha o caso `PayloadLegislativoMandato`
  → `("legislativo", payload.mandato)`.

### [6] UI (Streamlit)

Aba nova **"Legislativo"** em `app/ui.py`:
- Seletor de mandato (de `mandatos.yaml`).
- **KPIs**: total de leis sancionadas, total por tipo, total de vetos.
- **Gráficos** (Plotly): barras por tipo e por tema.
- **Tabela navegável/filtrável** das leis (tipo, número, data, ementa, link) e dos vetos.
- Botão **"Gerar resumo"** com o fluxo de cache/histórico já planejado.

A `main()`/helpers da UI seguem `# pragma: no cover` (smoke manual), como no Spec 1.

---

## Modelo de dados (DTOs de leitura)

```python
class Lei(BaseModel):
    id: str
    tipo: str            # LO | LC | MP | EC
    numero: str
    ano: int
    data: datetime.date
    ementa: str
    url: str

class Veto(BaseModel):
    id: str
    data: datetime.date
    tipo: str            # total | parcial
    descricao: str
    materia: str
    url: str
```

## Tratamento de erros

- Ano/arquivo de uma fonte indisponível → registra no `ingestao_log`, usa o último `raw/`
  se houver, e segue para o próximo ano/fonte (um ano quebrado não derruba o pipeline).
- Proposição sem temas → entra em `leis` sem linhas em `lei_temas` (contada em "sem tema").
- Geração de resumo falha após N tentativas → UI mostra o erro; nada é salvo (igual Spec 1).
- Juiz falha → resumo é salvo mesmo assim com `veredito = None` (não-fatal, igual Spec 1).

## Plano de testes (sem rede)

- **Fetchers** (`fetch_camara_leis`, `fetch_senado_vetos`): HTTP mockado com **fixtures de
  JSON real reduzido**; valida normalização (mapeamento de tipo, extração de data/ementa,
  filtro "Transformada em Norma Jurídica", junção de temas).
- **Storage** (`app/db.py`): upsert idempotente de `leis`/`vetos`/`lei_temas`; leitura.
- **Agregação** (`app/legislativo.py`): atribuição por data (lei na borda do mandato),
  `agregar_por_tipo`, `agregar_por_tema`, `vetos_no_mandato`.
- **Payload** (`construir_payload_legislativo`): monta totais corretos a partir do banco.
- **Persistência de resumo**: `descrever_payload(PayloadLegislativoMandato)` →
  `("legislativo", mandato)`.

`LLMClient` e HTTP sempre mockados; zero rede nos testes.

## Fora de escopo (YAGNI)

- Votações nominais, autoria parlamentar, presença/atuação de deputados/senadores
  (camada de candidato/parlamentar — spec futuro).
- Dados eleitorais / TSE.
- Tramitação completa de cada proposição.
- Cruzar veto ↔ lei resultante (mantido como campos textuais `materia`, sem join formal).
- Agendamento/cron da ingestão.
