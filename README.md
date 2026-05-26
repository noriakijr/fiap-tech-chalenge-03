# Assistente Virtual Médico Hospitalar

Sistema de suporte à decisão clínica baseado em IA (RAG + PLN) que responde perguntas clínicas, sugere condutas e tratamentos, e verifica exames pendentes de pacientes.

A especificação completa está em `.kiro/specs/medical-virtual-assistant/`:

- `requirements.md` — requisitos funcionais e critérios de aceitação.
- `design.md` — arquitetura, stack e propriedades de correção.
- `tasks.md` — divisão em tarefas implementáveis.

## Pré-requisitos

- Python 3.11+ (testado com 3.13)
- `pip`
- Chave de API OpenAI (`OPENAI_API_KEY`) — necessária para geração de embeddings e respostas via LLM.

## Rodando localmente (passo a passo)

### 1. Criar ambiente virtual e instalar dependências

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

**Windows — PowerShell**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

> Se receber o erro `running scripts is disabled`, execute antes:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**Windows — Prompt de Comando (CMD)**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements-dev.txt
```

> No Windows use `python` em vez de `python3` nos passos seguintes.

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Abra `.env` e preencha pelo menos a `OPENAI_API_KEY`:

```
OPENAI_API_KEY=sk-...
```

As demais variáveis já têm valores padrão funcionais para desenvolvimento local (SQLite + FAISS em `data/`).

### 3. Inicializar o banco de dados

Cria as tabelas e insere pacientes, exames e medicamentos de exemplo:

```bash
python -m scripts.init_db
```

> Para resetar e recriar do zero: `python -m scripts.init_db --reset`

### 4. Indexar a base de conhecimento (FAISS)

Lê os arquivos de `data/pubmedqa/` e `data/protocolos/`, gera embeddings via OpenAI e salva o índice vetorial em `data/faiss_index/`:

```bash
python -m scripts.build_kb
```

Saída esperada:

```
  PubMedQA: sample.json → 6 entradas
  Protocolos: 3 documentos carregados

Total: 9 documentos (6 artigos + 3 protocolos)
Gerando embeddings e construindo índice FAISS em 'data/faiss_index'...
✓ Índice FAISS salvo em data/faiss_index
```

> **Sem `OPENAI_API_KEY`:** a API inicia em modo degradado. Endpoints de consulta, conduta e tratamento retornam `503`; o endpoint de exames continua funcionando normalmente.

### 5. Subir a API

```bash
uvicorn app.main:app --reload
```

A API ficará disponível em `http://localhost:8000`. Endpoints úteis:

- `GET /docs` — documentação OpenAPI interativa (Swagger UI).
- `POST /v1/sessao` — cria uma sessão para o médico.
- `POST /v1/consulta` — pergunta clínica em linguagem natural.
- `POST /v1/conduta` — sugestão de condutas para um quadro clínico.
- `GET /v1/pacientes/{numero}/exames-pendentes` — exames pendentes do paciente.
- `POST /v1/pacientes/{numero}/tratamento` — sugestão de tratamento personalizado.

### Exemplo rápido via curl

**Linux / macOS**
```bash
# Cria sessão e captura o ID
SESSAO=$(curl -s -X POST http://localhost:8000/v1/sessao \
  -H "Content-Type: application/json" \
  -d '{"id_medico": "DR-001"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['sessao_id'])")

# Pergunta clínica
curl -s -X POST http://localhost:8000/v1/consulta \
  -H "Content-Type: application/json" \
  -d "{\"texto\": \"Tratamento de primeira linha para pneumonia bacteriana?\", \"sessao_id\": \"$SESSAO\"}" \
  | python3 -m json.tool
```

**Windows — PowerShell**
```powershell
# Cria sessão e captura o ID
$sessao = (curl -s -X POST http://localhost:8000/v1/sessao `
  -H "Content-Type: application/json" `
  -d '{"id_medico": "DR-001"}' | python -c "import sys,json; print(json.load(sys.stdin)['sessao_id'])")

# Pergunta clínica
curl -s -X POST http://localhost:8000/v1/consulta `
  -H "Content-Type: application/json" `
  -d "{`"texto`": `"Tratamento de primeira linha para pneumonia bacteriana?`", `"sessao_id`": `"$sessao`"}" `
  | python -m json.tool
```

Veja mais exemplos em [`docs/api.md`](docs/api.md).

## Estrutura do projeto

```
app/
  api/           # rotas FastAPI
  core/          # config, logging, exceções, resiliência
  db/            # modelos SQLAlchemy, sessão, repositórios
  rag/           # ingestão e motor RAG (FAISS + LangChain)
  nlu/           # interpretação de intenção e ciclo de esclarecimento
  orchestrator/  # fluxo clínico e aplicação de avisos
  services/      # ordenação, emergência, interações, contraindicações
  models/        # modelos Pydantic do domínio
  workers/       # tarefas assíncronas (atualização de exames)
tests/
  unit/ integration/ e2e/ properties/
data/            # índice FAISS, base PubMedQA, banco SQLite
scripts/         # utilitários de seed/ingestão
```

## Variáveis de ambiente

Veja `.env.example`. Variáveis principais:

| Variável | Descrição |
|---|---|
| `OPENAI_API_KEY` | Chave de API da OpenAI. |
| `LLM_MODEL` | Modelo LLM (default `gpt-4o`). |
| `EMBEDDINGS_MODEL` | Modelo de embeddings (default `text-embedding-3-small`). |
| `CONFIDENCE_THRESHOLD` | Limiar de confiança da resposta (0–1). |
| `PLN_TIMEOUT_SECONDS` | Timeout do serviço de PLN (default 10s). |
| `DATABASE_URL` | URL SQLAlchemy (default SQLite local). |
| `FAISS_INDEX_PATH` | Caminho do índice FAISS no disco. |

## Testes

```bash
pytest
```
