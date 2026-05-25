# Tasks — Assistente Virtual Médico Hospitalar

Este documento divide a implementação do sistema em tarefas sequenciais e rastreáveis. Cada tarefa referencia os requisitos (`requirements.md`) e os componentes/propriedades de design (`design.md`) que valida.

Convenções:
- **Refs Req.**: requisitos atendidos pela tarefa.
- **Refs Design**: seções/componentes/propriedades do `design.md`.
- **Entregáveis**: artefatos concretos produzidos (módulos, modelos, testes).
- **DoD**: definition of done — critérios objetivos para considerar a tarefa concluída.

---

## Fase 0 — Fundação do Projeto

### Task 0.1 — Estrutura inicial do repositório e gerenciamento de dependências
- **Refs Design**: Technology Stack, Dependências
- **Entregáveis**:
  - Estrutura de diretórios: `app/`, `app/api/`, `app/core/`, `app/db/`, `app/rag/`, `app/services/`, `app/models/`, `tests/`.
  - `requirements.txt` com versões fixadas conforme `design.md`.
  - `.env.example` com chaves: `OPENAI_API_KEY`, `DATABASE_URL`, `CONFIDENCE_THRESHOLD`, `PLN_TIMEOUT_SECONDS`.
  - `README.md` com instruções de setup local.
- **DoD**: `pip install -r requirements.txt` executa sem erro; `uvicorn app.main:app` sobe um stub do FastAPI.

### Task 0.2 — Configuração centralizada e carregamento de variáveis
- **Refs Req.**: 1.6, 1.11
- **Entregáveis**:
  - Módulo `app/core/config.py` com `Settings` (Pydantic `BaseSettings`) expondo: limiar de confiança, timeout de PLN, modelo LLM, modelo de embeddings, caminho do índice FAISS, URL do banco.
- **DoD**: testes verificam carga via `.env` e valores default seguros.

### Task 0.3 — Logging estruturado e tratamento global de exceções
- **Refs Req.**: 1.10, 1.11, 3.3, 4.7
- **Entregáveis**:
  - `app/core/logging.py` (JSON logs).
  - `app/core/exceptions.py` com hierarquia: `BaseAppError`, `KnowledgeBaseUnavailableError`, `PLNTimeoutError`, `PatientNotFoundError`, `InteractionServiceUnavailableError`, `DatabaseUnavailableError`.
  - Handlers FastAPI mapeando cada exceção a códigos HTTP e mensagens em pt-BR.
- **DoD**: testes de integração disparam cada exceção e validam payload de erro.

---

## Fase 1 — Modelagem de Dados e Persistência

### Task 1.1 — Modelos Pydantic do domínio
- **Refs Design**: Data Models
- **Entregáveis**: `app/models/domain.py` com:
  - `EntradaPubMedQA`, `Protocolo`
  - `Prontuario`, `Exame` (com enum `StatusExame`), `Medicamento`
  - `RespostaClinica`, `FonteReferencia`, `Aviso` (com enum `TipoAviso`)
  - `SessaoMedico`
- **DoD**: validações Pydantic rejeitam valores inválidos (ex.: `final_decision` fora de `{yes,no,maybe}`).

### Task 1.2 — Modelos SQLAlchemy e migrações
- **Refs Req.**: 3.1, 3.2, 4.1, 4.5, 4.6, 4.8
- **Refs Design**: Repositório de Pacientes, tabelas
- **Entregáveis**:
  - `app/db/models.py`: tabelas `pacientes`, `prontuarios`, `exames`, `medicamentos`.
  - `app/db/session.py`: engine async + sessionmaker.
  - Script `scripts/init_db.py` criando o schema e populando dados de exemplo (>= 3 pacientes, exames variados, medicamentos ativos).
- **DoD**: schema criado em SQLite local; dados de seed verificáveis via SQL.

