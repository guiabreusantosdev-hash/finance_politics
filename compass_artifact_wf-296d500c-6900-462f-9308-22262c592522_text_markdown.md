# Como construir uma ferramenta de análise de dados econômicos e legislativos para avaliar a performance de governos (foco Brasil, contexto eleitoral 2026)

## TL;DR
- **É totalmente viável** com Claude Code: o caminho mais rápido é um backend Python (FastAPI) que ingere dados de APIs oficiais brasileiras gratuitas e abertas (BCB/SGS, IBGE/SIDRA, IPEADATA, Tesouro, Câmara, Senado) e internacionais (World Bank, IMF, OECD, FRED, OWID), armazena em PostgreSQL, e um frontend Next.js + ECharts/Plotly, com a API da Anthropic gerando os resumos em linguagem natural a partir de dados estruturados.
- **Atalho central**: a **Base dos Dados** (basedosdados.org), datalake público no BigQuery, já agrega e padroniza centenas de datasets brasileiros (IBGE, TSE, RAIS/CAGED, Câmara), reduzindo drasticamente o trabalho de ETL — use-a para dados históricos/eleitorais e as APIs nativas para dados "ao vivo".
- **Os riscos não são técnicos, mas de método**: instabilidade e documentação irregular das APIs públicas (mitigar com cache e camada de dados própria) e, sobretudo, **neutralidade analítica** no contexto eleitoral de 2026 (mitigar com metodologia transparente, fontes citadas, indicadores pré-definidos e separação rígida entre dado e interpretação).

## Key Findings

### Eixo 1 — Fontes de dados
1. **As principais fontes brasileiras têm APIs REST públicas, gratuitas e sem necessidade de chave de API** (BCB/SGS, IBGE/SIDRA, IPEADATA OData, Tesouro, Câmara v2, Senado). Isso simplifica muito a arquitetura.
2. O **BCB/SGS** é a fonte mais simples e robusta para séries macroeconômicas (Selic série 432, IPCA 433, INPC 188, IGP-M 189, câmbio dólar venda 1, PIB nominal R$ 1207). Retorna JSON/CSV via URL simples.
3. O **IBGE/SIDRA** (API de agregados v3) é a fonte oficial para PIB, IPCA, desemprego (PNAD Contínua) e produção industrial, mas é mais complexo (conceitos de agregado/variável/classificação) e tem limites de requisição.
4. Para **dados legislativos**, a API de Dados Abertos da Câmara (v2, REST/JSON, Swagger) e a do Senado (REST/XML/JSON, OpenAPI) cobrem proposições, votações, autoria e tramitação.
5. Fontes internacionais (World Bank, IMF, OECD, FRED, OWID) permitem comparação entre países; FRED exige chave de API, as demais não.

### Eixo 2 — Arquitetura técnica
1. **Stack recomendada**: Python + FastAPI (backend/ETL), PostgreSQL (dados), Next.js + TypeScript (frontend), ECharts ou Plotly (gráficos), API Anthropic (resumos). Essa combinação é ideal para Claude Code porque Python concentra o ecossistema de dados (pandas, requests) e IA.
2. **Banco de dados**: comece com PostgreSQL puro (ou até SQLite no protótipo). O volume de séries econômicas brasileiras é pequeno; só adote TimescaleDB se houver milhões de linhas.
3. **A camada de IA** deve usar Structured Outputs / tool use da Anthropic para gerar resumos confiáveis a partir de dados já calculados (nunca pedir ao modelo para "inventar" números).

## Details

### EIXO 1 — FONTES DE DADOS E APIs

#### 1.1 Fontes econômicas do Brasil

