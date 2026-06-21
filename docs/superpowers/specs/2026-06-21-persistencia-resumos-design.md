# Spec — Persistência de resumos (cache + histórico)

> Feature pequena sobre o Núcleo Econômico (Spec 1, já concluído). Hoje os resumos
> gerados pela camada de IA são **efêmeros**: o `claude -p` é chamado no clique do
> botão, o texto é exibido na UI e some ao recarregar. Nada é gravado.

## Job To Be Done

Como pesquisador, quero que cada resumo factual gerado pela IA seja **gravado**, para
(a) não pagar/esperar uma nova chamada ao LLM quando os dados não mudaram (cache) e
(b) manter um **histórico auditável** de todas as versões geradas ao longo do tempo,
incluindo o veredito do juiz e o modelo usado.

## Decisões (do brainstorming)

- **Comportamento:** cache **+** histórico. Reusa o resumo em cache por padrão; um botão
  "Regerar" força nova chamada. Nunca sobrescreve — toda geração vira uma linha nova.
- **Chave do cache:** `sha256` do JSON canônico do payload (`payload.model_dump_json()`).
  Mesmos dados → mesmo hash → reusa. Reingestão que muda os dados → hash novo → regenera,
  e a versão antiga permanece no histórico.
- **Conteúdo de cada registro:** texto do resumo, veredito do juiz, payload completo e o
  modelo/versão do LLM.
- **UI:** ao abrir a aba, exibe o resumo em cache automaticamente (rótulo "✅ em cache");
  o botão vira "Regerar"; um `st.expander("Histórico")` lista versões anteriores.

## Princípio mantido

**O LLM nunca calcula números.** Esta feature só persiste o que já é gerado; não toca na
camada de cálculo nem no guard de factualidade.

---

## Esquema SQLite — nova tabela `resumos`

```sql
CREATE TABLE IF NOT EXISTS resumos (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo          TEXT,   -- 'ano' | 'mandato' | 'comparacao'
  identificador TEXT,   -- '2024' | 'Lula 3' | 'Lula 3 × Bolsonaro'
  payload_hash  TEXT,   -- sha256 do model_dump_json() do payload
  payload_json  TEXT,   -- payload completo (reprodutibilidade)
  resumo_json   TEXT,   -- ResumoFactual serializado
  veredito_json TEXT,   -- Veredito serializado (NULL se o juiz falhou/não rodou)
  modelo        TEXT,   -- 'claude-opus-4-8' ou 'claude-code-default'
  criado_em     TEXT    -- ISO timestamp
);
CREATE INDEX IF NOT EXISTS idx_resumos_lookup
  ON resumos (tipo, identificador, criado_em);
```

A tabela entra no `_SCHEMA` de `app/db.py` (criada por `criar_schema`, idempotente).

## Componentes e fronteiras

### `app/payload.py` — funções puras
- `hash_payload(payload) -> str`: `sha256` hex de `payload.model_dump_json()`. Determinístico
  para o mesmo payload; muda se qualquer valor mudar.
- `descrever_payload(payload) -> tuple[str, str]`: deriva `(tipo, identificador)`:
  - `PayloadAno` → `("ano", str(payload.ano))`
  - `PayloadMandato` → `("mandato", payload.mandato)`
  - `PayloadComparacao` → `("comparacao", f"{payload.mandato_a} × {payload.mandato_b}")`

### `app/models.py` — DTO de leitura
```python
class ResumoRegistro(BaseModel):
    id: int
    tipo: str
    identificador: str
    payload_hash: str
    resumo: ResumoFactual
    veredito: dict | None   # dict (não Veredito) p/ evitar import cíclico com judge.py
    modelo: str
    criado_em: str
```

### `app/db.py` — storage
- `salvar_resumo(conn, *, payload, resumo, veredito, modelo, criado_em=None) -> int`
  - deriva `tipo/identificador` via `descrever_payload` e `payload_hash` via `hash_payload`
  - `veredito`: aceita `Veredito | None`; serializa para `veredito_json` (ou NULL)
  - `criado_em=None` → usa `datetime.datetime.now().isoformat()`
  - retorna o `id` inserido
- `buscar_resumo_cache(conn, payload_hash) -> ResumoRegistro | None`
  - retorna o registro **mais recente** com aquele hash (ORDER BY criado_em DESC, id DESC LIMIT 1),
    ou `None` se não houver
- `historico_resumos(conn, tipo, identificador) -> list[ResumoRegistro]`
  - todos os registros daquele `(tipo, identificador)`, mais recente primeiro

### `app/ui.py` — fluxo (permanece `# pragma: no cover`, smoke manual)
Para cada aba (ano / mandato / comparação):
1. constrói o `payload` (como hoje) e calcula o hash.
2. `cache = buscar_resumo_cache(conn, hash)`. Se existir, exibe o resumo + "✅ em cache
   (gerado em <criado_em> · <modelo>)".
3. botão **"Regerar"** (ou "Gerar resumo" se não há cache): chama `gerar_resumo` + `julgar`,
   depois `salvar_resumo(...)`, e exibe o resultado.
4. `st.expander("Histórico")`: lista `historico_resumos(tipo, identificador)` com
   `criado_em`, `modelo`, flag do juiz (ancorado/neutro) e o texto por eixo.

O `modelo` salvo vem de `client.modelo or "claude-code-default"`.

## Tratamento de erros
- `gerar_resumo` falha (`ValueError` após N tentativas) → nada é salvo; UI mostra o erro
  (comportamento atual).
- `julgar` falha → resumo é salvo mesmo assim com `veredito = None` (juiz é não-fatal, como hoje).

## Plano de testes (TDD — alvos testáveis, sem rede)
1. `hash_payload`: mesmo payload → mesmo hash; mudar um valor → hash diferente.
2. `descrever_payload`: retorna `(tipo, identificador)` corretos para os 3 tipos.
3. `salvar_resumo` + `buscar_resumo_cache`: roundtrip; cache retorna o **mais recente**
   quando há duas versões do mesmo hash; `None` em cache miss.
4. `historico_resumos`: ordenação (mais recente primeiro) e filtragem por `(tipo, identificador)`.
5. `salvar_resumo` com `veredito=None` grava `NULL` e relê como `veredito is None`.

`LLMClient` continua mockado; estes testes nem chamam o LLM (operam sobre payloads/registros).

## Fora de escopo (YAGNI)
- Purga / limite de retenção do histórico.
- Diff visual entre versões.
- Exportar resumos (CSV/MD).
- Agendamento de regeração.