### Task 1.3 — Repositório de Pacientes
- **Refs Req.**: 3.1, 3.3, 4.1, 4.5, 4.6
- **Refs Design**: Componente 4
- **Entregáveis**: `app/db/repositories/pacientes.py` com `RepositorioPacientes` async:
  - `buscar_prontuario(numero) -> Prontuario | None`
  - `listar_exames_pendentes(numero) -> list[Exame]` (apenas `Solicitado`, `Coletado`, `Em Análise`)
  - `buscar_medicamentos_em_uso(numero) -> list[str]`
- **DoD**: testes unitários com SQLite in-memory cobrindo: paciente inexistente, sem exames pendentes, com mix de status.

---

## Fase 2 — Base de Conhecimento e Motor RAG

### Task 2.1 — Ingestão da Base PubMedQA
- **Refs Req.**: 1.2, 1.3, 1.4
- **Refs Design**: Motor RAG, Data Models
- **Entregáveis**:
  - `app/rag/ingest_pubmedqa.py`: lê JSON PubMedQA → normaliza para `EntradaPubMedQA` → gera `Document` LangChain com metadata (`id`, `MESHES`, `final_decision`, `reasoning_required_pred`, `YEAR`).
  - Persistência do índice FAISS em disco.
- **DoD**: índice construído e recarregável; sanity check de busca semântica retorna documentos esperados.

### Task 2.2 — Ingestão de Protocolos Internos
- **Refs Req.**: 2.1, 2.2, 2.5
- **Entregáveis**:
  - Formato JSON/YAML dos protocolos definido (`docs/protocolo-schema.md`).
  - `app/rag/ingest_protocolos.py`: lê arquivos de protocolo → cria `Document` com metadata (`tipo=protocolo`, `vigente`, `nivel_evidencia`, `condicoes`, `contraindicacoes`, `termos_emergencia`).
  - Conjunto mínimo de 3 protocolos de exemplo (incluindo um com termo de emergência).
- **DoD**: protocolos indexados no mesmo vector store, recuperáveis por filtro `tipo=protocolo`.

### Task 2.3 — Motor RAG com filtros de metadados
- **Refs Req.**: 1.1, 1.2, 1.3, 1.4, 4.3
- **Refs Design**: Componente 2, Propriedades 1, 2, 3, 4
- **Entregáveis**: `app/rag/engine.py`:
  - `recuperar_e_gerar(consulta, filtros_mesh, excluir_decisao_final, limite) -> RespostaRAG`
  - Pipeline LangChain: `FAISS.as_retriever(search_kwargs={"filter": ...})` + `ChatPromptTemplate` + `ChatOpenAI(temperature=0.1)` + `StructuredOutputParser`.
  - Cálculo de `confianca_geral` a partir dos scores do retriever.
- **DoD**: testes verificam que (a) artigos `final_decision="no"` são excluídos quando solicitado; (b) `maybe` retorna com flag de inconclusividade; (c) `reasoning_required` traz `LONG_ANSWER`.

### Task 2.4 — Serviço de Ordenação de Condutas
- **Refs Req.**: 2.4, 2.6
- **Refs Design**: Componente 3, Propriedade 5
- **Entregáveis**: `app/services/ordenacao.py` com `ordenar_condutas(protocolos, artigos, max_protocolos=5)`:
  - Protocolos primeiro, ordenados por nº de condições aplicáveis correspondentes (desc).
  - Artigos em seguida, ordenados por `YEAR` (desc).
  - Limite de 5 protocolos.
- **DoD**: testes unitários cobrindo empates, lista vazia de protocolos e mais de 5 protocolos.

### Task 2.5 — Detecção de emergência
- **Refs Req.**: 2.5
- **Refs Design**: Propriedade 15
- **Entregáveis**: `app/services/emergencia.py` com `detectar_emergencia(quadro_clinico, protocolos) -> Protocolo | None`.
- **DoD**: dado um quadro com termo presente em `termos_emergencia` de algum protocolo, função retorna o protocolo correspondente.

---

## Fase 3 — Processamento de Linguagem Natural

