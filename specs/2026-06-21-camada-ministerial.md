# Spec — Camada Ministerial (Spec 3)

> Terceira camada do app de análise de governos (BR). Spec 1 = Núcleo Econômico
> (indicadores). Spec 2 = Legislativo (leis sancionadas + vetos). Este spec adiciona a
> dimensão **ministerial**: os **principais ministros** de cada governo e suas
> **principais medidas**, para análise.

## Job To Be Done

Como pesquisador analisando governos brasileiros, quero ver, por governo, os **principais
ministros** (por pasta, com período e fonte) e suas **principais medidas** — como
**visualização navegável** e como **resumo factual por governo** —, para avaliar a atuação
de cada gestão. As medidas são **curadas e verificadas por mim**; a IA pode acelerar a
curadoria rascunhando medidas com fonte, mas nada vira "fato" sem minha aprovação.

## Tensão de design e princípio inegociável

Ao contrário das camadas econômica e legislativa (que puxam APIs oficiais estruturadas),
**não existe API pública das "principais medidas" de cada ministro** — esse dado é
editorial. Para preservar o princípio do app (**o LLM nunca apresenta fato/número não
verificado**), esta camada usa um **workflow de curadoria com aprovação humana**:

1. Todo rascunho de medida exige `fonte_url`.
2. Um rascunho **nunca** aparece como fato na visualização nem entra em nenhum resumo
   enquanto não for **aprovado** pelo usuário.
3. O resumo factual por governo usa **apenas medidas aprovadas**.
4. ⚠️ Modelos podem alucinar citações: o usuário **deve conferir o link da fonte** antes de
   aprovar uma medida rascunhada pela IA.

Os **ministros** são dado factual estático; vêm de um YAML curado (não há API oficial limpa
com o histórico de ministros). As **medidas** são editáveis/aprováveis e vivem no SQLite.

---

## Decisões (do brainstorming)

| Tema | Decisão |
|---|---|
| Fonte das medidas | **Híbrido**: ministros de fonte factual (YAML); medidas curadas pelo usuário, com assistente de rascunho por IA (aprovação humana). |
| Fonte dos ministros | YAML curado (`config/ministros.yaml`), semeável a partir da Wikipédia. |
| Pastas | **Ampliado (~8)**: Fazenda/Economia, Casa Civil, Planejamento, Banco Central, Saúde, Educação, Justiça, Infraestrutura — conjunto-semente, dirigido pelo YAML. |
| Resultado | **Visualização navegável + resumo factual** por governo. |
| Assistente de rascunho por IA | **Incluído no v1.** |

## Arquitetura

Terceira camada, mesmo padrão em camadas das anteriores, mas **sem fetcher de API externa**:

```
config/ministros.yaml (ministros, factual)        LLM (rascunho de medidas, opcional)
        │                                                  │
        ▼                                                  ▼
[1] Domínio: carrega ministros            +    medidas (SQLite): rascunho → aprovada
        │
        ▼
[2] Agregação: ministros + medidas APROVADAS por governo/pasta
        │
        ▼
[3] Payload builder → PayloadMinisterialGoverno (DTO Pydantic)
        │
        ▼
[4] IA: payload → ResumoFactual (guard + juiz existentes; só medidas aprovadas)
        │
        ▼
[5] UI (Streamlit): aba "Ministros" — tabela, medidas, assistente de rascunho, resumo
```

---

## Componentes e decisões

### [0] Config de ministros — `config/ministros.yaml`

```yaml
- governo: "Lula 3"          # DEVE casar com um 'nome' de config/mandatos.yaml
  ministros:
    - pasta: "Fazenda"
      nome: "Fernando Haddad"
      inicio: 2023-01-01
      fim: null              # null = até o fim do mandato do governo
      fonte: "https://pt.wikipedia.org/wiki/..."
```
- Vários ministros na mesma pasta ao longo do tempo são permitidos (entradas repetidas de
  pasta com `inicio`/`fim` distintos).
- `governo` precisa existir em `config/mandatos.yaml` (validado na carga).
- Loader segue o padrão de `app/config_loader.py` (já existe para indicadores/mandatos).

### [1] Domínio — `app/ministros.py`

- `carregar_ministros(path="config/ministros.yaml") -> list[Ministro]`
  - valida que cada `governo` existe em `mandatos.yaml`; erro claro se não.
- `ministros_do_governo(ministros, governo) -> list[Ministro]`
- CRUD de medidas no SQLite:
  - `salvar_medida(conn, medida) -> int` (insere; retorna id)
  - `medidas_do_governo(conn, governo, *, apenas_aprovadas=False) -> list[Medida]`
  - `aprovar_medida(conn, medida_id) -> None` (status → "aprovada")
  - `editar_medida(conn, medida_id, *, titulo, descricao, fonte_url) -> None`
  - `descartar_medida(conn, medida_id) -> None` (remove rascunho)

### [2] Assistente IA — `app/medidas_ia.py`

- `rascunhar_medidas(client: LLMClient, ministro: Ministro, n: int = 3) -> list[Medida]`
  - prompt: "liste até N principais medidas/políticas deste ministro; para CADA uma forneça
    título curto, descrição factual e uma `fonte_url` verificável; NÃO invente fontes; se não
    houver fonte confiável, omita a medida". Saída JSON validada por Pydantic.
  - cada `Medida` retorna com `status="rascunho"`, `origem="ia"`; **não** é salva
    automaticamente — a UI mostra para edição/aprovação e só então chama `salvar_medida`.

