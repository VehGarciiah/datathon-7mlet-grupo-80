# Datathon 7MLET — Grupo 80

Solução acadêmica de Machine Learning Engineering para experimentação adaptativa em campanhas de marketing. O MVP escolhe o próximo melhor **canal de contato** entre ações elegíveis e aprende com a conversão observada.

> Status: M0–M6 concluídos — pipeline reproduzível, baselines, Thompson Sampling candidato, replay, golden set, API, MLflow, observabilidade local e arquitetura AWS. A publicação do vídeo e a aprovação humana da política candidata permanecem como gates finais.

## Resumo executivo e impacto

O projeto transforma o problema genérico de “melhor oferta” em uma decisão factual suportada pela base: escolher `celular` ou `telefone` para o próximo contato elegível. A política fixa recomenda sempre celular; a política Thompson Sampling `1.1.0` usa mês do contato e resultado da campanha anterior para equilibrar exploração e explotação.

No replay factual de teste, a recompensa média entre eventos aceitos passou de **15,19%** no baseline para **17,94%** no Thompson Sampling: lift absoluto médio de **2,75 p.p.**, lift relativo de **18,13%** e IC95% bootstrap do lift de **[2,53; 2,99] p.p.** em 30 seeds. O mesmo gate foi positivo na validação.

Esse ganho é evidência offline observacional, não estimativa causal de produção. As políticas têm coberturas diferentes no replay e só revelam recompensa quando a recomendação coincide com o canal histórico. O impacto de negócio deverá ser confirmado em experimento online controlado, com propensão registrada, limites de contato, custo por canal e aprovação humana.

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

O artefato `artifacts/preprocessing/context_preprocessor.joblib`, as matrizes `.npz` e a lista de features são regeneráveis, mas ficam versionados como evidências reproduzíveis do M2. Os CSVs processados e seus hashes também são versionados:

| Artefato | Finalidade |
|---|---|
| [`train.csv`](data/processed/train.csv) | treino com contexto, ação e target separados por coluna |
| [`validation.csv`](data/processed/validation.csv) | seleção de configuração |
| [`test.csv`](data/processed/test.csv) | avaliação final intocada |
| [`audit.csv`](data/processed/audit.csv) | fatias de auditoria vinculadas por `event_id` e split |
| [`split_assignments.csv`](data/processed/split_assignments.csv) | atribuição reproduzível de cada evento |
| [`preparation.metadata.json`](data/processed/preparation.metadata.json) | hashes, versões, IDs removidos, features, shapes e prevalência |

O notebook [`02_preparation.ipynb`](notebooks/02_preparation.ipynb) demonstra o processo sem duplicar lógica. Testes automatizados comprovam que `duration`, campanha bruta, ação, target, identificador e campos de auditoria não entram no contexto.

## Baselines determinístico e preditivo — M3

O M3 cria duas referências distintas:

1. uma política determinística que sempre recomenda o canal com maior conversão histórica no treino;
2. um modelo de propensão que estima `P(conversão | contexto, canal observado)`.

A política decide uma ação. O modelo preditivo estima uma probabilidade associativa e não deve ser confundido com a política nem com efeito causal.

### Baseline determinístico

A classe [`BestHistoricalActionPolicy`](src/policies/fixed.py) foi ajustada exclusivamente em `train`. Empates são resolvidos pela ordem estável do contrato e, se o melhor braço estiver indisponível, a política usa a primeira ação elegível como fallback.

| Canal no treino | Observações | Conversões | Conversão | IC 95% de Wilson |
|---|---:|---:|---:|---:|
| Celular | 18.313 | 2.699 | 14,738% | 14,232%–15,259% |
| Telefone | 10.510 | 548 | 5,214% | 4,805%–5,656% |

O braço congelado é `celular`. No replay factual:

| Split | Eventos aceitos | Cobertura | Conversões | Recompensa média |
|---|---:|---:|---:|---:|
| Validação | 3.924 | 63,54% | 561 | 14,30% |
| Teste | 3.898 | 63,11% | 592 | 15,19% |

Somente eventos cujo canal histórico coincide com a recomendação possuem recompensa observável. A cobertura deve sempre acompanhar a recompensa; esse resultado não estima causalmente o que ocorreria ao trocar o canal.

### Baseline preditivo

O script [`train_propensity.py`](src/models/train_propensity.py) compara `DummyClassifier(strategy="prior")` com Regressão Logística L2. O pipeline recebe os 12 campos de contexto do M2 mais `canal_contato`, ajusta todo o preprocessing no treino e gera 29 features transformadas.

