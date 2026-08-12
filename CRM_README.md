# CRM Simulator — requisitos, premissas e execução

Este módulo transforma a demonstração do Datathon em uma história próxima de um sistema real: uma pessoa operadora abre uma oportunidade de contato no CRM, solicita o melhor canal ao motor de recomendações e registra o resultado observado.

O CRM é formado por dois produtos independentes:

- `crm-api`: API Java responsável pelas regras de negócio, persistência e integração com o motor de recomendação;
- `crm-web`: aplicação Angular com Fluent 2, servida por Nginx e integrada à `crm-api` pelo proxy `/api`.

A API Python existente continua sendo o motor de decisão. Ela não foi duplicada dentro do Java.

## Requisitos funcionais

1. Importar as oportunidades do conjunto de teste processado na primeira inicialização do banco.
2. Listar e consultar oportunidades sem expor o canal ou o resultado histórico.
3. Permitir alterar autorização de contato, bloqueio de contato e canais elegíveis.
4. Solicitar uma recomendação contextual à API Python.
5. Persistir a recomendação com política, modelo, evidências e data da decisão.
6. Registrar feedback manual terminal e encaminhá-lo ao motor de recomendação.
7. Simular o resultado histórico apenas quando a ação recomendada for igual à ação realmente observada.
8. Retornar `COUNTERFACTUAL_UNKNOWN` quando as ações forem diferentes, sem inventar reward e sem alimentar o modelo.
9. Expor contrato OpenAPI e Swagger UI na raiz da API.
10. Expor saúde e métricas Prometheus para operação local.
11. Oferecer uma fila responsiva para busca, paginação, elegibilidade, recomendação, feedback e simulação histórica.
12. Versionar configurações operacionais, ativá-las sem novo deploy e manter trilha de auditoria.
13. Avaliar política, rollout, kill switch e aprendizado pelo SDK OpenFeature com `flagd` open source.

## Premissas de produto e de dados

- Uma linha do dataset representa uma **oportunidade histórica de contato**, não um cadastro completo de cliente. Por isso a API usa identificadores sintéticos como `OP-000003` e não inventa nome, CPF, telefone ou renda.
- `canal_contato` e `resultado` são atributos posteriores à decisão. Eles ficam no servidor somente para auditoria e simulação e nunca são enviados no contexto do modelo.
- O dataset é observacional. A API informa explicitamente `causalClaim: false`; uma associação histórica não é apresentada como efeito causal.
- O feedback é terminal: uma recomendação não pode receber dois resultados diferentes.
- O Java é o dono das regras e do histórico do simulador. O Python é o dono da política de recomendação e de seu aprendizado.
- PostgreSQL e a API são executados por containers no mesmo Compose do projeto.
- As credenciais padrão servem apenas para desenvolvimento local e devem ser substituídas fora desse ambiente.
- `crm_owner` aplica migrations; `crm_app` possui somente os privilégios DML necessários à execução.
- Falha ou indisponibilidade do `flagd` nunca promove a candidata: o SDK usa defaults que mantêm a baseline fixa e o aprendizado desligado.

## Arquitetura

```text
crm-web (Angular + Nginx) :80
        |
        v
crm-api :8081  ----->  PostgreSQL 18 :5432
   |                         |
   | publica flags          | histórico imutável
   v                         |
flagd :8013 <---------------+
   |
   | OpenFeature SDK
   v
API de recomendações FastAPI :8000 <----- crm-api
```

O código Java segue **package by feature**:

```text
br.com.fiap._mlet.datathon.grupo101.crm.api
├── opportunity
│   ├── dto
│   └── seed
├── recommendation
│   ├── client
│   └── dto
├── configuration
│   └── dto
└── shared
    ├── config
    ├── error
    └── web
```

Cada feature contém seu controller, serviço, repositório e contratos. `shared` mantém somente preocupações realmente transversais.

## Modelo relacional e normalização

O schema `crm` é criado e versionado pelo Flyway. A aplicação usa SQL explícito por meio de Spring JDBC; nenhuma criação automática de tabelas ocorre na inicialização.

| Tabela | Responsabilidade |
|---|---|
| `contact_channel` | Catálogo canônico dos canais `celular` e `telefone` |
| `contact_opportunity` | Contexto da oportunidade, permissões e atributos históricos protegidos |
| `opportunity_eligible_channel` | Relação N:N entre oportunidade e seus canais elegíveis |
| `recommendation` | Decisão retornada pelo motor, política, modelo e evidências |
| `recommendation_feedback` | Resultado terminal 1:1 de uma recomendação |
| `runtime_configuration` | Versões imutáveis das flags, autor, motivo e instante de ativação |

As três formas normais são atendidas desta maneira:

- **1FN:** cada coluna contém um valor atômico; a lista de canais elegíveis não é armazenada em array ou texto, mas em uma relação própria.
- **2FN:** a tabela associativa tem chave composta `(opportunity_id, channel_id)` e não possui atributo dependente de apenas parte dessa chave.
- **3FN:** descrição de canal existe somente em `contact_channel`; feedback depende da recomendação, e não repete oportunidade, política ou modelo. Cada configuração é um snapshot imutável cujos atributos dependem apenas de sua versão. Não há dependências transitivas persistidas.

Além da normalização, chaves estrangeiras têm ações explícitas, identificadores usam `GENERATED ALWAYS AS IDENTITY`, valores de domínio possuem `CHECK`, códigos naturais são únicos e as consultas principais têm índices dedicados.

Há uma exceção observada que não é escondida: uma única linha de teste possui `previousCampaignContacts = 7`, enquanto o contrato do motor foi delimitado pelo treino até `6`. Ela é preservada no CRM para fidelidade histórica, mas pode ser rejeitada pelo motor como fora da distribuição conhecida.