### [3] Storage — tabela nova `medidas` (em `app/db.py`)

```sql
CREATE TABLE IF NOT EXISTS medidas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    governo   TEXT,
    pasta     TEXT,
    ministro  TEXT,
    titulo    TEXT,
    descricao TEXT,
    fonte_url TEXT,
    status    TEXT,   -- 'rascunho' | 'aprovada'
    origem    TEXT,   -- 'curada' | 'ia'
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_medidas_governo ON medidas (governo, status);
```
Ministros NÃO são persistidos (ficam no YAML); só medidas.

### [4] Payload builder — `app/payload.py`

DTO novo em `app/models.py`:

```python
class MedidaResumo(BaseModel):
    pasta: str
    ministro: str
    titulo: str
    descricao: str
    fonte_url: str

class PayloadMinisterialGoverno(BaseModel):
    governo: str
    ano_inicio: int
    ano_fim: int
    ministros: list[str]                 # "pasta — nome" por ministro do governo
    medidas: list[MedidaResumo]          # SOMENTE medidas aprovadas
```

`construir_payload_ministerial(conn, ministros, governo) -> PayloadMinisterialGoverno`.
**Garantia:** o builder filtra `status="aprovada"`; rascunhos nunca entram no payload.

### [5] Camada de IA — resumo

- Prompt factual novo (em `app/resumo.py` ou módulo irmão): mesmas regras (use só o que está
  no payload; cite a `fonte_url`; tom neutro; sem juízo de valor; sem causação especulativa).
  Saída no schema `ResumoFactual` existente (eixos = seções por pasta/área).
- Guard de factualidade e LLM-as-judge existentes são reutilizados.
- **Persistência de resumos** (cache + histórico, do spec `2026-06-21-persistencia-resumos`):
  `descrever_payload` ganha o caso `PayloadMinisterialGoverno` → `("ministerial", governo)`.

### [6] UI (Streamlit) — aba "Ministros"

- Seletor de governo (de `mandatos.yaml`).
- **Tabela de ministros**: pasta, nome, período, fonte (link).
- **Medidas aprovadas** agrupadas por pasta (título, descrição, link da fonte).
- Por ministro: botão **"Sugerir medidas (IA)"** → chama `rascunhar_medidas`; mostra os
  rascunhos em campos **editáveis** com botões **Aprovar** (→ `salvar_medida` + aprovar) e
  **Descartar**. Rascunhos aparecem visualmente marcados como "não verificado".
- Entrada **manual** de medida curada (formulário: pasta, ministro, título, descrição, fonte).
- Botão **"Gerar resumo do governo"** com o fluxo de cache/histórico já planejado.

`main()`/helpers da UI seguem `# pragma: no cover` (smoke manual), como nas outras camadas.

---

## Modelo de dados (DTOs)

```python
class Ministro(BaseModel):
    governo: str
    pasta: str
    nome: str
    inicio: datetime.date
    fim: datetime.date | None
    fonte: str

class Medida(BaseModel):
    id: int | None = None        # None antes de salvar
    governo: str
    pasta: str
    ministro: str
    titulo: str
    descricao: str
    fonte_url: str
    status: str                  # 'rascunho' | 'aprovada'
    origem: str                  # 'curada' | 'ia'
    criado_em: str | None = None
```

## Tratamento de erros

- `ministros.yaml` com `governo` inexistente em `mandatos.yaml` → erro de carga explícito.
- `rascunhar_medidas`: resposta da IA inválida (JSON/schema) → erro tratado; a UI mostra
  "não foi possível sugerir medidas" e não salva nada.
- Medida da IA sem `fonte_url` → descartada na validação (não vira rascunho).
- Geração de resumo falha após N tentativas → UI mostra erro; nada salvo (igual Spec 1/2).
- Juiz falha → resumo salvo com `veredito = None` (não-fatal).

## Plano de testes (sem rede)

- **Loader** (`carregar_ministros`): lê YAML válido; rejeita `governo` fora de `mandatos.yaml`.
- **Storage/CRUD** (`app/db.py` + `app/ministros.py`): `salvar_medida`,
  `medidas_do_governo` (com/sem filtro de aprovadas), `aprovar_medida`, `editar_medida`,
  `descartar_medida`.
- **Assistente IA** (`rascunhar_medidas`): LLM **mockado** retornando JSON de medidas com
  fonte → vira lista de `Medida(status="rascunho", origem="ia")`; medida sem `fonte_url` é
  descartada.
- **Payload** (`construir_payload_ministerial`): inclui SOMENTE medidas aprovadas
  (rascunho no banco NÃO aparece no payload).
- **Persistência de resumo**: `descrever_payload(PayloadMinisterialGoverno)` →
  `("ministerial", governo)`.

`LLMClient` sempre mockado; zero rede nos testes.

## Fora de escopo (YAGNI)

- Scraping automático da lista de ministros (curadoria manual no YAML).
- Biografia / dados pessoais / patrimônio de ministros.
- Votações, indicações, CPIs.
- Cruzar medida ↔ indicador econômico/legislativo.
- Histórico de edições de uma medida além do campo `status`.
- Internacionalização / múltiplos países.