PR-AUC/average precision é a métrica de seleção por causa do desbalanceamento. O limiar `0,204832` maximiza F1 na validação e é congelado antes do teste.

| Modelo | Split | PR-AUC | ROC-AUC | Brier | F1 |
|---|---|---:|---:|---:|---:|
| Dummy | Validação | 0,1127 | 0,5000 | 0,1000 | 0,0000 |
| Regressão Logística | Validação | 0,4493 | 0,7954 | 0,0790 | 0,4909 |
| Dummy | Teste | 0,1127 | 0,5000 | 0,1000 | 0,0000 |
| Regressão Logística | Teste | 0,4664 | 0,8129 | 0,0771 | 0,5054 |

No teste, o modelo alcançou precision de 45,37%, recall de 57,04% e matriz de confusão `TN=5003`, `FP=478`, `FN=299`, `TP=397`. A PR-AUC de validação superou o Dummy em 0,3366 ponto absoluto, aprovando o gate do M3. Como o Brier e a curva por decis melhoraram de forma consistente contra o Dummy, um calibrador adicional não foi aplicado nesta baseline.

Após gerar as predições, o teste é avaliado em 34 fatias agregadas de idade, profissão, estado civil, escolaridade, inadimplência e empréstimos, todas com pelo menos 100 registros. Esses atributos não são features: o cruzamento ocorre somente pela camada separada de auditoria. PR-AUC varia com a prevalência de cada fatia, então diferenças são sinais para investigação e não comprovam, isoladamente, discriminação ou desempenho superior de um grupo.

Os relatórios versionáveis são:

| Artefato | Conteúdo |
|---|---|
| [`m3_metrics.json`](reports/modeling/m3_metrics.json) | métricas, calibração, matriz de confusão, contratos, hashes e limitações |
| [`fixed_baseline.json`](reports/modeling/fixed_baseline.json) | braço escolhido, suporte, intervalo de confiança e replay |
| [`logistic_coefficients.csv`](reports/modeling/logistic_coefficients.csv) | coeficientes e odds ratios para análise técnica |
| [`validation_predictions.csv`](reports/modeling/validation_predictions.csv) | probabilidades e predições da validação |
| [`test_predictions.csv`](reports/modeling/test_predictions.csv) | probabilidades e predições do teste congelado |
| [`test_slice_metrics.csv`](reports/modeling/test_slice_metrics.csv) | PR-AUC, ROC-AUC, Brier e classificação por fatia de auditoria |

O pipeline treinado fica em `artifacts/models/propensity_pipeline.joblib` e a política em `artifacts/policies/fixed_policy.joblib`. Ambos são regeneráveis, ficam versionados como evidências do M3 e passaram por inferência smoke usando o mesmo preprocessing do treino.

### MLflow

O comando oficial registra onze parâmetros, oito métricas e os artefatos do M3 no experimento `datathon-7mlet-m3-baselines`. O backend é SQLite (`mlflow.db`), pois versões atuais do MLflow mantêm o antigo file store apenas em modo de manutenção. O banco, `mlruns/` e `artifacts/` são versionados intencionalmente para permitir auditoria acadêmica, estudo e reprodução por outro desenvolvedor. Nenhum segredo ou dado operacional real deve ser armazenado nesses diretórios.

O identificador da execução mais recente está em [`latest_mlflow_run.json`](reports/modeling/latest_mlflow_run.json). O notebook [`03_modeling_and_baseline.ipynb`](notebooks/03_modeling_and_baseline.ipynb) apenas reproduz os relatórios e não cria runs extras.

### Limites de interpretação

- o canal observado não foi alocado aleatoriamente;
- não existe recompensa contrafactual para o canal não executado;
- coeficientes regularizados representam associações condicionais, não regras causais;
- atributos demográficos e financeiros da camada de auditoria não entram no modelo;
- o limiar técnico maximiza F1 e deverá ser substituído por uma regra baseada em custo/capacidade antes de produção.

## Thompson Sampling e replay factual — M4

O M4 implementa [`SegmentedThompsonSamplingPolicy`](src/policies/thompson_sampling.py), uma política Beta-Bernoulli com prior `Beta(1,1)`, seed controlada, atualização idempotente e estado JSON persistido por substituição atômica. A versão `1.1.0` usa somente `mes_contato` e `resultado_campanha_anterior`, ambos disponíveis antes da decisão. Essa configuração foi escolhida entre combinações parcimoniosas usando apenas validação e congelada antes da avaliação final em teste.