**Banco Central do Brasil — SGS (Sistema Gerenciador de Séries Temporais)**
- Documentação/busca de séries: https://www3.bcb.gov.br/sgspub/ e https://dadosabertos.bcb.gov.br
- Endpoint REST (sem autenticação): `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=dd/MM/aaaa&dataFinal=dd/MM/aaaa`
- Últimos N valores: `.../bcdata.sgs.{codigo}/dados/ultimos/{N}?formato=json`
- Formatos: JSON e CSV. Sem chave de API.
- Códigos úteis: **432** (meta Selic), **433** (IPCA mensal), **188** (INPC), **189** (IGP-M), **190** (IGP-DI), **1** (câmbio dólar venda), **1207** (PIB nominal R$), **13521** (meta de inflação), **3546** (reservas internacionais), **4447/4448/4449** (IPCA comercializáveis/não-comercializáveis/monitorados).
- Biblioteca Python recomendada: `python-bcb` (`from bcb import sgs`) — wrapper que devolve DataFrame pandas, com versões assíncronas. Documentação: https://wilsonfreitas.github.io/python-bcb/
- Também há a **API Olinda** (BCB) para dados como o Boletim Focus (expectativas de mercado: IPCA, PIB, Selic, câmbio projetados) e PTAX (câmbio).
- **Atenção**: a API pública REST é estável, mas o webservice SOAP legado exige certificado digital — prefira a API REST `api.bcb.gov.br`.

**IBGE — SIDRA (API de Agregados v3)**
- Documentação: https://servicodados.ibge.gov.br/api/docs/agregados?versao=3
- API simples alternativa: http://api.sidra.ibge.gov.br
- Base: `https://servicodados.ibge.gov.br/api/v3/agregados/{agregado}/periodos/{periodos}/variaveis/{variavel}?localidades=N1[all]`
- Retorna JSON. Sem chave de API, mas **com limites de requisição** — usar com cautela e cache.
- Tabelas-chave (confirmadas): **1620/1621** (PIB trimestral volume, sem/com ajuste sazonal), **1846** (PIB nominal trimestral), **1737** (IPCA mensal — série histórica e variações 12m), **7060** (IPCA por grupos, a partir de 2020), **6468** (taxa de desocupação PNAD Contínua, headline), **4093/4095** (desocupação por sexo/instrução), **8888** (Produção Física Industrial PIM-PF Brasil, série vigente base 2022=100; **8887** por categorias de uso; **8159** regional). Confirmar cada número em `sidra.ibge.gov.br/tabela/{numero}`.
- Bibliotecas: `sidrapy` (Python), pacote `sidra`/`ipeadatar` (R), módulo `DadosAbertosBrasil`.

**IPEADATA (IPEA)**
- Funciona como **agregador** consolidando IBGE, BCB, MTE, CVM etc. em uma base única — muito útil para séries históricas longas e dados regionais/sociais (IDH-M, Gini, pobreza).
- API OData v4 (sem chave): base `http://www.ipeadata.gov.br/api/odata4/`
- Metadados: `http://www.ipeadata.gov.br/api/odata4/Metadados` (filtrável por `$filter=contains(SERNOME,'PIB')`)
- Valores: `http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='PRECOS_IPCA')` — retorna JSON com campos SERCODIGO, VALDATA, VALVALOR, NIVNOME, TERCODIGO.
- Três bases temáticas: Macroeconômico, Regional, Social.
- Bibliotecas: `ipeadatapy` (Python), `ipeadatar` (R).

**Tesouro Nacional / Tesouro Transparente**
- Portal de APIs: https://www.gov.br/tesouronacional/pt-br/central-de-conteudo/apis
- APIs de dados abertos (sem autenticação, sem captcha): SIAFI, **SICONFI** (dados contábeis e fiscais de entes subnacionais, Matriz de Saldos Contábeis), **SADIPEM** (dívida pública e operações de crédito de estados/municípios — docs em `apidatalake.tesouro.gov.br/docs/sadipem`), SIC (custos do governo federal).
- Dívida Pública Federal (DPF) e estatísticas: https://www.tesourotransparente.gov.br/temas/divida-publica-federal — datasets CKAN com API.
- Para a relação **Dívida/PIB (DBGG)** e resultado primário/nominal, o BCB/SGS também expõe séries fiscais.

**Emprego — RAIS / CAGED**
- Disponíveis tratados na **Base dos Dados** (`basedosdados.br_me_rais`, microdados de vínculos) e via IPEADATA (saldo do Novo CAGED: série `CAGED12_SALDON12`).

#### 1.2 Fontes legislativas do Brasil