### Task 3.1 — Módulo NLU
- **Refs Req.**: 1.8, 1.9
- **Refs Design**: Componente 1
- **Entregáveis**: `app/nlu/interpretador.py`:
  - `interpretar_pergunta(texto) -> NLUResult` usando `ChatOpenAI` + `StructuredOutputParser`.
  - Prompt classifica em uma das 5 intenções e extrai entidades (`numero_prontuario`, `condicao`, `medicamentos_mencionados`).
  - Detecta idioma; valida pt-BR.
- **DoD**: testes verificam classificação correta para amostras de cada intenção e fallback para `INTENCAO_DESCONHECIDA`.

### Task 3.2 — Ciclo de esclarecimento (máx. 3 perguntas)
- **Refs Req.**: 1.8
- **Refs Design**: Propriedade 11, fluxo do Orquestrador
- **Entregáveis**: `app/nlu/esclarecimento.py`:
  - Gera até 3 perguntas objetivas usando o estado da `SessaoMedico`.
  - Incrementa `contador_esclarecimentos`; encerra ciclo ao atingir 3.
- **DoD**: teste end-to-end com mock de `interpretar_pergunta` confirma máximo de 3 ciclos antes de resposta de fallback.

---

## Fase 4 — Serviços Auxiliares

### Task 4.1 — Serviço de Interações Medicamentosas
- **Refs Req.**: 4.5, 4.6, 4.7
- **Refs Design**: Componente 5, Propriedade 6
- **Entregáveis**: `app/services/interacoes.py`:
  - `verificar_interacoes(tratamento_sugerido, medicamentos_em_uso) -> list[InteracaoMedicamentosa]`.
  - Implementação inicial baseada em base local JSON (`data/interacoes.json`) com pares conhecidos.
  - Retry com backoff exponencial (1s, 2s, 4s); lança `InteractionServiceUnavailableError` após esgotar.
- **DoD**: testes cobrem (a) interações detectadas, (b) lista vazia, (c) indisponibilidade após 3 tentativas.

### Task 4.2 — Verificação de Contraindicações
- **Refs Req.**: 4.8
- **Refs Design**: Propriedade 6
- **Entregáveis**: `app/services/contraindicacoes.py`:
  - `verificar_contraindicacoes(tratamento, prontuario) -> list[str]` cruzando com `alergias`, `comorbidades`, `historico_clinico` e contraindicações dos protocolos aplicáveis.
- **DoD**: testes verificam detecção a partir de cada campo do prontuário.

### Task 4.3 — Validação de completude do prontuário
- **Refs Req.**: 4.9
- **Refs Design**: Propriedade 9
- **Entregáveis**: `app/services/prontuario_validator.py`:
  - `validar_campos_obrigatorios(prontuario) -> list[str]` retornando lista de campos ausentes entre `{diagnostico_ativo, medicamentos_em_uso, alergias}`.
- **DoD**: orquestrador bloqueia sugestão de tratamento quando lista for não vazia.

### Task 4.4 — Resiliência do LLM (Circuit Breaker + Timeout)
- **Refs Req.**: 1.11
- **Refs Design**: Estratégia de Resiliência
- **Entregáveis**: `app/core/resilience.py`:
  - Decorador `with_timeout(seconds)` aplicando `asyncio.wait_for` (10s para PLN).
  - Circuit breaker (3 falhas → aberto por 30s).
- **DoD**: testes simulam timeout e falhas consecutivas; verifica `PLNTimeoutError` e abertura do circuito.

---

## Fase 5 — Orquestração e Regras de Negócio

### Task 5.1 — Orquestrador de Fluxo Clínico
- **Refs Req.**: 1.1, 1.5, 1.7, 1.10, 2.1, 2.7, 3.1, 4.1
- **Refs Design**: Componente 6 (fluxograma)
- **Entregáveis**: `app/orchestrator/fluxo.py`:
  - `processar_pergunta(texto, sessao) -> RespostaClinica` despachando para o handler por intenção.
  - Handlers: `handle_consulta_clinica`, `handle_sugestao_conduta`, `handle_verificacao_exames`, `handle_sugestao_tratamento`.
- **DoD**: cada handler tem teste de integração com mocks dos componentes downstream.

