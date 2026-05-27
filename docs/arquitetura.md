# Arquitetura — Assistente Virtual Médico Hospitalar

## Visão Geral

O sistema é uma **API REST assíncrona** (FastAPI) que combina RAG (*Retrieval-Augmented Generation*) com um orquestrador de fluxo clínico. Toda resposta é rastreável a fontes (artigos PubMedQA ou protocolos internos) e acompanhada de avisos de segurança padronizados.

---

## Camadas

```
┌─────────────────────────────────────────────────┐
│                  HTTP (FastAPI)                  │
│  POST /v1/sessao  POST /v1/consulta              │
│  POST /v1/conduta POST /v1/pacientes/*/tratamento│
│  GET  /v1/pacientes/*/exames-pendentes           │
├─────────────────────────────────────────────────┤
│              Orquestrador Clínico                │
│   NLU → esclarecimento → dispatch → avisos       │
├──────────────┬──────────────────────────────────┤
│   Motor RAG  │       Repositório de Pacientes    │
│ FAISS+OpenAI │       SQLAlchemy async (SQLite/PG)│
├──────────────┴──────────────────────────────────┤
│              Serviços de Domínio                 │
│  ordenação · emergência · interações · contrainds│
│  MeSH mapper · validador de prontuário           │
├─────────────────────────────────────────────────┤
│                   Worker Async                   │
│         AtualizadorExames (ciclo de 10s)         │
└─────────────────────────────────────────────────┘
```

---

## Módulos em Detalhe

### `app/api/` — Camada HTTP

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Fábrica da app, registra rotas e handlers de exceção |
| `deps.py` | DI: lifespan (carrega LLM, FAISS, protocolos na inicialização), `get_orchestrador`, `get_session_store` |
| `routes/sessao.py` | `POST /v1/sessao` → cria `SessaoMedico` com UUID e armazena no store em memória |
| `routes/consulta.py` | `POST /v1/consulta` → delega ao orquestrador (fluxo NLU completo) |
| `routes/conduta.py` | `POST /v1/conduta` → constrói `NLUResult` diretamente e chama `handle_sugestao_conduta` |
| `routes/exames.py` | `GET /v1/pacientes/{id}/exames-pendentes` → chama `handle_verificacao_exames` |
| `routes/tratamento.py` | `POST /v1/pacientes/{id}/tratamento` → chama `handle_sugestao_tratamento` |

**Session store** é um `dict` em memória (`app.state` / módulo `deps.py`). Documentado para migração futura a Redis em implantações multi-instância.

---

### `app/nlu/` — Interpretação de Intenção

- **`InterpretadorNLU`** — usa `ChatOpenAI` + `ChatPromptTemplate` para classificar a pergunta em uma das 5 intenções: `CONSULTA_CLINICA`, `SUGESTAO_CONDUTA`, `VERIFICACAO_EXAMES`, `SUGESTAO_TRATAMENTO`, `INTENCAO_DESCONHECIDA`. Se o JSON retornado for inválido ou a confiança for inferior a 0.5, cai automaticamente para `INTENCAO_DESCONHECIDA`.
- **`GeradorEsclarecimento`** — quando a intenção é desconhecida, gera perguntas objetivas de esclarecimento (máx. 3 por ciclo, controlado por `SessaoMedico.contador_esclarecimentos`).

---

### `app/orchestrator/` — Núcleo de Negócio

- **`OrquestradorClinico`** (`fluxo.py`) — coordena todos os componentes. Recebe a pergunta, passa pelo NLU e despacha para o handler correto:
  - `handle_consulta_clinica` — RAG direto, retorna resposta com fontes.
  - `handle_sugestao_conduta` — RAG + mapeamento MeSH + ordenação (protocolos → artigos por ano) + detecção de emergência.
  - `handle_verificacao_exames` — consulta o banco, formata lista de exames pendentes.
  - `handle_sugestao_tratamento` — valida prontuário, RAG, verifica interações e contraindicações. Propaga `InteractionServiceUnavailableError` sem suprimir.
- **`aplicar_avisos`** (`avisos.py`) — pós-processador aplicado a toda resposta: injeta `APOIO_DECISAO` (sempre), `BAIXA_CONFIANCA`, `EVIDENCIA_INCONCLUSIVA`, `RACIOCINIO_NECESSARIO`, `EMERGENCIA`, `FORA_PROTOCOLO` conforme o contexto. Deduplica por tipo.

---

### `app/rag/` — Recuperação e Geração

- **`MotorRAG`** (`engine.py`) — usa `FAISS` como vector store e `ChatOpenAI (gpt-4o)` como gerador. Suporta filtros por `MESHES`, exclusão por `final_decision` e limite de documentos. A confiança geral é calculada como média dos scores de relevância dos documentos recuperados.
- **`ingest_pubmedqa.py`** — parser dos JSONs PubMedQA → `list[Document]` LangChain com metadados (`id`, `YEAR`, `final_decision`, `reasoning_required_pred`, `MESHES`).
- **`ingest_protocolos.py`** — parser dos JSONs de protocolos → `list[(Protocolo, texto)]` + `list[Document]`.

---

### `app/services/` — Regras de Domínio