```mermaid
flowchart LR
    A[Evento em ordem por event_id] --> B[Thompson amostra braços elegíveis]
    B --> C{Recomendação coincide<br/>com canal histórico?}
    C -- não --> D[Não revela recompensa<br/>nem atualiza posterior]
    C -- sim --> E[Revela recompensa binária]
    E --> F[Atualiza somente o braço escolhido]
    F --> G[Registra feedback_id idempotente]
```

O treino determina apenas quais segmentos têm suporte mínimo de 100 observações por braço. As recompensas históricas não aquecem os posteriores, evitando transformar o viés da política observacional em prior. Dos 30 segmentos observados, seis atendem ao suporte; os demais recorrem ao posterior global do braço.

### Protocolo e resultado

Cada uma das 30 seeds começa do mesmo estado inicial em validação e teste. Baseline e política adaptativa recebem a mesma sequência estável. Eventos sem coincidência de ação são descartados porque não existe recompensa contrafactual observada.

| Split | Política | Recompensa média | Desvio entre seeds | Cobertura | Recompensa cumulativa | Exploração |
|---|---|---:|---:|---:|---:|---:|
| Validação | Baseline fixa | 14,30% | — | 63,54% | 561 | 0% |
| Validação | Thompson Sampling | 17,22% | 0,57 p.p. | 42,78% | 454,3 em média | 14,91% |
| Teste | Baseline fixa | 15,19% | — | 63,11% | 592 | 0% |
| Teste | Thompson Sampling | 17,94% | 0,64 p.p. | 41,11% | 454,6 em média | 13,40% |

| Split | Lift absoluto médio | Lift relativo médio | IC95% bootstrap do lift | Gate |
|---|---:|---:|---:|---|
| Validação | +2,92 p.p. | +20,43% | [+2,72; +3,13] p.p. | passou |
| Teste | +2,75 p.p. | +18,13% | [+2,53; +2,99] p.p. | passou |

O IC do lift usa as 30 seeds como unidade de reamostragem; o IC da recompensa fixa reamostra os eventos aceitos. Como o lift médio e seu limite inferior são positivos nos dois splits, a política fica marcada como `candidate`. A promoção continua bloqueada até aprovação humana; `best_historical_action` permanece como rollback do serving padrão. Não houve seleção oportunista de seed. Recompensa cumulativa também não deve ser comparada isoladamente, porque as coberturas são diferentes.

Regret factual não foi calculado: a base não contém um oracle nem o resultado do canal não executado. IPS também não é evidência principal porque a propensão da política histórica é desconhecida.

### Evidências do M4

| Artefato | Conteúdo |
|---|---|
| [`policy.yaml`](configs/policy.yaml) | prior, segmentos, suporte, seeds, bootstrap e gate congelados |
| [`m4_policy_evaluation.json`](reports/policy/m4_policy_evaluation.json) | comparação completa, intervalos, gate e limitações |
| [`m4_seed_results.csv`](reports/policy/m4_seed_results.csv) | métricas individuais das 30 seeds por split |
| [`m4_replay_curves.csv`](reports/policy/m4_replay_curves.csv) | curvas agregadas evento a evento |
| [`m4_replay_comparison.png`](reports/policy/m4_replay_comparison.png) | recompensa cumulativa, escolhas e exploração |
| [`thompson_policy_state.json`](artifacts/policies/thompson_policy_state.json) | estado inicial versionado e restaurável |
| [`latest_mlflow_run.json`](reports/policy/latest_mlflow_run.json) | run oficial do experimento M4 |

O identificador da execução mais recente fica em [`latest_mlflow_run.json`](reports/policy/latest_mlflow_run.json). O run registra configuração, métricas, artefatos e as tags `candidate=true`, `approved=false`, `rejected=false`. O notebook [`04_policy_evaluation.ipynb`](notebooks/04_policy_evaluation.ipynb) apresenta as evidências sem reimplementar o replay nem gerar runs extras.

## Golden set e API demonstrável — M5

O serving carrega automaticamente o modelo M3 e os metadados dos runs M3/M4. Como o Thompson Sampling está `candidate`, mas ainda não recebeu aprovação humana, a estratégia `approved_adaptive_or_fixed_rollback` mantém [`BestHistoricalActionPolicy`](src/policies/fixed.py). O modo adaptativo só pode ser iniciado explicitamente como `adaptive_demo`; ele usa estado separado e não altera o status de aprovação.

### Golden set

Os cinco casos sintéticos versionados em [`golden_set.json`](tests/fixtures/golden_set.json) passaram pelo mesmo endpoint FastAPI. A categoria `profissao=desconhecido` aparece apenas como nota de auditoria do quarto caso e não é enviada à política.