### Task 5.2 — Aplicação de avisos e fonte fixa de apoio à decisão
- **Refs Req.**: 1.3, 1.4, 1.6, 1.7, 2.5, 4.4
- **Refs Design**: Propriedades 1, 2, 3, 8, 10, 15
- **Entregáveis**: `app/orchestrator/avisos.py`:
  - `aplicar_avisos(resposta, contexto) -> RespostaClinica` adicionando avisos: `apoio_decisao` (sempre), `baixa_confianca` (se score < limiar), `evidencia_inconclusiva` (maybe), `raciocinio_necessario` (reasoning_required), `emergencia`, `fora_protocolo`.
- **DoD**: testes verificam que toda resposta clínica contém o aviso fixo `apoio_decisao` e que demais avisos aparecem somente nas condições previstas.

### Task 5.3 — Mapeamento de Termos MeSH a partir do quadro clínico
- **Refs Req.**: 1.5, 2.1, 4.1
- **Refs Design**: Propriedade 13
- **Entregáveis**: `app/services/mesh_mapper.py`:
  - `mapear_para_mesh(termos_clinicos) -> list[str]` usando LLM com prompt curto e cache local.
  - Quando não houver Base_de_Conhecimento aplicável (1.5), sugere ao menos um termo MeSH ou especialidade.
- **DoD**: testes verificam mapeamento determinístico para amostras conhecidas (com cache).

---

## Fase 6 — API HTTP (FastAPI)

### Task 6.1 — Endpoint de consulta clínica
- **Refs Req.**: 1.1, 1.2, 1.7, 1.9, 1.10, 1.11
- **Entregáveis**: `app/api/routes/consulta.py`:
  - `POST /v1/consulta` body `{ "texto": str, "sessao_id": str }` → `RespostaClinica`.
- **DoD**: contrato OpenAPI gerado; testes de contrato (request/response) passam.

### Task 6.2 — Endpoint de sugestão de conduta
- **Refs Req.**: 2.1–2.7
- **Entregáveis**: `app/api/routes/conduta.py`:
  - `POST /v1/conduta` body `{ "quadro_clinico": str, "sessao_id": str }`.
- **DoD**: resposta inclui protocolos ordenados, no máximo 5; artigos por YEAR desc; flag de emergência quando aplicável.

### Task 6.3 — Endpoint de verificação de exames
- **Refs Req.**: 3.1–3.5
- **Entregáveis**: `app/api/routes/exames.py`:
  - `GET /v1/pacientes/{numero_prontuario}/exames-pendentes`.
- **DoD**: retorna 404 com mensagem padrão se paciente não existir; lista vazia substituída por mensagem 3.4.

### Task 6.4 — Endpoint de sugestão de tratamento
- **Refs Req.**: 4.1–4.9
- **Entregáveis**: `app/api/routes/tratamento.py`:
  - `POST /v1/pacientes/{numero_prontuario}/tratamento`.
- **DoD**: bloqueio quando campos obrigatórios ausentes (4.9); bloqueio quando serviço de interações indisponível (4.7); separação Protocolos vs Artigos (4.2).

### Task 6.5 — Endpoint de sessão e esclarecimento
- **Refs Req.**: 1.8
- **Entregáveis**:
  - `POST /v1/sessao` cria `SessaoMedico` (UUID, idioma `pt-BR`, contador zerado).
  - Estado de sessão em memória/redis (decisão de implementação documentada).
- **DoD**: ciclo de até 3 perguntas funcionando ponta-a-ponta via API.

---

## Fase 7 — Atualização Assíncrona de Exames

### Task 7.1 — Worker de atualização de status de exames
- **Refs Req.**: 3.5
- **Refs Design**: Propriedade 14
- **Entregáveis**: `app/workers/exames_updater.py`:
  - Tarefa periódica (intervalo de 10s) que verifica resultados disponíveis e atualiza status para `Concluído`.
  - Garantia de atualização em até 60s após disponibilidade.
- **DoD**: teste de integração com mock injetando "resultado disponível" mede latência < 60s.

---

## Fase 8 — Testes de Aceitação e Propriedades

