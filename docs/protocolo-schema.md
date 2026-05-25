# Schema dos Protocolos Clínicos Internos

Os protocolos são arquivos JSON colocados em `data/protocolos/` (um arquivo por
protocolo, ou um único arquivo contendo uma lista). Cada entrada deve respeitar
o schema abaixo, validado pelo modelo Pydantic `app.models.domain.Protocolo`.

## Campos

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | sim | Identificador único do protocolo (ex.: `PROT-SEPSE-001`). |
| `titulo` | string | sim | Título legível em pt-BR. |
| `nivel_evidencia` | string | sim | Classificação do nível de evidência (`A`, `B`, `C`, `I`, `II`, `III`...). |
| `condicoes_aplicaveis` | string[] | sim | Termos clínicos cobertos pelo protocolo (preferencialmente alinhados a Termos MeSH). |
| `contraindicacoes` | string[] | sim | Contraindicações explícitas. Pode ser lista vazia. |
| `termos_emergencia` | string[] | sim | Termos que disparam o destaque de emergência (Requisito 2.5). Lista vazia indica que o protocolo não é de urgência. |
| `vigente` | boolean | não (default `true`) | Indica se o protocolo está em vigor. Protocolos não vigentes são ignorados na ingestão. |
| `texto` | string | sim (ingestão) | Corpo do protocolo usado para embeddings. **Não faz parte do modelo Pydantic** — é lido apenas no momento da ingestão para gerar o `Document` LangChain. |

## Convenções

- Comparações de termos (`termos_emergencia`, `condicoes_aplicaveis`) são feitas
  case-insensitive e tolerantes a acentos pelo serviço de detecção
  (`app.services.emergencia.detectar_emergencia`).
- `texto` deve estar em pt-BR e ser autossuficiente — o RAG não recorre a
  outros documentos para complementar.

## Exemplo (formato JSON)

```json
{
  "id": "PROT-SEPSE-001",
  "titulo": "Manejo Inicial de Sepse e Choque Séptico",
  "nivel_evidencia": "A",
  "condicoes_aplicaveis": ["sepse", "choque séptico", "infecção grave"],
  "contraindicacoes": ["alergia conhecida ao antibiótico empírico"],
  "termos_emergencia": ["choque séptico", "sepse grave"],
  "vigente": true,
  "texto": "1. Reconhecer sinais de sepse... 2. Administrar antibiótico empírico em até 1h... 3. Reposição volêmica..."
}
```

## Estrutura de diretórios

```
data/protocolos/
  protocolo-sepse.json
  protocolo-iam.json
  protocolo-anafilaxia.json
```

A ingestão (`app.rag.ingest_protocolos.carregar_protocolos`) lê todos os
`*.json` desse diretório. Se um arquivo contiver uma lista, cada elemento é
tratado como um protocolo independente.
