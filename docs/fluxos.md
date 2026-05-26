# Fluxos Principais da Aplicação — Assistente Virtual Médico Hospitalar

---

## Fluxo 0 — Inicialização (Startup)

Acontece uma única vez quando o servidor sobe, antes de aceitar qualquer requisição.

```
uvicorn app.main:app
        │
        ▼
  lifespan() [app/api/deps.py]
        │
        ├── OPENAI_API_KEY ausente?
        │     └── app.state.vectorstore = None  → inicia em modo degradado
        │
        └── Chave presente:
              │
              ├─ 1. Instancia ChatOpenAI (gpt-4o, temp=0.1) → app.state.llm
              ├─ 2. Instancia OpenAIEmbeddings → carrega FAISS do disco
              │         data/faiss_index/index.faiss + index.pkl
              │         → app.state.vectorstore
              ├─ 3. Lê data/protocolos/*.json → list[Protocolo]
              │         → app.state.protocolos
              ├─ 4. Cria MapadorMeSH(llm) → app.state.mesh_mapper
              └─ 5. Cria ServicoInteracoes(carregador=data/interacoes.json)
                        → app.state.servico_interacoes
```

> Se qualquer etapa falhar (arquivo FAISS ausente, chave inválida, etc.) a exceção é capturada, um aviso é logado e a API sobe **sem RAG**. Endpoints de exames continuam funcionando; os demais retornam `503`.

---

## Fluxo 1 — Criar Sessão (`POST /v1/sessao`)

O ponto de entrada obrigatório antes de qualquer interação clínica.

```
POST /v1/sessao  {"id_medico": "DR-001"}
        │
        ▼
  sessao.py → cria SessaoMedico(
                id_sessao = UUID gerado,
                id_medico = "DR-001",
                contador_esclarecimentos = 0,
                historico_perguntas = []
              )
        │
        ├── Armazena em _session_store[sessao_id] (dict em memória)
        │
        └── Retorna {"sessao_id": "3f1a2b4c-..."}  → 201
```

A sessão controla dois estados importantes: `historico_perguntas` (contexto) e `contador_esclarecimentos` (trava que impede mais de 3 ciclos de esclarecimento por intenção desconhecida).

---

## Fluxo 2 — Consulta Clínica (`POST /v1/consulta`)

O fluxo mais completo — percorre NLU, ciclo de esclarecimento, RAG e pós-processamento de avisos.

```
POST /v1/consulta  {"texto": "Tratamento de pneumonia?", "sessao_id": "..."}
        │
        ▼
  [deps.py] Valida sessão no store → 404 se não existe
        │
  [deps.py] Monta OrquestradorClinico por requisição
        │   (LLM, FAISS e protocolos vêm do app.state; DB Session é nova por req)
        │
        ▼
  OrquestradorClinico.processar_pergunta(texto, sessao)
        │
        ▼
  ┌─── NLU: InterpretadorNLU.interpretar_pergunta(texto)
  │         ChatOpenAI classifica → JSON com {intencao, entidades, confianca}
  │         Se JSON inválido ou confiança < 0.5 → INTENCAO_DESCONHECIDA
  │
  ├── INTENCAO_DESCONHECIDA?
  │     │
  │     ├── sessao.contador_esclarecimentos < 3?
  │     │     │
  │     │     └── GeradorEsclarecimento.gerar_pergunta(texto, historico)
  │     │               ChatOpenAI gera 1 pergunta objetiva em pt-BR
  │     │               sessao.contador_esclarecimentos += 1
  │     │               Retorna a pergunta como texto_resposta → 200
  │     │
  │     └── contador == 3 → retorna MENSAGEM_FALLBACK e encerra o ciclo
  │
  └── Intenção reconhecida → CONSULTA_CLINICA
              │
              ▼
        handle_consulta_clinica(texto, nlu)
              │
              ▼
        MotorRAG.recuperar_e_gerar(texto)
              │
              ├─ FAISS.similarity_search_with_score(consulta, k=10)
              │     Busca vetorial semântica nos documentos indexados
              │     Retorna [(Document, distância_L2)]
              │
              ├─ Converte distância → score [0,1]: 1 / (1 + distância)
              │
              ├─ Monta contexto formatado com id, título, CONTEXTS, LONG_ANSWER
              │
              ├─ ChatOpenAI gera resposta em pt-BR citando [identificadores]
              │
              └─ Retorna RespostaRAG {texto, documentos, confiança_geral,
                                       aviso_baixa_confianca}
              │
              ▼
        aplicar_avisos(resposta, ContextoAvisos)
              │
              ├── APOIO_DECISAO          → sempre
              ├── BAIXA_CONFIANCA        → se confiança < 0.65 ou flag RAG
              ├── EVIDENCIA_INCONCLUSIVA → se algum artigo tem final_decision=maybe
              └── RACIOCINIO_NECESSARIO  → se algum artigo tem reasoning_required=yes
              │
              ▼
        RespostaClinica → JSON → 200
```

---

## Fluxo 3 — Sugestão de Conduta (`POST /v1/conduta`)