### Task 8.1 — Testes end-to-end por requisito
- **Refs Req.**: todos
- **Entregáveis**: `tests/e2e/` com um cenário por *acceptance criterion* (formato Given/When/Then).
- **DoD**: cobertura de 100% dos critérios de aceitação dos 4 requisitos.

### Task 8.2 — Testes de propriedade (correctness properties)
- **Refs Design**: Propriedades 1–15
- **Entregáveis**: `tests/properties/` com Hypothesis ou casos parametrizados validando cada propriedade.
- **DoD**: cada propriedade tem ao menos 1 teste; suite verde em CI.

### Task 8.3 — Testes de erro e resiliência
- **Refs Req.**: 1.10, 1.11, 3.3, 3.4, 4.7
- **Refs Design**: tabela Error Handling
- **Entregáveis**: cenários simulando: Base_de_Conhecimento off, timeout do LLM, paciente inexistente, serviço de interações off, BD off.
- **DoD**: cada cenário produz a mensagem e o código previstos.

---

## Fase 9 — Empacotamento e Documentação

### Task 9.1 — Documentação de operação
- **Entregáveis**:
  - `docs/operacao.md`: como rodar localmente, variáveis de ambiente, comandos de seed do BD e ingestão da Base de Conhecimento.
  - `docs/api.md`: exemplos `curl` para cada endpoint.
- **DoD**: instruções verificadas em ambiente limpo.

### Task 9.2 — Dockerização (opcional)
- **Entregáveis**: `Dockerfile` + `docker-compose.yml` com serviço da API e PostgreSQL.
- **DoD**: `docker compose up` sobe API em `:8000` com BD configurado.

---

## Mapa de Rastreabilidade (Requisito → Tasks principais)

| Requisito | Tasks principais |
|---|---|
| 1.1 | 2.3, 4.4, 5.1, 6.1 |
| 1.2 | 2.1, 2.3, 5.2 |
| 1.3 | 2.3, 5.2 |
| 1.4 | 2.3, 5.2 |
| 1.5 | 5.1, 5.3 |
| 1.6 | 0.2, 2.3, 5.2 |
| 1.7 | 5.2 |
| 1.8 | 3.1, 3.2, 6.5 |
| 1.9 | 3.1 |
| 1.10 | 0.3, 5.1 |
| 1.11 | 0.2, 0.3, 4.4 |
| 2.1 | 2.2, 2.3, 5.1, 5.3 |
| 2.2 | 2.2, 2.3 |
| 2.3 | 2.3 |
| 2.4 | 2.4 |
| 2.5 | 2.5, 5.2 |
| 2.6 | 2.4 |
| 2.7 | 5.1 |
| 3.1 | 1.3, 6.3 |
| 3.2 | 1.1, 1.3 |
| 3.3 | 0.3, 6.3 |
| 3.4 | 6.3 |
| 3.5 | 7.1 |
| 4.1 | 1.3, 5.1, 5.3 |
| 4.2 | 6.4 |
| 4.3 | 2.3 |
| 4.4 | 5.2 |
| 4.5 | 4.1, 6.4 |
| 4.6 | 4.1, 6.4 |
| 4.7 | 0.3, 4.1 |
| 4.8 | 4.2 |
| 4.9 | 4.3, 6.4 |

---

## Ordem Recomendada de Execução

1. **Fase 0** (fundação) — sem dependências externas.
2. **Fase 1** (dados) — habilita 3.x e 4.x.
3. **Fase 2** (RAG) — habilita 1.x, 2.x, parte de 4.x.
4. **Fase 3** (NLU) — habilita orquestração.
5. **Fase 4** (serviços auxiliares) — paralelizável com Fase 3.
6. **Fase 5** (orquestração) — depende de 2, 3 e 4.
7. **Fase 6** (API) — depende de 5.
8. **Fase 7** (worker de exames) — paralelizável com Fase 6 após Fase 1.
9. **Fase 8** (testes) — incremental ao longo das fases, fechamento ao final.
10. **Fase 9** (docs e empacotamento) — última etapa.
