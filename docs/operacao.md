# Guia de Operação — Assistente Virtual Médico Hospitalar

## Pré-requisitos

- Python 3.11+
- pip

## Configuração local

### 1. Instalar dependências

```bash
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
pip install -r requirements-dev.txt  # somente para desenvolvimento/testes
```

### 2. Configurar variáveis de ambiente

Copie o arquivo de exemplo e edite:

```bash
cp .env.example .env
```

Variáveis disponíveis:

| Variável | Padrão | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | `""` | Chave da API OpenAI (obrigatória para produção) |
| `LLM_MODEL` | `gpt-4o` | Modelo LLM a ser utilizado |
| `LLM_TEMPERATURE` | `0.1` | Temperatura do LLM (0.0–2.0) |
| `EMBEDDINGS_MODEL` | `text-embedding-3-small` | Modelo de embeddings OpenAI |
| `FAISS_INDEX_PATH` | `./data/faiss_index` | Caminho do índice FAISS |
| `CONFIDENCE_THRESHOLD` | `0.65` | Limiar de confiança para aviso baixa_confianca |
| `PLN_TIMEOUT_SECONDS` | `10.0` | Timeout do serviço PLN em segundos |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | URL do banco de dados |
| `API_HOST` | `0.0.0.0` | Host do servidor |
| `API_PORT` | `8000` | Porta do servidor |
| `LOG_LEVEL` | `INFO` | Nível de log |

> **Produção**: substitua `DATABASE_URL` pela URL do PostgreSQL, por exemplo:
> `postgresql+asyncpg://user:senha@host:5432/dbname`

### 3. Inicializar o banco de dados

```bash
python -m scripts.init_db
```

Este comando cria as tabelas necessárias (`pacientes`, `prontuarios`, `exames`, `medicamentos`) e popula dados de exemplo para desenvolvimento.

### 4. Ingerir a Base de Conhecimento (FAISS)

A ingestão lê os arquivos de `data/pubmedqa/` e `data/protocolos/`, gera embeddings via OpenAI e salva o índice FAISS em `data/faiss_index/`.

```bash
# Requer OPENAI_API_KEY configurada
python -m scripts.ingest_kb
```

> **Sem chave OpenAI**: a API inicia no modo degradado (sem RAG). Endpoints de consulta,
> conduta e tratamento retornam 503. Os endpoints de exames continuam funcionando.

### 5. Iniciar a API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

A documentação interativa estará disponível em `http://localhost:8000/docs`.

---

## Executar os testes

```bash
# Todos os testes
pytest

# Apenas testes de unidade
pytest tests/unit/

# Apenas testes de integração
pytest tests/integration/

# Apenas testes E2E
pytest tests/e2e/

# Testes de propriedades
pytest tests/properties/

# Com cobertura
pytest --cov=app --cov-report=term-missing
```

---

## Docker

Veja [docker-compose.yml](../docker-compose.yml) para execução com Docker.

```bash
# Subir API + banco de dados
docker compose up --build

# Apenas o banco (útil para desenvolvimento local)
docker compose up db
```

---

## Estrutura de dados

### `data/interacoes.json`

Array JSON com as interações medicamentosas conhecidas:

```json
[
  {
    "medicamento_a": "Warfarina",
    "medicamento_b": "Aspirina",
    "severidade": "grave",
    "descricao": "Risco aumentado de sangramento."
  }
]
```

### `data/protocolos/`

Arquivos JSON com protocolos clínicos internos. Veja `docs/protocolo-schema.md` para o schema completo.

### `data/pubmedqa/`

Entradas no formato PubMedQA (JSON). Cada entrada segue o modelo `EntradaPubMedQA` definido em `app/models/domain.py`.