Diferente do `/v1/consulta`, a rota monta o `NLUResult` diretamente (sem passar pelo NLU), garantindo comportamento determinístico.

```
POST /v1/conduta  {"quadro_clinico": "febre + hipotensão + sepse", "sessao_id": "..."}
        │
        ▼
  conduta.py → NLUResult(
                 intencao = SUGESTAO_CONDUTA,
                 entidades = {"condicao": "febre + hipotensão + sepse"}
               )  [NLU bypassed]
        │
        ▼
  handle_sugestao_conduta(texto, nlu)
        │
        ├─ 1. MapadorMeSH.mapear_para_mesh(["febre + hipotensão + sepse"])
        │         ChatOpenAI converte termos livres → MeSH padronizados
        │         Ex.: ["Fever", "Hypotension", "Sepsis"]
        │         Resultado em cache in-memory por sessão
        │
        ├─ 2. MotorRAG.recuperar_e_gerar(
        │         consulta = quadro_clinico,
        │         filtros_mesh = ["fever", "sepsis", ...],
        │         excluir_decisao_final = ["no"]   ← Req 4.3
        │       )
        │
        ├─ 3. Separa protocolos e artigos da lista de documentos
        │
        ├─ 4. ordenar_condutas(protocolos, artigos, quadro_clinico)
        │         Protocolos ordenados por nº de MeSH que coincidem com o quadro (desc)
        │         Limite: 5 protocolos máximo
        │         Artigos ordenados por YEAR desc
        │
        ├─ 5. detectar_emergencia(quadro_clinico, protocolos_vigentes)
        │         Regex com fronteira de palavra sobre termos_emergencia de cada protocolo
        │         Ex.: "parada cardiorrespiratória" → protocolo PCR detectado
        │
        └─ 6. aplicar_avisos(...)
                 APOIO_DECISAO       → sempre
                 EMERGENCIA          → se emergência detectada  (destaque=True)
                 BAIXA_CONFIANCA     → se confiança RAG < limiar
                 EVIDENCIA_INCONCLUSIVA → artigos maybe
                 RACIOCINIO_NECESSARIO  → artigos reasoning_required
                 FORA_PROTOCOLO      → se nenhum protocolo na lista de fontes
                 │
                 └── RespostaClinica → JSON → 200
```

---

## Fluxo 4 — Verificação de Exames (`GET /v1/pacientes/{id}/exames-pendentes`)

Único fluxo sem LLM — consulta direta ao banco de dados.

```
GET /v1/pacientes/PRT-0001/exames-pendentes
        │
        ▼
  exames.py → NLUResult(
                intencao = VERIFICACAO_EXAMES,
                entidades = {"numero_prontuario": "PRT-0001"}
              )  [NLU bypassed, sem sessão]
        │
        ▼
  handle_verificacao_exames(nlu)
        │
        ├─ 1. RepositorioPacientes.buscar_prontuario("PRT-0001")
        │         SELECT * FROM pacientes WHERE numero_prontuario = ?
        │         None → PatientNotFoundError → 404
        │         SQLAlchemyError → DatabaseUnavailableError → 503
        │
        ├─ 2. RepositorioPacientes.listar_exames_pendentes("PRT-0001")
        │         SELECT * FROM exames
        │         WHERE numero_prontuario = ?
        │         AND status IN ('Solicitado', 'Coletado', 'Em Análise')
        │
        ├─ 3. Formata texto:
        │         Lista vazia → "Não há exames pendentes para..."
        │         Com itens  → "  • Hemograma — Em Análise (em 2026-05-20, por Dr. X)"
        │
        └─ 4. aplicar_avisos(ContextoAvisos())  → apenas APOIO_DECISAO
                 │
                 └── RespostaClinica → JSON → 200
```

> O status dos exames é mantido atualizado pelo **AtualizadorExames** (Fluxo 6).

---

## Fluxo 5 — Sugestão de Tratamento (`POST /v1/pacientes/{id}/tratamento`)

O fluxo mais complexo — combina banco de dados, RAG, interações medicamentosas e contraindicações.