| Serviço | Função |
|---|---|
| `ordenacao.py` | Protocolos primeiro (por cobertura do quadro clínico desc), artigos depois (por `YEAR` desc), máx. 5 protocolos |
| `emergencia.py` | Varredura dos `termos_emergencia` dos protocolos contra o quadro clínico (regex com fronteira de palavra, case/acento-insensitive) |
| `mesh_mapper.py` | LLM mapeia termos clínicos livres para descritores MeSH padronizados; resultado em cache in-memory |
| `interacoes.py` | Lê `data/interacoes.json`, cruza tratamento sugerido × medicamentos em uso; retry exponencial (1s → 2s → 4s); levanta `InteractionServiceUnavailableError` após 3 falhas |
| `contraindicacoes.py` | Cruza tratamento com alergias, comorbidades e histórico clínico do prontuário (e contraindicações dos protocolos) |
| `prontuario_validator.py` | Valida presença dos 3 campos obrigatórios (`diagnostico_ativo`, `medicamentos_em_uso`, `alergias`) antes de sugerir tratamento |

---

### `app/db/` — Persistência

- **ORM** SQLAlchemy 2.0 async com 4 tabelas: `pacientes`, `prontuarios`, `exames`, `medicamentos`.
- **`RepositorioPacientes`** — `buscar_prontuario`, `listar_exames_pendentes`, `buscar_medicamentos_em_uso`. Erros de banco sobem como `DatabaseUnavailableError`.
- Desenvolvimento: SQLite (`sqlite+aiosqlite:///./data/app.db`). Produção: PostgreSQL (`asyncpg`).

---

### `app/workers/` — Background

- **`AtualizadorExames`** — loop `asyncio` com intervalo de 10 s. A cada ciclo: busca exames `Em Análise`, chama `VerificadorResultado(numero_prontuario, nome) → bool`, atualiza para `Concluído`. Falha individual por exame não interrompe o ciclo. Garante atualização em ≤ 60 s após disponibilização do resultado (Req 3.5).

---

### `app/core/` — Infraestrutura Transversal

| Módulo | Função |
|---|---|
| `config.py` | `Settings` Pydantic com leitura automática de `.env` via `pydantic-settings` |
| `exceptions.py` | Hierarquia de erros (`BaseAppError` → 5 subclasses) com mapeamento automático para HTTP status e payload `{"error": {"code": ..., "message": ...}}` |
| `resilience.py` | Decorador `@with_timeout(seconds)` (converte `TimeoutError` → `PLNTimeoutError`) + `CircuitBreaker` (3 falhas → abre 30 s, transição via estado semi-aberto) |
| `logging.py` | JSON estruturado em produção, texto legível em desenvolvimento |

---

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11+ |
| Framework Web | FastAPI + Uvicorn |
| LLM | OpenAI `gpt-4o` via LangChain `ChatOpenAI` |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector Store | FAISS (busca vetorial local) |
| ORM | SQLAlchemy 2.0 async |
| Banco (dev) | SQLite via `aiosqlite` |
| Banco (prod) | PostgreSQL via `asyncpg` |
| Validação | Pydantic v2 |
| Testes | pytest + pytest-asyncio |

---

## Cobertura de Testes — 376 testes, 0 falhas

| Camada | Arquivos | Foco |
|---|---|---|
| `tests/unit/` (18 arquivos) | Cada módulo isolado com mocks | Lógica pura de cada serviço, NLU, RAG, worker |
| `tests/integration/` (7 arquivos) | TestClient + orquestrador mockado | Contratos HTTP, status codes, payloads |
| `tests/e2e/` (4 arquivos) | TestClient ponta a ponta por requisito | AC 1.x a 4.x do `requirements.md` |
| `tests/properties/` (1 arquivo) | Parametrizado sobre múltiplos cenários | 15 propriedades de correção do `design.md` |

---

## Diagrama de Dependências entre Módulos

```
app/main.py
    └── app/api/deps.py (lifespan, DI)
            ├── app/nlu/interpretador.py
            │       └── ChatOpenAI (LangChain)
            ├── app/nlu/esclarecimento.py
            │       └── ChatOpenAI (LangChain)
            ├── app/rag/engine.py
            │       ├── FAISS (LangChain Community)
            │       └── ChatOpenAI (LangChain)
            ├── app/orchestrator/fluxo.py
            │       ├── app/orchestrator/avisos.py
            │       ├── app/services/ordenacao.py
            │       ├── app/services/emergencia.py
            │       ├── app/services/mesh_mapper.py
            │       ├── app/services/interacoes.py
            │       ├── app/services/contraindicacoes.py
            │       └── app/services/prontuario_validator.py
            ├── app/db/repositories/pacientes.py
            │       └── app/db/session.py (AsyncSession)
            └── app/workers/exames_updater.py
                    └── app/db/session.py (async_sessionmaker)
```

---

## Decisões Arquiteturais Relevantes

| Decisão | Escolha | Justificativa |
|---|---|---|
| Orquestrador instanciado por requisição | Objeto leve montado no `Depends` | `RepositorioPacientes` requer `AsyncSession` por request; singletons pesados ficam no `app.state` |
| Session store em memória | `dict` no módulo `deps.py` | Simples para instância única; documentado para migração a Redis |
| NLU bypassed em `/v1/conduta` e `/v1/tratamento` | `NLUResult` construído diretamente na rota | Comportamento determinístico; evita re-classificação de texto já estruturado |
| Artigos `final_decision=no` excluídos no RAG | `excluir_decisao_final=["no"]` | Req 4.3: evidência contrária não aparece como suporte a tratamentos |
| Avisos como pós-processador | `aplicar_avisos()` separado do handler | Regras de sinalização desacopladas da lógica de negócio; testáveis de forma independente |
| Worker de exames como `asyncio.Task` | `asyncio.create_task` no lifespan | Sem thread extra; cancela limpo com `CancelledError` no shutdown |