**Câmara dos Deputados — Dados Abertos (API v2)**
- Documentação Swagger: https://dadosabertos.camara.leg.br/swagger/api.html
- Base REST/JSON: `https://dadosabertos.camara.leg.br/api/v2/`
- Endpoints-chave: `/proposicoes` (filtros: `siglaTipo` ex. PL/PEC/PLP, `numero`, `ano`, `dataApresentacaoInicio/Fim`, `keywords`), `/proposicoes/{id}` (detalhe), `/proposicoes/{id}/tramitacoes`, `/proposicoes/{id}/autores`, `/votacoes`, `/votacoes/{id}/votos`, `/deputados`, `/partidos`, `/orgaos`, `/frentes`, `/eventos`.
- Também há **arquivos anuais** para download em massa (CSV/XLSX/JSON/XML) em `http://dadosabertos.camara.leg.br/arquivos/{conjunto}/{formato}/{conjunto}-{ano}.{formato}` — útil para carga histórica de proposições (registros de 1934 em diante; todas as proposições a partir de 2001), votações e autores.
- Atualização diária. Sem chave de API.

**Senado Federal — Dados Abertos**
- Documentação (OpenAPI/Swagger): https://legis.senado.leg.br/dadosabertos/docs/
- Base REST: `https://legis.senado.leg.br/dadosabertos/` — saída padrão XML; acrescente sufixo `.json` ou `.csv` para mudar formato.
- Endpoints-chave: `/materia/...` (matérias legislativas, movimentações, emendas, relatorias, votações — v4), `/legislacao/lista.json` (normas), `/senador/...`, `/comissao/...`, `/materia/distribuicao/autoria.json`.
- Portal reformulado em 2025 com novo padrão OpenAPI.

**LexML**
- Acervo unificado de normas, projetos de lei, jurisprudência e doutrina.
- API de pesquisa segue o padrão **SRU (Search/Retrieval via URL)** da Library of Congress, retornando XML.
- Documentação via portal Senado: https://www12.senado.leg.br/dados-abertos/legislativo/legislacao/acervo-do-portal-lexml