```
POST /v1/pacientes/PRT-0001/tratamento
     {"sessao_id": "...", "medicamentos_sugeridos": ["Amoxicilina"]}
        │
        ▼
  [deps.py] Valida sessão → 404 se não existe
        │
        ▼
  handle_sugestao_tratamento(texto, nlu)
        │
        ├─ 1. RepositorioPacientes.buscar_prontuario("PRT-0001")
        │         None → PatientNotFoundError → 404
        │
        ├─ 2. validar_campos_obrigatorios(prontuario)
        │         Verifica: diagnostico_ativo · medicamentos_em_uso · alergias
        │         Algum ausente? → retorna 200 com mensagem listando campos faltantes
        │         (não é erro HTTP — é uma resposta clínica de bloqueio)
        │
        ├─ 3. MapadorMeSH.mapear_para_mesh([diagnostico_ativo])
        │         Ex.: "Pneumonia adquirida na comunidade"
        │              → ["Pneumonia", "Community-Acquired Infections"]
        │
        ├─ 4. MotorRAG.recuperar_e_gerar(
        │         consulta = "Tratamento para <diagnóstico>. Comorbidades: ... Alergias: ...",
        │         filtros_mesh = [termos_mesh]
        │       )
        │
        ├─ 5. ServicoInteracoes.verificar_interacoes(
        │         tratamento_sugerido = ["Amoxicilina"],
        │         medicamentos_em_uso  = prontuario.medicamentos_em_uso
        │       )
        │         Lê data/interacoes.json (retry 3x com backoff 1s → 2s → 4s)
        │         Falha após 3 tentativas → InteractionServiceUnavailableError → 503
        │         (bloqueia a sugestão — Req 4.7)
        │
        ├─ 6. verificar_contraindicacoes(
        │         tratamento, prontuario, protocolos_vigentes
        │       )
        │         Cruza alergias · comorbidades · histórico clínico
        │         e contraindicações dos protocolos
        │         Retorna lista de alertas em texto
        │
        ├─ 7. Monta texto_resposta:
        │         RAG base
        │         + "**Interações medicamentosas detectadas:**" (se houver)
        │         + "**Contraindicações detectadas:**" (se houver)
        │
        ├─ 8. Se há interações ou contraindicações → força aviso_baixa_confianca=True
        │
        └─ 9. aplicar_avisos(...)
                 APOIO_DECISAO       → sempre
                 BAIXA_CONFIANCA     → se interações/contraindicações ou confiança baixa
                 EVIDENCIA_INCONCLUSIVA · RACIOCINIO_NECESSARIO → conforme RAG
                 FORA_PROTOCOLO      → se RAG não trouxe nenhum protocolo
                 │
                 └── RespostaClinica → JSON → 200
```

---

## Fluxo 6 — Worker de Atualização de Exames (background)

Roda em paralelo à API como uma `asyncio.Task`, sem bloquear requisições.

```
  [lifespan startup] asyncio.create_task(worker.iniciar())
        │
        ▼
  AtualizadorExames.iniciar()
        │
        └── loop infinito até asyncio.CancelledError:
              │
              ├─ executar_ciclo()
              │     │
              │     ├─ SELECT * FROM exames WHERE status = 'Em Análise'
              │     │
              │     └─ Para cada exame:
              │           await verificar_resultado(numero_prontuario, nome)
              │               True  → exame.status = 'Concluído'
              │               False → mantém
              │               Erro  → loga e continua (não interrompe o ciclo)
              │
              │     Commit apenas se atualizados > 0
              │     Retorna nº de exames atualizados
              │
              └─ await asyncio.sleep(10s)
                    ↑
              Garante atualização em ≤ 60s (6 ciclos × 10s = Req 3.5)
```

---

## Tratamento de Erros (transversal a todos os fluxos)

Dois handlers globais registrados em `main.py` protegem todas as rotas:

```
Qualquer exceção levantada em qualquer rota
        │
        ├── É BaseAppError?
        │     (KnowledgeBaseUnavailableError · PLNTimeoutError
        │      PatientNotFoundError · InteractionServiceUnavailableError
        │      DatabaseUnavailableError)
        │
        │     └── JSONResponse(
        │               status = exc.http_status,
        │               body   = {"error": {"code": "...", "message": "..."}}
        │         )
        │
        └── Qualquer outra exceção (RuntimeError, etc.)
              └── JSONResponse(500, {"error": {"code": "internal_error", ...}})
                  Stack trace nunca vazado para o cliente
```

### Resiliência para chamadas ao LLM

```
CircuitBreaker [app/core/resilience.py]
  ├── 3 falhas consecutivas → estado ABERTO por 30s
  ├── Chamadas no período ABERTO → CircuitBreakerOpenError (503) imediato
  ├── Após 30s → estado SEMI_ABERTO → tenta 1 chamada
  └── Sucesso → FECHADO · Nova falha → ABERTO novamente

@with_timeout(10s)
  └── asyncio.wait_for → TimeoutError → PLNTimeoutError → 504
```

### Retry para interações medicamentosas

```
ServicoInteracoes.verificar_interacoes()
  └── _carregar_com_retry()
        ├── Tentativa 1 → falha → aguarda 1s
        ├── Tentativa 2 → falha → aguarda 2s
        ├── Tentativa 3 → falha → aguarda 4s
        └── Esgotou tentativas → InteractionServiceUnavailableError → 503
```

---

## Mapa de Status HTTP por Cenário

| Cenário | Status | Código de erro |
|---|---|---|
| Sucesso | 200 / 201 | — |
| Sessão não encontrada | 404 | `session_not_found` |
| Paciente não encontrado | 404 | `patient_not_found` |
| Base de conhecimento indisponível | 503 | `knowledge_base_unavailable` |
| Serviço de interações indisponível | 503 | `interaction_service_unavailable` |
| Banco de dados indisponível | 503 | `database_unavailable` |
| Timeout do PLN (> 10s) | 504 | `pln_timeout` |
| Payload inválido (Pydantic) | 422 | *(FastAPI padrão)* |
| Erro interno inesperado | 500 | `internal_error` |