| Caso | Cenário | Recomendação | Fallback | Revisão humana |
|---|---|---|---|---|
| `golden_previous_success` | campanha anterior com sucesso | celular | não | faz sentido, sem alegação causal |
| `golden_previous_failure` | campanha anterior com fracasso | celular | não | faz sentido, sem responsabilizar o cliente |
| `golden_never_contacted` | nenhum contato anterior | celular | não | requer confirmar consentimento |
| `golden_unknown_audit_category` | categoria desconhecida só na auditoria | celular | não | faz sentido; atributo excluído |
| `golden_cellular_unavailable` | celular indisponível | telefone | sim | requer confirmar disponibilidade |

O relatório [`golden_set_results.json`](reports/serving/golden_set_results.json) registra `5/5` contratos aprovados, versões, razões e pareceres humanos. O notebook [`05_golden_set_and_api.ipynb`](notebooks/05_golden_set_and_api.ipynb) apresenta a tabela sem criar eventos de produção.

### Contrato HTTP

| Método e rota | Comportamento |
|---|---|
| `POST /v1/recommendations` | valida contexto, autorização e braços; retorna decisão e versões |
| `POST /v1/feedback` | registra recompensa terminal e impede duplicação/conflito |
| `GET /health` | confirma vida do processo |
| `GET /ready` | confirma política, modelo, SQLite e linhagem MLflow |
| `GET /metrics` | expõe counters, gauges e histogramas no formato Prometheus |
| `GET /docs` | disponibiliza Swagger gerado pelo contrato Pydantic |

```mermaid
sequenceDiagram
    participant C as Canal autorizado
    participant A as FastAPI
    participant P as Política aprovada
    participant S as SQLite
    C->>A: contexto pré-decisão + ações elegíveis
    A->>A: valida schema, autorização e opt-out
    A->>P: recommend(contexto, ações)
    P-->>A: canal, versão e razão
    A->>S: decisão + somente contexto mínimo de aprendizado
    A-->>C: recommendation_id + canal
    C->>A: reward + observed_at
    A->>S: valida vínculo, janela e idempotência
    A-->>C: recorded ou duplicate
```

As faixas numéricas do schema vêm dos mínimos e máximos do treino versionado. Payload fora da referência, campo extra, lista de ações vazia ou inconsistência entre `nunca_contatado_anteriormente` e dias desde o contato retornam `422`. Contato não autorizado ou opt-out retorna `409` sem decisão. O banco [`serving.db`](artifacts/serving/serving.db) guarda ação, versão, braços elegíveis e apenas os dois campos de segmento; o payload completo e atributos de auditoria não são persistidos.

Feedback idêntico retorna `duplicate` sem nova atualização. Uma segunda recompensa divergente retorna `409`; ID desconhecido retorna `404`; timestamp inválido retorna `422`. Feedback tardio é preservado para auditoria, mas não atualiza a política. A política fixa apenas audita recompensas. No modo demonstrativo adaptativo, somente o braço recomendado é atualizado e o estado runtime é salvo atomicamente.

Logs JSON registram rota normalizada, status, latência, versão, `trace_id` e `span_id`, nunca o corpo. `/metrics` publica counters agregáveis, histogramas de latência e atraso de feedback, readiness, volumes persistidos, recompensa observada, recomendações, exploração e fallback sem identificadores. [`monitoring.yaml`](configs/monitoring.yaml) preserva faixas do treino e o limite inferior do IC95% factual do baseline; SLO de serviço permanece sem limiar até existir amostra local suficiente, evitando inventar uma meta.

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

## Arquitetura-alvo AWS — M6

O serviço seria empacotado em imagem versionada no Amazon ECR e executado pelo ECS Fargate atrás de Amazon API Gateway e AWS WAF. O DynamoDB armazenaria decisões, feedback idempotente e o estado concorrente da política; o S3, com versionamento e criptografia KMS, guardaria datasets permitidos, relatórios e artefatos. Jobs agendados no SageMaker Processing/Training ou em tarefas ECS executariam preparação, treino e replay, registrando parâmetros e métricas em um MLflow hospedado em ECS com metadados no RDS e artefatos no S3.

CloudWatch centralizaria logs estruturados, métricas, dashboards e alarmes. IAM de mínimo privilégio separaria serving, treino e aprovação; Secrets Manager guardaria credenciais, e CloudTrail registraria mudanças administrativas. Uma versão candidata só seria promovida após o gate técnico e aprovação humana. Falha de artefato, degradação de recompensa ou violação de dados acionaria rollback para `best_historical_action`. O desafio não exige provisionar esses serviços; esta é a arquitetura operacional proposta.

