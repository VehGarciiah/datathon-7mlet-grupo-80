# Datathon 7MLET — Grupo 80

Solução acadêmica de Machine Learning Engineering para experimentação adaptativa em campanhas de marketing. O MVP escolhe o próximo melhor **canal de contato** entre ações elegíveis e aprende com a conversão observada.

> Status: M0, M1 e M2 concluídos — contrato, governança, tradução PT-BR, EDA e preparação sem vazamento. Baselines e estratégia adaptativa começam no M3, conforme o [roadmap técnico](specs/ROADMAP_IMPLEMENTACAO.md).

## Visão do problema

Uma instituição financeira digital precisa escolher, para cada oportunidade elegível, qual próximo passo apresentar sem depender apenas de regras fixas e testes A/B longos. O projeto compara uma política determinística com uma política adaptativa baseada em Thompson Sampling, preservando exploração, rastreabilidade e revisão humana.

A base escolhida registra uma única oferta — assinatura de depósito a prazo — e dois canais históricos. Portanto, este projeto **não recomenda produtos diferentes**. A decisão do MVP é qual canal usar no próximo contato elegível.

## Contrato da decisão

O contrato completo e legível por máquina está em [`configs/experiment.yaml`](configs/experiment.yaml).

| Elemento | Definição do MVP |
|---|---|
| Unidade de decisão | uma oportunidade de contato elegível |
| Ações/braços | `celular` e `telefone` |
| Recompensa | `1` quando há assinatura do depósito; `0` caso contrário |
| Janela online inicial | 7 dias após a recomendação; hipótese a validar antes de uso real |
| Baseline | canal com maior conversão calculada somente no treino |
| Política adaptativa | Thompson Sampling Beta-Bernoulli por segmentos com fallback global |
| Saída | próximo melhor canal, versão da política e indicação de exploração |
| Abstenção | nenhuma ação quando elegibilidade ou canal permitido não estiver comprovado |

```mermaid
flowchart LR
    A[Oportunidade de contato] --> B{Elegível e autorizada?}
    B -- não --> C[Abster e encaminhar para revisão humana]
    B -- sim --> D[Política recebe contexto pré-decisão]
    D --> E[Seleciona celular ou telefone]
    E --> F[Registra decisão e versão]
    F --> G[Observa conversão na janela]
    G --> H[Atualiza somente o braço escolhido]
```

### Elegibilidade

Em uma operação real, uma recomendação só poderá ser emitida quando:

- existir finalidade e base legal aprovadas para o contato;
- o cliente não estiver em lista de bloqueio ou opt-out;
- houver ao menos um canal permitido e disponível;
- o payload respeitar o contrato de dados;
- limites de frequência e horário definidos pelo negócio forem atendidos.

A base pública não possui consentimento, opt-out, identificador persistente nem regras completas de elegibilidade. Para avaliação acadêmica, cada linha representa somente uma oportunidade histórica observada e nunca uma autorização para contato real.

### Contexto permitido e campos bloqueados

O contexto inicial da política usa momento do contato, histórico de campanhas e indicadores macroeconômicos disponíveis antes da decisão. `pdays=999` será convertido no indicador “nunca contatado anteriormente”. Como `campaign` inclui o contato atual, o pipeline deverá derivar `previous_attempts_current_campaign = campaign - 1` em vez de usar o campo bruto.

| Classificação | Campos | Regra |
|---|---|---|
| Contexto candidato | `month`, `day_of_week`, `pdays`, `previous`, `poutcome`, `emp.var.rate`, `cons.price.idx`, `cons.conf.idx`, `euribor3m`, `nr.employed` | podem entrar após validação e transformação no treino |
| Somente auditoria | `age`, `job`, `marital`, `education`, `default`, `housing`, `loan` | usar em EDA e análise de disparidade; não controlar a política do MVP |
| Bloqueados diretamente | `duration`, `campaign`, `contact`, `y` e identificadores técnicos | duração é pós-contato; `campaign` só alimenta a derivação pré-decisão; ação e recompensa ficam separadas do contexto |

## Dados e proveniência