## Contrato HTTP

Com a aplicação em execução:

- Swagger UI: <http://localhost:8081/>
- OpenAPI JSON: <http://localhost:8081/v3/api-docs>
- Saúde: <http://localhost:8081/actuator/health>
- Métricas: <http://localhost:8081/actuator/prometheus>
- Frontend Angular: <http://localhost/>

A readiness da API combina estado da aplicação, PostgreSQL e `/ready` do motor de recomendações; o container só fica saudável quando as três partes estão disponíveis.

Endpoints do domínio:

| Método | Caminho | Uso |
|---|---|---|
| `GET` | `/api/v1/opportunities` | Lista paginada; aceita `search`, `page` e `size` |
| `GET` | `/api/v1/opportunities/{id}` | Detalhe sem atributos históricos protegidos |
| `PATCH` | `/api/v1/opportunities/{id}/eligibility` | Permissões e canais elegíveis |
| `POST` | `/api/v1/opportunities/{id}/recommendations` | Solicita uma nova decisão |
| `GET` | `/api/v1/opportunities/{id}/recommendations` | Histórico de decisões da oportunidade |
| `GET` | `/api/v1/recommendations/{uuid}` | Detalhe de uma decisão |
| `POST` | `/api/v1/recommendations/{uuid}/feedback` | Feedback manual terminal |
| `POST` | `/api/v1/recommendations/{uuid}/simulate-historical` | Simulação histórica factual |
| `GET` | `/api/v1/configurations/active` | Snapshot ativo e versão publicada |
| `GET` | `/api/v1/configurations/history` | Histórico imutável de ativações |
| `POST` | `/api/v1/configurations/activate` | Ativa uma nova versão com controle de concorrência |

O endpoint interno `/internal/openfeature/flags.json` não é publicado pelo Nginx. O `flagd` o consulta pela rede privada do Compose a cada dois segundos e usa `ETag`/`If-None-Match` para evitar recargas desnecessárias. A API Python avalia as flags com o SDK OpenFeature e inclui em cada `evidence` a versão, origem, modo solicitado, alocação e motivo de fallback.

## Como demonstrar uma mudança em tempo real

1. Abra <http://localhost/configuracoes> e confirme a versão ativa.
2. Escolha `Adaptativa de demonstração`, defina o tráfego e identifique o experimento.
3. Salve o rascunho para mostrar que isso ainda não altera o runtime.
4. Informe operador e motivo e use **Ativar configuração**.
5. Aguarde até dois segundos e gere uma recomendação; o evidence mostra a nova versão OpenFeature.
6. Para rollback, escolha `Baseline aprovada` ou acione o kill switch e publique outra versão.

A alocação determinística usa o identificador sintético da oportunidade, o nome do experimento e um hash. Assim, a mesma oportunidade permanece no mesmo grupo durante o rollout, sem expor regras ou dados ao navegador.

Erros seguem o formato `application/problem+json` (RFC 9457/Problem Details).

## Execução com Podman Compose

Na raiz do repositório, copie as variáveis locais se ainda não houver um `.env`:

```powershell
Copy-Item .env.example .env
```

O caminho recomendado compila todas as imagens e deixa CRM, motor de recomendações,
Airflow e observabilidade online, aguardando a saúde de cada serviço:

```powershell
.\scripts\start-all.ps1
```

Para reaproveitar imagens já compiladas, use `.\scripts\start-all.ps1 -SkipBuild`. Para
subir a stack sem o Airflow, acrescente `-WithoutAirflow`.

Suba o motor Python, o PostgreSQL, a API Java e o frontend:

```powershell
podman compose up -d --build flagd api crm-postgres crm-api crm-web
```

O Compose respeita a ordem de inicialização: primeiro o PostgreSQL fica saudável, depois o Flyway aplica as migrations e a API importa `data/processed/test.csv` caso ainda não existam oportunidades.

Para subir também toda a observabilidade existente:

```powershell
podman compose up -d --build
```

Consulte os logs:

```powershell
podman compose logs -f crm-api
```

Confirme a versão real do servidor e a quantidade importada:

```powershell
podman compose exec crm-postgres psql -U crm_app -d crm -c "SHOW server_version;"
podman compose exec crm-postgres psql -U crm_app -d crm -c "SELECT count(*) FROM crm.contact_opportunity;"
```

O banco é persistido no volume nomeado `crm-postgres-data`. Um `podman compose down` preserva os dados; não use `down -v` se quiser manter o histórico.

## Execução Java fora do container

Para desenvolvimento do backend, mantenha apenas o banco e o motor em containers:

```powershell
podman compose up -d crm-postgres api
Set-Location crm-api
.\mvnw.cmd spring-boot:run
```

Os padrões locais usam PostgreSQL em `localhost:5433` e o motor em `localhost:8000`. Todas as configurações podem ser sobrescritas pelas variáveis documentadas em `.env.example` e `application.yml`.

## Critérios de aceite deste incremento

- build Java reproduzível em container;
- migrations executadas com sucesso em PostgreSQL 18;
- 6.177 oportunidades importadas de forma idempotente;
- Swagger carregando em `/`;
- recomendação persistida sem canal/reward histórico no payload enviado ao modelo;
- simulação factual gerando feedback e simulação contrafactual retornando estado desconhecido;
- métricas da API disponíveis para o Prometheus do projeto;
- flags sincronizadas pelo `flagd`, com métricas no Prometheus e fallback seguro no motor;
- ativação versionada, bloqueio de rascunho obsoleto e rollback sem reiniciar containers.

O `crm-web` permanece como projeto Angular independente e agora também possui uma imagem reproduzível. O Nginx encaminha `/api/*` para a `crm-api`, evitando que o navegador acesse diretamente o PostgreSQL ou a API Python.