```mermaid
flowchart LR
    U[Canal digital] --> WAF[AWS WAF]
    WAF --> APIG[API Gateway]
    APIG --> API[FastAPI em ECS Fargate]
    ECR[ECR<br/>imagens versionadas] --> API
    API --> DDB[(DynamoDB<br/>decisões, feedback e posterior)]
    API --> S3[(S3<br/>eventos e artefatos)]
    S3 --> TRAIN[Job SageMaker ou ECS<br/>treino e replay]
    TRAIN --> MLF[MLflow<br/>ECS + RDS + S3]
    MLF --> APPROVE{Gate técnico<br/>e humano}
    APPROVE -->|promover| S3
    APPROVE -->|rejeitar| ROLLBACK[Baseline aprovado]
    CW[CloudWatch<br/>logs, métricas e alarmes] --- API
    CW --- TRAIN
    KMS[KMS] --- S3
    KMS --- DDB
    IAM[IAM + Secrets Manager] --- API
    CT[CloudTrail] --- IAM
```

### Observabilidade e resposta operacional

O MVP publica métricas Prometheus nativas da API e um exportador das evidências M1–M5. Prometheus, Alertmanager, Grafana, Loki, Alloy, Tempo, OpenTelemetry Collector, MLflow e a própria API sobem no mesmo Podman Compose. Os dashboards provisionados cobrem sinais RED, feedback e política online, métricas offline, gates e disponibilidade dos artefatos. Logs e traces são correlacionados pelo `trace_id`. Após pelo menos 500 feedbacks, recompensa abaixo do limite inferior factual do baseline (`14,11%`) abre alerta para pausa do modo adaptativo e revisão.

Na AWS, um job periódico compararia a janela recente com o treino por PSI ou Jensen-Shannon, além de medir categorias desconhecidas, nulos, cobertura, braço dominante e disparidades por fatia de auditoria. CloudWatch alarmaria erros, indisponibilidade e latência; relatórios de drift e qualidade seriam gravados no S3 e anexados ao MLflow. Limiares de SLO permanecem sem números inventados até uma medição local representativa. Todo alerta de dados, recompensa ou governança abre revisão humana e pode bloquear promoção ou acionar rollback.

## Estrutura atual

```text
datathon-7mlet-grupo-80/
├── configs/
│   ├── data.yaml
│   ├── experiment.yaml
│   ├── modeling.yaml
│   ├── policy.yaml
│   ├── monitoring.yaml
│   └── api.yaml
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
├── examples/
│   └── recommendation_request.json
├── notebooks/
│   ├── 01_EDA.ipynb
│   ├── 02_preparation.ipynb
│   ├── 03_modeling_and_baseline.ipynb
│   ├── 04_policy_evaluation.ipynb
│   └── 05_golden_set_and_api.ipynb
├── artifacts/                       # preprocessadores, modelos e políticas versionados
│   └── serving/serving.db           # schema local de decisões e feedback
├── mlruns/                          # artefatos das execuções registradas no MLflow
├── mlflow.db                        # metadados e métricas das execuções do MLflow
├── orchestration/
│   └── dags/datathon_pipeline.py     # DAG visual M1–M4 do Airflow
├── observability/                    # configuração e runbook da stack local
│   ├── alertmanager/
│   ├── alloy/
│   ├── grafana/                     # datasources e dashboards provisionados
│   ├── loki/
│   ├── mlflow/
│   ├── otel-collector/
│   ├── prometheus/
│   └── tempo/
├── reports/
│   ├── modeling/
│   │   ├── fixed_baseline.json
│   │   ├── latest_mlflow_run.json
│   │   ├── logistic_coefficients.csv
│   │   ├── m3_metrics.json
│   │   ├── test_predictions.csv
│   │   ├── test_slice_metrics.csv
│   │   └── validation_predictions.csv
│   ├── policy/
│   │   ├── latest_mlflow_run.json
│   │   ├── m4_policy_evaluation.json
│   │   ├── m4_replay_comparison.png
│   │   ├── m4_replay_curves.csv
│   │   └── m4_seed_results.csv
│   └── serving/
│       └── golden_set_results.json
├── src/
│   ├── api/
│   │   ├── main.py
│   │   ├── repository.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── data/
│   │   ├── contracts.py
│   │   ├── prepare.py
│   │   ├── translate.py
│   │   └── validate.py
│   ├── features/
│   │   └── build_features.py
│   ├── models/
│   │   └── train_propensity.py
│   ├── observability/
│   │   ├── api.py
│   │   └── process_exporter.py
│   ├── evaluation/
│   │   ├── golden_set.py
│   │   └── replay.py
│   └── policies/
│       ├── base.py
│       ├── fixed.py
│       └── thompson_sampling.py
├── scripts/
│   ├── rebase_mlflow_paths.py       # adapta URIs do MLflow ao caminho do clone
│   └── snapshot_mlflow.py           # publica e valida o snapshot do volume MLflow
├── specs/
│   ├── fiap-postech-mlet-datathon.pdf
│   └── ROADMAP_IMPLEMENTACAO.md
├── tests/
│   ├── integration/
│   ├── fixtures/
│   └── unit/
├── Containerfile
├── compose.yaml
├── pyproject.toml
├── README.md
├── requirements-api.txt
└── requirements.txt
```