Foi selecionada a base pública [Bank Marketing no Kaggle](https://www.kaggle.com/datasets/henriqueyamahata/bank-marketing), versão 1, publicada em 06/06/2018. A página do Kaggle identifica a licença como “Other (specified in description)” e referencia como origem o [UCI Machine Learning Repository](https://archive.ics.uci.edu/dataset/222/bank+marketing). A fonte UCI atual publica a base sob CC BY 4.0 e fornece o DOI [10.24432/C5K306](https://doi.org/10.24432/C5K306).

> A licença informada pelo distribuidor Kaggle e a licença atual da fonte UCI são registradas separadamente para não presumir equivalência jurídica. Qualquer redistribuição deve manter atribuição e ser revisada conforme a origem efetivamente utilizada.

| Propriedade do snapshot local | Valor |
|---|---|
| Arquivo | `data/raw/bank-additional-full.csv` |
| Registros | 41.188 |
| Colunas | 21 |
| Tamanho | 5.834.924 bytes |
| SHA-256 | `74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8` |
| Imutabilidade | obrigatória; transformações serão gravadas fora de `data/raw` |

Citação da fonte original:

> Moro, S., Rita, P., & Cortez, P. (2014). *Bank Marketing* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5K306.

Validação de integridade no PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 data\raw\bank-additional-full.csv
```

A variável alvo original é `y`: `yes` representa conversão e `no` representa não conversão. A coluna `duration` será mantida apenas na fonte imutável e em análises explícitas de vazamento; ela não poderá ser usada no treinamento realista nem na decisão.

## Camada canônica PT-BR — M1

O pipeline [`src/data/translate.py`](src/data/translate.py) verifica primeiro o hash da fonte, valida schema e categorias, traduz os dados e somente então grava [`data/interim/bank_marketing_ptbr.csv`](data/interim/bank_marketing_ptbr.csv). A linhagem e os controles de paridade ficam em [`bank_marketing_ptbr.metadata.json`](data/interim/bank_marketing_ptbr.metadata.json).

As chaves, funções e variáveis Python permanecem em inglês. Nomes físicos do dado usam `snake_case` em português sem acentos; documentação, comentários, docstrings e mensagens explicativas usam PT-BR.

### Dicionário de colunas

| Original | Canônica PT-BR | Uso no MVP |
|---|---|---|
| `age` | `idade` | somente auditoria |
| `job` | `profissao` | somente auditoria |
| `marital` | `estado_civil` | somente auditoria; `divorced` representa divorciado ou viúvo na fonte |
| `education` | `escolaridade` | somente auditoria |
| `default` | `inadimplencia` | somente auditoria |
| `housing` | `financiamento_habitacional` | somente auditoria |
| `loan` | `emprestimo_pessoal` | somente auditoria |
| `contact` | `canal_contato` | ação histórica, separada do contexto |
| `month` | `mes_contato` | contexto candidato |
| `day_of_week` | `dia_semana` | contexto candidato |
| `duration` | `duracao_contato` | auditoria de vazamento; proibida no modelo |
| `campaign` | `contatos_campanha_atual` | proibida diretamente; alimentará derivação pré-decisão no M2 |
| `pdays` | `dias_desde_ultimo_contato` | contexto; sentinela 999 será tratada no M2 |
| `previous` | `contatos_campanhas_anteriores` | contexto candidato |
| `poutcome` | `resultado_campanha_anterior` | contexto candidato |
| `emp.var.rate` | `taxa_variacao_emprego` | contexto candidato |
| `cons.price.idx` | `indice_precos_consumidor` | contexto candidato |
| `cons.conf.idx` | `indice_confianca_consumidor` | contexto candidato |
| `euribor3m` | `euribor_3_meses` | contexto candidato |
| `nr.employed` | `numero_empregados` | contexto candidato |
| `y` | `resultado` | recompensa binária, separada do contexto |

O pipeline acrescenta `event_id`, sequencial de 1 a 41.188, apenas para rastreabilidade. Esse identificador está bloqueado como feature.

### Paridade e qualidade

| Controle | Resultado do M1 |
|---|---|
| Registros da fonte/interim | 41.188 / 41.188 |
| Colunas da fonte/interim | 21 / 22, incluindo `event_id` |
| Linhas removidas | 0 |
| Células nulas | 0 |
| Duplicatas de negócio | 12, preservadas para remoção controlada no M2 |
| Target negativo | 36.548 — 88,73% |
| Target positivo | 4.640 — 11,27% |
| SHA-256 da camada interim | `0c073203818b48978ee6e1c9742cbe8b5fa0a6b531de78bf0530a0cf6328fa7c` |

`desconhecido` é uma categoria semântica, não um nulo técnico:

| Campo canônico | Quantidade | Proporção |
|---|---:|---:|
| `inadimplencia` | 8.597 | 20,87% |
| `escolaridade` | 1.731 | 4,20% |
| `financiamento_habitacional` | 990 | 2,40% |
| `emprestimo_pessoal` | 990 | 2,40% |
| `profissao` | 330 | 0,80% |
| `estado_civil` | 80 | 0,19% |

### Principais evidências da EDA

O notebook [`01_EDA.ipynb`](notebooks/01_EDA.ipynb) foi reconstruído para executar do kernel limpo e consumir apenas funções versionadas de `src/data`.

- conversão geral: 11,27%, confirmando desbalanceamento relevante;
- celular: 26.144 registros, 3.853 conversões e taxa histórica de 14,74%;
- telefone: 15.044 registros, 787 conversões e taxa histórica de 5,23%;
- campanha anterior com sucesso: conversão histórica de 65,11%, com suporte de 1.373 registros;
- duração média sem conversão: 220,84 segundos; com conversão: 553,19 segundos.

Os valores por canal são associações observacionais, não efeito causal. A grande diferença de duração demonstra por que `duration`, conhecida depois do contato, deve permanecer bloqueada.

O artefato legado `data/processed/bank_processed.csv` foi removido antes do M2 porque continha `duration` e não possuía pipeline integralmente reproduzível.

## Preparação para modelagem — M2

O pipeline [`src/data/prepare.py`](src/data/prepare.py) consome apenas a camada `interim` validada, remove duplicatas de negócio, deriva contexto pré-decisão, separa ação/target/auditoria e cria splits estratificados antes de ajustar transformações.

```mermaid
flowchart LR
    A[Interim validada] --> B[Remover 12 duplicatas]
    B --> C[Derivar contexto pré-decisão]
    C --> D[Separar contexto, ação, target e auditoria]
    D --> E[Split 70% / 15% / 15%]
    E --> F[Fit do preprocessing somente no treino]
    F --> G[Transform de treino, validação e teste]
```

### Contrato das features

| Componente | Colunas/regra |
|---|---|
| Identificador | `event_id`, preservado para linhagem e bloqueado como feature |
| Contexto categórico | `mes_contato`, `dia_semana`, `resultado_campanha_anterior` |
| Contexto numérico | dias desde último contato, contatos anteriores, tentativas anteriores na campanha e cinco indicadores macroeconômicos |
| Contexto binário | `nunca_contatado_anteriormente` |
| Ação | `canal_contato`, armazenada separadamente do contexto |
| Target | `resultado`, armazenado separadamente do contexto |
| Somente auditoria | idade, profissão, estado civil, escolaridade, inadimplência e empréstimos |
| Bloqueados | `duracao_contato`, `contatos_campanha_atual`, identificador, ação, target e campos de auditoria |

As duas derivações temporais são:

- `dias_desde_ultimo_contato=999` → valor ausente imputável mais `nunca_contatado_anteriormente=1`;
- `tentativas_anteriores_campanha_atual = contatos_campanha_atual - 1`, evitando expor o contato corrente.

### Deduplicação e splits

As duplicatas são calculadas usando os 21 campos de negócio, sem `event_id`. A primeira ocorrência na ordem da fonte é preservada e os 12 IDs removidos ficam registrados em [`preparation.metadata.json`](data/processed/preparation.metadata.json).

| Split | Registros | Negativos | Positivos | Taxa positiva |
|---|---:|---:|---:|---:|
| Treino | 28.823 | 25.576 | 3.247 | 11,265% |
| Validação | 6.176 | 5.480 | 696 | 11,269% |
| Teste | 6.177 | 5.481 | 696 | 11,268% |
| Total | 41.176 | 36.537 | 4.639 | 11,266% |

Os splits usam `random_seed=42`, estratificação por `resultado`, são disjuntos e ficam ordenados por `event_id` nos arquivos persistidos. Validação escolhe configuração; teste permanece reservado para a avaliação final.

### Preprocessing

O `ColumnTransformer` é ajustado exclusivamente nas 28.823 linhas de treino:

- categóricas: imputação pela moda e one-hot encoding com categorias novas ignoradas de forma controlada;
- numéricas: imputação pela mediana do treino e padronização com estatísticas do treino;
- binária: passagem direta;
- saída: 27 features em matrizes esparsas para treino, validação e teste.

O artefato local `artifacts/preprocessing/context_preprocessor.joblib`, as matrizes `.npz` e a lista de features são regeneráveis e permanecem fora do Git. Os CSVs processados e seus hashes são versionáveis:

| Artefato | Finalidade |
|---|---|
| [`train.csv`](data/processed/train.csv) | treino com contexto, ação e target separados por coluna |
| [`validation.csv`](data/processed/validation.csv) | seleção de configuração |
| [`test.csv`](data/processed/test.csv) | avaliação final intocada |
| [`audit.csv`](data/processed/audit.csv) | fatias de auditoria vinculadas por `event_id` e split |
| [`split_assignments.csv`](data/processed/split_assignments.csv) | atribuição reproduzível de cada evento |
| [`preparation.metadata.json`](data/processed/preparation.metadata.json) | hashes, versões, IDs removidos, features, shapes e prevalência |

O notebook [`02_preparation.ipynb`](notebooks/02_preparation.ipynb) demonstra o processo sem duplicar lógica. Testes automatizados comprovam que `duration`, campanha bruta, ação, target, identificador e campos de auditoria não entram no contexto.

## Critérios de sucesso

- negócio: taxa de conversão e lift absoluto/relativo contra o baseline;
- política: recompensa média e acumulada, distribuição de braços e cobertura do replay;
- incerteza: intervalo de confiança de 95% e no mínimo 30 seeds para a política estocástica;
- aprovação: configuração congelada, ausência de vazamento e limitações apresentadas junto às métricas;
- operação: possibilidade de abstenção e rollback para o baseline aprovado.

A política adaptativa só poderá ser marcada como candidata se superar o baseline no protocolo pré-registrado. Caso não supere, o resultado será documentado sem seleção oportunista de seed, subconjunto ou métrica.

## Governança e uso responsável

### Finalidade e base legal

O uso atual é exclusivamente educacional, com uma base pública sem identificadores diretos. Isso não autoriza o uso de dados reais. Antes de produção, Jurídico/Compliance deverá aprovar finalidade, base legal, transparência, direitos do titular, regras de contato, opt-out e tratamento de clientes vulneráveis.

A solução é apoio à decisão. Ela não concede crédito, altera preço, define condição financeira, executa contato automaticamente nem substitui julgamento humano.

### Minimização e retenção

- não coletar identificadores diretos, renda, patrimônio, gênero, raça ou regras comerciais privadas;
- não registrar payload completo em logs técnicos;
- manter atributos de maior risco somente para auditoria até existir justificativa e aprovação;
- reter eventos de recomendação e feedback por até 90 dias no ambiente demonstrativo;
- reter logs técnicos por até 30 dias;
- revisar a necessidade de retenção a cada 30 dias;
- excluir registros e derivados ao encerrar a finalidade ou vencer o prazo.

### Responsabilidades e aprovação

| Papel | Responsável no M0 | Responsabilidade |
|---|---|---|
| Negócio | Grupo 80 | aprovar objetivo, recompensa, elegibilidade e interpretação |
| Técnico | Grupo 80 | garantir reprodução, testes, segurança e operação |
| Risco de modelo | revisão por par do Grupo 80 | revisar vazamento, métricas, disparidades, limitações e rollback |

Quando houver mais de um integrante, a aprovação de uma versão candidata deverá vir de uma pessoa diferente de seu autor. Os nomes individuais serão registrados antes da primeira promoção de modelo.

### Registro inicial de riscos

| ID | Risco | Controle definido no M0 |
|---|---|---|
| R01 | confundir canal com produto/oferta | contrato e comunicação usam “próximo melhor canal” |
| R02 | vazamento por `duration` ou `campaign` bruto | denylist e derivação de contexto pré-decisão |
| R03 | tratar associação histórica como causalidade | replay com cobertura e limitação observacional junto às métricas |
| R04 | discriminação por atributos proxy | campos de risco somente para auditoria e gate humano |
| R05 | contato sem autorização ou acima de limites | abstenção quando elegibilidade não estiver comprovada |
| R06 | feedback duplicado ou atribuído ao braço errado | `recommendation_id` idempotente e vínculo validado |
| R07 | política adaptativa degradar a conversão | monitoramento e rollback para baseline aprovado |

## Limitações conhecidas

- os dados são observacionais e não contêm a propensão da política histórica;
- apenas o resultado da ação executada é conhecido; não existe contrafactual por cliente;
- a base possui uma oferta e dois canais, não um catálogo de produtos;
- consentimento, custo de contato, elegibilidade e identificadores persistentes não estão disponíveis;
- `duration` é conhecida somente depois da ligação e causa vazamento;
- a base é ordenada por data, mas não oferece uma data completa por registro para reconstrução temporal rigorosa;
- associações por canal ou perfil não devem ser apresentadas como efeito causal.

## Estrutura atual

```text
datathon-7mlet-grupo-80/
├── configs/
│   ├── data.yaml
│   └── experiment.yaml
├── data/
│   ├── interim/
│   │   ├── bank_marketing_ptbr.csv
│   │   └── bank_marketing_ptbr.metadata.json
│   ├── raw/
│   │   └── bank-additional-full.csv
│   └── processed/
│       ├── audit.csv
│       ├── preparation.metadata.json
│       ├── split_assignments.csv
│       ├── test.csv
│       ├── train.csv
│       └── validation.csv
├── notebooks/
│   ├── 01_EDA.ipynb
│   └── 02_preparation.ipynb
├── src/
│   ├── data/
│   │   ├── contracts.py
│   │   ├── prepare.py
│   │   ├── translate.py
│   │   └── validate.py
│   └── features/
│       └── build_features.py
├── specs/
│   ├── fiap-postech-mlet-datathon.pdf
│   └── ROADMAP_IMPLEMENTACAO.md
├── tests/
│   ├── integration/
│   └── unit/
├── README.md
└── requirements.txt
```

## Como executar o estado atual

Clone o repositório:

```bash
git clone https://github.com/VehGarciiah/datathon-7mlet-grupo-80
cd datathon-7mlet-grupo-80
```

Crie e ative um ambiente virtual e instale as dependências:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Valide o contrato YAML:

```powershell
python -c "from pathlib import Path; import yaml; yaml.safe_load(Path('configs/experiment.yaml').read_text(encoding='utf-8')); print('Contrato válido')"
```

Gere novamente a camada canônica PT-BR:

```powershell
python -m src.data.translate --config configs/data.yaml
```

Gere os splits e o preprocessing do M2:

```powershell
python -m src.data.prepare --config configs/data.yaml
```

Execute todos os testes:

```powershell
python -m pytest -q
```

Execute o notebook de análise:

```powershell
jupyter notebook notebooks/01_EDA.ipynb
```

Execute o notebook de preparação:

```powershell
jupyter notebook notebooks/02_preparation.ipynb
```

Os comandos de treinamento, avaliação, MLflow e API serão adicionados nos marcos seguintes sem alterar os contratos aprovados de forma silenciosa.

## Checklist M0

- [x] decisão, braços e recompensa definidos;
- [x] elegibilidade, abstenção e limitações documentadas;
- [x] fonte, versão, licença e hash registrados;
- [x] contexto permitido, campos de auditoria e vazamentos separados;
- [x] finalidade, minimização, retenção e humano no loop definidos;
- [x] responsáveis por negócio, técnica e risco definidos por papel;
- [x] critérios de sucesso, aprovação e rollback registrados;
- [x] contrato versionado em `configs/experiment.yaml`;
- [ ] nomes individuais atribuídos aos papéis antes da promoção do primeiro modelo;
- [ ] janela de recompensa e regras de elegibilidade validadas antes de uso real.

## Checklist M1

- [x] contrato operacional criado em `configs/data.yaml`;
- [x] SHA-256 da fonte verificado antes da leitura;
- [x] 21 colunas e todas as categorias conhecidas validadas;
- [x] tradução EN→PT-BR versionada em `src/data`;
- [x] categoria nova ou schema divergente causa falha explícita;
- [x] 41.188 linhas e distribuição do target preservadas;
- [x] `event_id` técnico adicionado e bloqueado como feature;
- [x] camada `interim` e metadados de linhagem gerados;
- [x] notebook de EDA executável do kernel limpo;
- [x] 12 duplicatas e categorias `desconhecido` mensuradas;
- [x] vazamento de `duration` demonstrado e documentado;
- [x] testes unitários e de integração aprovados.

## Checklist M2

- [x] artefato processado legado e com vazamento removido;
- [x] 12 duplicatas removidas mantendo a primeira ocorrência;
- [x] IDs removidos registrados para rastreabilidade;
- [x] sentinela 999 transformada em indicador e ausência imputável;
- [x] campanha bruta substituída por tentativas anteriores à decisão;
- [x] contexto, ação, target, identificador e auditoria separados;
- [x] splits 70%/15%/15% estratificados, disjuntos e determinísticos;
- [x] preprocessing ajustado somente no treino;
- [x] validação e teste recebem apenas `transform`;
- [x] `duration` e demais campos bloqueados ausentes do contexto;
- [x] 27 nomes de features e shapes registrados;
- [x] hashes dos outputs e versões das dependências registrados;
- [x] notebook de preparação executável do kernel limpo;
- [x] testes unitários e de integração aprovados.
