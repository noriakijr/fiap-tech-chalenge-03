# Assistente Virtual Médico Hospitalar

Sistema de suporte à decisão clínica baseado em IA (RAG + PLN) que responde perguntas clínicas, sugere condutas e tratamentos, e verifica exames pendentes de pacientes.

A especificação completa está em `.kiro/specs/medical-virtual-assistant/`:

- `requirements.md` — requisitos funcionais e critérios de aceitação.
- `design.md` — arquitetura, stack e propriedades de correção.
- `tasks.md` — divisão em tarefas implementáveis.

## Pré-requisitos

- Python 3.11+ (testado com 3.13)
- `pip`

## Setup local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# edite .env com sua OPENAI_API_KEY
```

## Subindo a API

```bash
uvicorn app.main:app --reload
```

A API ficará disponível em `http://localhost:8000`. Endpoints úteis:

- `GET /health` — verificação de disponibilidade.
- `GET /docs` — documentação OpenAPI gerada automaticamente.

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