## Como executar o estado atual

Clone o repositório:

```bash
git clone https://github.com/VehGarciiah/datathon-7mlet-grupo-80
cd datathon-7mlet-grupo-80
```

### Executar API e observabilidade com Podman Compose

Com a máquina do Podman iniciada, prepare as variáveis locais e suba todo o ambiente:

```powershell
Copy-Item .env.example .env
podman compose config
podman compose up -d --build
podman compose ps
```

Execute o pipeline completo (tradução, preparação, treino e replay) sem instalar
Python no host:

```powershell
podman compose run --rm --build pipeline
podman compose restart api process-exporter
```

O job usa `http://mlflow:5000` como tracking URI e grava os artefatos no mesmo volume
persistente do servidor. Os runs de M3 e M4 aparecem na interface do MLflow; os dados,
modelos e relatórios continuam materializados em `data/`, `artifacts/` e `reports/` no
checkout. O restart final faz a API recarregar o modelo e a linhagem recém-gerados.

Quando os runs forem escolhidos como evidência da entrega, publique o banco e os
artefatos do volume no snapshot versionado:

```powershell
podman compose run --rm --build mlflow-snapshot
python -m scripts.snapshot_mlflow --check-only
```

O primeiro comando recusa copiar enquanto existir run ativo, faz backup consistente do
SQLite e valida se os IDs de M3/M4 em `latest_mlflow_run.json` estão finalizados e possuem
artefatos. O segundo repete essa validação no checkout e também é executado pelo CI.

Para executar apenas uma etapa, use um dos serviços de tarefa:

```powershell
podman compose run --rm --build prepare
podman compose run --rm --build train
podman compose run --rm --build evaluate
```

Os serviços de tarefa pertencem ao profile `jobs`: eles não ficam em execução com
`podman compose up`. Cada `run --rm` cria um contêiner efêmero, encerra ao concluir e
preserva somente as saídas e o tracking. Não execute `mlflow ui` no host ao mesmo tempo,
pois o serviço do Compose já ocupa a porta 5000.

#### Orquestração visual com Airflow

O profile opcional `orchestration` oferece estado e logs por etapa, retries, histórico e
execução manual pela interface, sem substituir o MLflow:

```powershell
podman compose --profile orchestration up -d --build airflow
```

Abra `http://127.0.0.1:8080`, selecione o DAG `datathon_pipeline_m1_m4` e use **Trigger**.
O DAG executa `M1 traduzir → M2 preparar → M3 treinar → M4 avaliar`; M3 e M4
continuam registrando parâmetros, métricas e artefatos em `http://mlflow:5000`. Ele é
manual (`schedule=None`), limita-se a um run ativo e tenta novamente uma vez cada tarefa.

Também é possível dispará-lo pela CLI:

```powershell
podman compose --profile orchestration exec airflow `
  airflow dags trigger datathon_pipeline_m1_m4
```

Depois de um run bem-sucedido, recarregue os consumidores dos artefatos:

```powershell
podman compose run --rm mlflow-snapshot
podman compose restart api process-exporter
```

O Airflow usa standalone + LocalExecutor + SQLite no volume `airflow-data`; essa escolha
é deliberadamente local e não representa uma topologia de produção. Como a porta está
restrita ao loopback, o ambiente local permite acesso administrativo sem login por padrão.
Defina `AIRFLOW_LOCAL_ALL_ADMINS=false` para exigir o usuário `admin`; a senha gerada fica
em `/opt/airflow/simple_auth_manager_passwords.json.generated` dentro do contêiner.

As portas são vinculadas somente ao loopback do host:

| Interface | Endereço padrão | Finalidade |
|---|---|---|
| API/Swagger | `http://127.0.0.1:8000/docs` | recomendação, feedback e probes |
| Grafana | `http://127.0.0.1:3000` | dashboards de API e processo de ML |
| Prometheus | `http://127.0.0.1:9090` | consultas, targets e regras |
| Alertmanager | `http://127.0.0.1:9093` | alertas ativos e silêncios locais |
| MLflow | `http://127.0.0.1:5000` | runs, métricas e artefatos M3/M4 |
| Airflow (profile opcional) | `http://127.0.0.1:8080` | DAG, tarefas, retries e logs de execução |