**TSE (eleições 2026)**
- Portal oficial: https://dadosabertos.tse.jus.br/
- Via Base dos Dados: dataset `br_tse_eleicoes` (página https://basedosdados.org/dataset/br-tse-eleicoes), com tabelas BigQuery `basedosdados.br_tse_eleicoes.candidatos`, `.receitas_candidato`, `.despesas_candidato`, `.resultados_candidato_municipio_zona`, `.bens_candidato` (cobertura 1945–2024). Validar grafia exata das tabelas na página do dataset ou via `__TABLES__` no BigQuery.

#### 1.3 Fontes econômicas internacionais

- **World Bank (World Development Indicators)**: API REST sem chave. `https://api.worldbank.org/v2/country/{iso}/indicator/{indicador}?format=json` (ex.: `NY.GDP.MKTP.CD` = PIB US$). Há também o novo World Bank Data360. Docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
- **IMF (FMI)**: APIs SDMX 2.1/3.0 em https://data.imf.org/en/Resource-Pages/IMF-API — bases WEO (World Economic Outlook, projeções), IFS, CPI, Fiscal Monitor.
- **OECD**: API SDMX REST (38 países) para dados macroeconômicos estruturados.
- **FRED (Federal Reserve de St. Louis)**: o próprio site descreve "Download, graph, and track 845,000 economic time series from 121 sources" (acesso jun/2026). **Requer chave de API gratuita**. Docs: https://fred.stlouisfed.org/docs/api/fred/
- **Our World in Data (OWID)**: API Grapher por URL — `https://ourworldindata.org/grapher/{chart}.csv` (full ou `?csvType=filtered&country=BRA&time=2000..2024`), metadados em `.metadata.json`. Excelente para indicadores comparáveis e índices de democracia/governança já harmonizados. Licença CC-BY (envie header `User-Agent`). Docs: https://docs.owid.io/projects/etl/api/chart-api/
- **Trading Economics**: tem API comercial (paga) — útil como referência de UX de dashboard, menos como fonte aberta.

#### 1.4 Governança/política internacional

- **Worldwide Governance Indicators (WGI)** do Banco Mundial: www.govindicators.org (seis dimensões de governança; revisão 2024/2025).
- **V-Dem (Varieties of Democracy)**: a página oficial da versão Country-Year Full+Others v16 descreve "All 531 V-Dem indicators and 251 indices + 62 other indicators"; a v15 (mar/2025) reuniu mais de 31 milhões de pontos de dados para 202 países de 1789 a 2024, com mais de 4.200 acadêmicos colaboradores. Cinco índices de democracia (eletoral, liberal, participativa, deliberativa, igualitária). https://www.v-dem.net/data/the-v-dem-dataset/ — acessível também via OWID e pacote R `democracyData`.
- **Freedom House**, **Polity5**: medidas clássicas de democracia, acessíveis via OWID e `democracyData`.

#### 1.5 Indicadores-chave para avaliar performance de governo

- **PIB / PIB per capita** (IBGE tabelas 1620/1621/1846): mede crescimento econômico; o PIB real desconta inflação. Não mede distribuição nem qualidade de vida — complementar com Gini e IDH.
- **Inflação (IPCA)** (IBGE 1737; BCB 433): índice oficial; mede custo de vida e poder de compra; base de calibração da Selic.
- **Desemprego / taxa de desocupação (PNAD Contínua)** (IBGE 6468): força de trabalho desocupada; sinaliza saúde do mercado de trabalho.
- **Dívida/PIB (DBGG)** e **déficit/resultado primário e nominal**: sustentabilidade fiscal. A DBGG fechou 2025 em 78,7% do PIB (R$ 10,018 trilhões), segundo as Estatísticas Fiscais do Banco Central divulgadas em 30/jan/2026 (ante 76,3% em 2024); pelo conceito do FMI, 93,4% do PIB em dez/2025.
- **Selic** (BCB 432): política monetária; juros reais = Selic − inflação.
- **Câmbio (R$/US$)** (BCB 1): competitividade externa, repasse inflacionário.
- **Balança comercial / contas externas**, **investimento (FBKF)**: dinamismo produtivo.
- **Gini, IDH/IDH-M, pobreza** (IPEADATA, Atlas do Desenvolvimento Humano, OWID): desigualdade e desenvolvimento social.
- **Boa prática**: nenhum indicador isolado avalia um governo. Usar um *painel balanceado* (econômico + social + fiscal) e contextualizar por mandato, ciclo econômico global e defasagens de política.

### EIXO 2 — ARQUITETURA TÉCNICA E IMPLEMENTAÇÃO

#### 2.1 Stack recomendada (justificada para Claude Code)

- **Backend / ETL: Python + FastAPI.** Python concentra o ecossistema de dados brasileiro (`python-bcb`, `ipeadatapy`, `sidrapy`, `basedosdados`, pandas) e a SDK da Anthropic. FastAPI é assíncrono, tem tipagem via Pydantic e gera OpenAPI automaticamente. Claude Code é muito produtivo em Python + FastAPI.
- **Frontend: Next.js + TypeScript.** Renderização híbrida (SSR/SSG/ISR), Route Handlers como Backend-for-Frontend, ótimo para dashboards. Alternativas: Vue/Nuxt (curva menor) ou, para protótipos rápidos, **Streamlit** (Python puro — pode ser o MVP mais veloz, dispensando frontend separado).
- **Padrão de implantação comum**: Next.js na Vercel + FastAPI/PostgreSQL no Railway/Render. Há template pronto `vintasoftware/nextjs-fastapi-template`.

#### 2.2 Bibliotecas de visualização — comparação

- **Apache ECharts (v6, 2025)**: melhor desempenho para grandes volumes e dashboards ricos (20+ tipos, mapas, séries temporais, heatmaps). Curva de aprendizado média (API extensa). Recomendada se o foco é dashboard denso. Wrapper React: `echarts-for-react`.
- **Plotly.js / Plotly.py**: excelente para análise científica/estatística, interatividade (zoom/pan), exportação; integra com Python/Jupyter. Mais pesado (bundle grande) — usar lazy loading. Ótimo se o autor quer gerar gráficos tanto no backend Python quanto no frontend.
- **Recharts**: nativo React, declarativo, simples, ideal para dashboards pequenos/médios; baseado em SVG (re-render lento em alta frequência) e menos customizável que D3/ECharts.
- **Chart.js**: minimalista (~60KB), rápido para gráficos básicos (linha/barra/pizza); pouca profundidade para visualizações complexas.
- **D3.js**: controle total, mas alto custo de desenvolvimento; usar só para visualizações customizadas.
- **Recomendação**: **ECharts** (dashboard principal) + **Plotly** se quiser reaproveitar geração de gráficos no Python. Para MVP em Streamlit, Plotly é o default natural.

#### 2.3 Pipeline de dados (ETL)

- **Ingestão**: scripts Python com `requests`/`httpx` + os wrappers (`python-bcb`, `sidrapy`, `ipeadatapy`, `basedosdados`). Persistir o **JSON bruto** antes de transformar (rastreabilidade).
- **Transformação**: pandas para normalizar para um esquema comum (`fonte`, `serie_id`, `data`, `valor`, `unidade`, `periodicidade`).
- **Armazenamento**: tabela de séries + tabela de observações (long format).
- **Agendamento**: `cron` (ou GitHub Actions agendado) para o caso simples; **Apache Airflow** ou **Prefect** só se o número de pipelines crescer muito.
- **Cache / proteção das APIs públicas**: cachear respostas (Redis ou cache em disco/SQLite), respeitar limites (sobretudo SIDRA), implementar *retry com backoff* (as APIs públicas brasileiras têm instabilidade conhecida) e atualizar conforme a periodicidade real de cada série (mensal/trimestral) em vez de a cada request.

#### 2.4 Banco de dados

- **Comece com PostgreSQL** (ou SQLite no protótipo local). Séries econômicas brasileiras são de volume pequeno; PostgreSQL puro cobre séries temporais + dados relacionais legislativos com folga.
- **TimescaleDB** (extensão do PostgreSQL com hypertables, compressão e continuous aggregates) só compensa em escala de milhões/bilhões de linhas — provavelmente desnecessário aqui.
- **BigQuery** entra naturalmente se você usar a Base dos Dados como backend de dados históricos/eleitorais (1 TB/mês gratuito por projeto Google Cloud).

#### 2.5 Camada de IA / LLM (resumos automáticos)

- Use a **API da Anthropic (Messages API)** com **Structured Outputs** (JSON Schema) ou **tool use** para gerar resumos confiáveis.
- **Princípio central**: o LLM **não calcula** indicadores — o backend computa os números (variação do PIB, inflação 12m, etc.) e os entrega ao modelo como contexto estruturado; o modelo apenas redige a narrativa. Isso evita alucinação numérica.
- Para resumos de "situação do país por ano": montar um payload com os indicadores do ano + variações + comparação com anos anteriores, e pedir um texto factual.
- Para "resumos de candidatos": alimentar dados objetivos e verificáveis (proposições de autoria, votações, dados de campanha do TSE) — **nunca** opiniões; pedir tom neutro e atribuição de fonte.
- Técnicas: `client.messages.parse()` com Pydantic (Python) ou `output_format` JSON Schema. Para escala, a documentação oficial da Anthropic indica cache reads a 0,1× do preço de input (90% de desconto), com cache writes a 1,25× (TTL 5 min) ou 2× (1 h), e Batch API com 50% de desconto tanto em input quanto em output, processado em até 24 h.
- Modelos atuais (jun/2026, página oficial de preços da Anthropic): **Claude Opus 4.8** (lançado 28/mai/2026) a US$5/US$25 por milhão de tokens (input/output), **Sonnet 4.6** a US$3/US$15 e **Haiku 4.5** a US$1/US$5, todos com janela de 1M tokens a preço padrão. Use Opus para máxima qualidade e Haiku para custo/volume.

#### 2.6 Arquitetura do sistema (componentes)

1. **Ingestão**: workers Python agendados (cron/Actions) → buscam APIs (BCB, IBGE, IPEA, Tesouro, Câmara, Senado, World Bank, OWID) → gravam bruto.
2. **Armazenamento**: PostgreSQL (séries + observações + metadados legislativos) + opcionalmente BigQuery/Base dos Dados para histórico.
3. **Backend/API**: FastAPI expõe endpoints REST tipados (`/series/{id}`, `/indicadores/ano/{ano}`, `/candidatos/{id}/resumo`) e orquestra cache.
4. **Camada de IA**: serviço que recebe dados estruturados e chama a API Anthropic com Structured Outputs para gerar resumos.
5. **Frontend/dashboard**: Next.js + ECharts/Plotly, com páginas por tema (macro, fiscal, social, legislativo) e visões comparativas por país/ano/governo.

#### 2.7 Dashboard — boas práticas e referências

- Organize por **temas** (macroeconomia, fiscal, social, legislativo) e por **visões temporais** (por ano e por mandato).
- Sempre exibir fonte, data da última atualização e unidade junto de cada gráfico.
- **Referências de inspiração**: dashboards do Banco Mundial e Trading Economics (UX de indicadores), painéis do IBGE (https://www.ibge.gov.br/indicadores), Tesouro Transparente, **Base dos Dados** (modelo de padronização e acesso), **Volt Data Lab / Núcleo Jornalismo** (jornalismo de dados sobre política e orçamento; criaram, por exemplo, um agregador interativo de pesquisas eleitorais para o Poder360 com dados desde 2000).

### Desafios específicos

- **Instabilidade e documentação irregular das APIs públicas brasileiras**: mitigar com camada de dados própria (não consultar a API a cada request), cache, retries com backoff, monitoramento e fallback para a Base dos Dados.
- **Neutralidade político-eleitoral (2026)**: definir um conjunto de indicadores *antes* de olhar os dados; separar rigidamente dado bruto de interpretação; citar fontes oficiais sempre; usar linguagem factual nos resumos de IA; documentar a metodologia publicamente; tratar todos os candidatos/governos com os mesmos critérios e janelas temporais; evitar cherry-picking de período.
- **Atualização de dados**: respeitar a periodicidade real (IPCA mensal, PIB trimestral, etc.); marcar dados preliminares/revisados; versionar.

## Recommendations

**Estágio 1 — MVP.** Streamlit OU Next.js simples + FastAPI + SQLite/PostgreSQL. Ingerir 8–10 séries do BCB/SGS (`python-bcb`) e 3–4 tabelas do SIDRA (PIB 1620/1621, IPCA 1737, desemprego 6468, produção industrial 8888). Gráficos com Plotly. Uma página "Situação do país por ano" com resumo gerado pela API Anthropic a partir dos números já calculados. Benchmark de avanço: dashboard mostrando séries atualizadas + 1 resumo automático coerente e factualmente correto.

**Estágio 2 — Camada legislativa e fiscal.** Adicionar API da Câmara (proposições/votações por ano e autoria) e Senado; dados de dívida/fiscais do Tesouro e BCB. Migrar para PostgreSQL. Adicionar cache e agendamento (cron/GitHub Actions).

**Estágio 3 — Comparação internacional e eleitoral.** Integrar World Bank/OWID/IMF para comparar o Brasil com pares; integrar TSE via Base dos Dados (`br_tse_eleicoes`) para "resumos de candidatos" baseados em dados objetivos. Publicar metodologia e fontes.

**Estágio 4 — Robustez.** Avaliar TimescaleDB só se o volume exigir; adicionar testes de qualidade de dados; Batch API + prompt caching para gerar resumos em escala; monitoramento de disponibilidade das APIs.

**Limiares que mudam as decisões**: se o volume de observações passar de poucos milhões → considerar TimescaleDB/BigQuery; se o número de pipelines passar de ~10 e com dependências → adotar Airflow/Prefect; se o frontend exigir muitos gráficos densos em tempo real → priorizar ECharts sobre Recharts; se os custos de geração de resumos crescerem → migrar de Opus para Sonnet/Haiku e ativar Batch API + prompt caching.

## Caveats
- Os números de séries do BCB e tabelas do SIDRA podem mudar de versão (a PIM-PF foi reformulada em 2023, p.ex.); sempre confirmar o código/tabela no portal oficial antes de codar.
- As APIs públicas brasileiras têm instabilidade e limites de requisição conhecidos (especialmente SIDRA); a arquitetura deve assumir falhas como normais.
- Os nomes exatos de algumas tabelas da Base dos Dados (TSE) devem ser validados na página do dataset / via `__TABLES__` no BigQuery (`candidatos` e `receitas_candidato` foram confirmados; os demais seguem o padrão de nomenclatura).
- FRED exige chave de API gratuita; Trading Economics é majoritariamente pago.
- Os modelos e preços da API Anthropic citados refletem a página oficial de jun/2026 e devem ser reconfirmados antes de orçar custos.
- O número da DBGG (78,7% do PIB pelo conceito BCB / 93,4% pelo FMI, dez/2025) é exemplo ilustrativo; atualizar pela fonte na implementação.
- Este relatório trata de *como construir a ferramenta*; a responsabilidade pela neutralidade e exatidão das análises produzidas é de quem opera a ferramenta.