O login inicial do Grafana vem de `.env.example`; altere `GRAFANA_ADMIN_PASSWORD` no `.env` antes de compartilhar o ambiente. Loki, Tempo, Alloy, OpenTelemetry Collector e o exportador do processo permanecem apenas na rede interna do Compose. Verifique rapidamente o ambiente:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:9090/-/ready
Invoke-RestMethod http://127.0.0.1:3000/api/health
Invoke-RestMethod http://127.0.0.1:5000/health
```

Para acompanhar ou encerrar os serviços:

```powershell
podman compose logs -f api prometheus grafana
podman compose --profile orchestration down
```

O profile pode ser omitido se o Airflow não estiver ativo. O comando preserva os volumes.
Acrescentar `-v` também apaga métricas, traces, logs internos, estado do Airflow e a cópia
containerizada do banco MLflow; use-o somente quando quiser reinicializar todo o ambiente.
O runbook completo está em [`observability/README.md`](observability/README.md).

### Executar diretamente no Python (alternativa sem contêiner)

Use Python 3.14, crie e ative um ambiente virtual e instale as versões fixadas:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Adapte os caminhos dos artefatos registrados no SQLite ao diretório do clone atual:

```powershell
python scripts/rebase_mlflow_paths.py
```

O MLflow persiste URIs absolutas no banco. Esse comando altera somente `artifact_location` e `artifact_uri` em `mlflow.db`, preservando runs, parâmetros, métricas e artefatos. Use `python scripts/rebase_mlflow_paths.py --check-only` para verificar o vínculo depois da adaptação. É normal que o banco versionado apareça como modificado localmente quando o clone estiver em outro caminho.

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

Valide lint e imports:

```powershell
python -m ruff check .
```

Execute o notebook de análise:

```powershell
jupyter notebook notebooks/01_EDA.ipynb
```

Execute o notebook de preparação:

```powershell
jupyter notebook notebooks/02_preparation.ipynb
```

Treine os baselines e registre o experimento no MLflow:

```powershell
python -m src.models.train_propensity --config configs/modeling.yaml
```

Execute o Thompson Sampling, as 30 seeds do replay e o tracking do M4:

```powershell
python -m src.evaluation.replay --config configs/policy.yaml
```

Abra a interface local do MLflow:

```powershell
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000 --workers 1
```

No Windows, mantenha `--workers 1`: o multiprocessamento usado pelo servidor com o valor
padrão pode falhar ao compartilhar o socket e gerar `WinError 10022`. O aviso de que o
backend de jobs não suporta Windows afeta apenas a execução de MLflow Jobs; tracking,
artefatos e a interface continuam disponíveis.

Execute o notebook do M3:

```powershell
jupyter notebook notebooks/03_modeling_and_baseline.ipynb
```

Execute o notebook de evidências do M4:

```powershell
jupyter notebook notebooks/04_policy_evaluation.ipynb
```

Execute os cinco casos do golden set:

```powershell
python -m src.evaluation.golden_set --config configs/api.yaml
```

Inicie a API com a política aprovada:

```powershell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000/docs` ou envie o exemplo versionado:

```powershell
curl.exe -X POST http://127.0.0.1:8000/v1/recommendations `
  -H "Content-Type: application/json" `
  --data-binary "@examples/recommendation_request.json"
```

Para uma demonstração isolada da política candidata ainda não aprovada, em outro processo:

```powershell
$env:DATATHON_POLICY_MODE = "adaptive_demo"
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8001
```

Esse modo não promove a política e persiste seu posterior em `artifacts/serving/thompson_runtime_state.json`. Remova a variável antes de iniciar o serving padrão.

Execute o notebook do M5:

```powershell
jupyter notebook notebooks/05_golden_set_and_api.ipynb
```

## Demo Day e encerramento

O pitch deve durar no máximo cinco minutos: problema e decisão; dados e vazamento removido; baseline e Thompson Sampling; lift, incerteza e cobertura; API com recomendação e feedback; MLflow, AWS, governança e limitações. A demonstração padrão mantém o baseline aprovado; o modo `adaptive_demo` mostra a candidata sem promovê-la automaticamente.

**Vídeo final:** pendente de gravação e publicação pelo Grupo 80. Substituir esta frase pelo link público antes da submissão.

### Próximos passos

1. registrar os nomes dos responsáveis por negócio, técnica e risco de modelo;
2. aprovar ou rejeitar formalmente a política candidata após revisão por par;
3. validar a janela de recompensa, consentimento e regras de elegibilidade;
4. executar experimento online controlado com logging da propensão;
5. definir SLOs a partir de tráfego representativo e automatizar drift/disparidade;
6. gravar o vídeo, executar a checklist final e criar a tag de entrega.

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

## Checklist M3

- [x] baseline determinístico ajustado somente no treino;
- [x] canal, suporte, conversão e intervalo de confiança documentados;
- [x] fallback determinístico para indisponibilidade do melhor braço;
- [x] replay factual reporta recompensa e cobertura juntas;
- [x] DummyClassifier treinado como referência mínima;
- [x] Regressão Logística com preprocessing interno e serializado;
- [x] `duration`, campanha bruta, identificador e auditoria ausentes do modelo;
- [x] seleção por PR-AUC na validação;
- [x] limiar selecionado por F1 na validação e congelado no teste;
- [x] PR-AUC, ROC-AUC, Brier, calibração e matriz de confusão reportados;
- [x] avaliação pós-predição em 34 fatias agregadas com suporte mínimo;
- [x] modelo supera Dummy em PR-AUC e Brier na validação;
- [x] inferência smoke executada com o pipeline persistido;
- [x] parâmetros, métricas e artefatos registrados no MLflow com SQLite;
- [x] notebook executável do kernel limpo;
- [x] testes unitários e de integração aprovados.

## Checklist M4

- [x] Thompson Sampling Beta-Bernoulli com prior `Beta(1,1)`;
- [x] segmentos formados apenas por contexto pré-decisão e suporte mínimo;
- [x] fallback global para segmentos esparsos;
- [x] seed controlada e 30 seeds usadas sem seleção oportunista;
- [x] atualização restrita ao braço factual dos eventos aceitos;
- [x] feedback duplicado rejeitado por `feedback_id`;
- [x] estado versionado, restaurável e persistido atomicamente;
- [x] baseline e política adaptativa avaliadas na mesma sequência;
- [x] recompensa, cobertura, escolhas, exploração e lift reportados;
- [x] intervalo bootstrap de 95% e dispersão entre seeds reportados;
- [x] regret omitido com justificativa contrafactual explícita;
- [x] política `1.1.0` passou o gate estatístico em validação e teste e foi marcada como candidata;
- [x] parâmetros, métricas, tags e artefatos registrados no MLflow;
- [x] notebook de evidências e testes automatizados adicionados.

## Checklist M5

- [x] cinco casos sintéticos estáveis e revisados por humano;
- [x] sucesso, fracasso, primeiro contato, desconhecido e braço indisponível cobertos;
- [x] atributos de auditoria ausentes do payload da política;
- [x] FastAPI com recomendações, feedback, health, ready, metrics e Swagger;
- [x] schemas Pydantic com enums, faixas de referência e campos extras bloqueados;
- [x] política fixa mantida até aprovação humana explícita da candidata do M4;
- [x] fallback seguro quando o estado adaptativo está ausente;
- [x] serviço indisponível com `503` quando o rollback obrigatório não carrega;
- [x] SQLite transacional guarda somente contexto mínimo;
- [x] feedback idempotente, conflito terminal e ID desconhecido cobertos;
- [x] concorrência básica do feedback validada com oito threads;
- [x] estado adaptativo isolado e atualização restrita ao modo demonstrativo;
- [x] logs estruturados sem payload e métricas técnicas agregadas;
- [x] referências de qualidade/recompensa derivadas dos artefatos versionados;
- [x] SLO não definido enquanto não existe amostra de latência representativa;
- [x] exemplos de execução, notebook e testes de contrato adicionados.

## Checklist M6

- [x] arquitetura AWS consolidada no README;
- [x] serving, estado, feedback, treino e MLflow separados no diagrama;
- [x] IAM, KMS, Secrets Manager, WAF e CloudTrail documentados;
- [x] logs, métricas, drift, alertas e rollback descritos;
- [x] resumo executivo e impacto com limitações junto às métricas;
- [x] comandos de teste e lint documentados;
- [x] CI em Linux valida dependências, lint, testes e hash do snapshot;
- [ ] nomes individuais registrados e política candidata aprovada ou rejeitada por humano;
- [ ] vídeo público de até cinco minutos vinculado no README;
- [ ] tag final de entrega criada após a validação independente.
