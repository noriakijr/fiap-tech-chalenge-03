# Referência de API — Assistente Virtual Médico Hospitalar

Base URL: `http://localhost:8000/v1`

Documentação interativa (Swagger): `http://localhost:8000/docs`

---

## Sessão

### `POST /v1/sessao` — Criar sessão

Cria uma nova sessão para um médico. Necessária antes de usar os endpoints de consulta, conduta e tratamento.

```bash
curl -s -X POST http://localhost:8000/v1/sessao \
  -H "Content-Type: application/json" \
  -d '{"id_medico": "DR-001"}' | jq .
```

**Resposta 201:**

```json
{
  "sessao_id": "3f1a2b4c-..."
}
```

---

## Consulta Clínica

### `POST /v1/consulta` — Pergunta clínica em linguagem natural

Processa uma pergunta clínica e retorna resposta baseada em evidências.

```bash
curl -s -X POST http://localhost:8000/v1/consulta \
  -H "Content-Type: application/json" \
  -d '{
    "texto": "Qual o tratamento de primeira linha para pneumonia bacteriana em adultos?",
    "sessao_id": "3f1a2b4c-..."
  }' | jq .
```

**Resposta 200:**

```json
{
  "texto_resposta": "O tratamento de primeira linha para pneumonia bacteriana...",
  "fontes": [
    {
      "tipo": "artigo",
      "identificador": "PMID-12345",
      "titulo": "Treatment of community-acquired pneumonia",
      "ano": 2022,
      "decisao_final": "yes"
    }
  ],
  "avisos": [
    {
      "tipo": "apoio_decisao",
      "mensagem": "Este sistema é um auxílio à decisão clínica...",
      "destaque": false
    }
  ],
  "confianca": 0.87,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Erros:**

| Status | Código | Situação |
|---|---|---|
| 404 | `session_not_found` | `sessao_id` não existe |
| 503 | `knowledge_base_unavailable` | Base de conhecimento indisponível |
| 504 | `pln_timeout` | PLN não respondeu em 10s |

---

## Sugestão de Conduta

### `POST /v1/conduta` — Sugestão de condutas clínicas

Sugere condutas baseadas em protocolos e evidências para um quadro clínico descrito.

```bash
curl -s -X POST http://localhost:8000/v1/conduta \
  -H "Content-Type: application/json" \
  -d '{
    "quadro_clinico": "Paciente com febre alta, tosse produtiva e dispneia moderada",
    "sessao_id": "3f1a2b4c-..."
  }' | jq .
```

**Resposta 200:** (mesma estrutura de `/v1/consulta`)

```json
{
  "texto_resposta": "Condutas recomendadas para o quadro descrito...",
  "fontes": [
    {
      "tipo": "protocolo",
      "identificador": "PROT-PNEUMONIA-001",
      "titulo": "Protocolo de Pneumonia Hospitalar"
    },
    {
      "tipo": "artigo",
      "identificador": "PMID-99001",
      "titulo": "Antibiotic therapy for pneumonia",
      "ano": 2023,
      "decisao_final": "yes"
    }
  ],
  "avisos": [...],
  "confianca": 0.91
}
```

> Os protocolos vigentes sempre aparecem antes dos artigos na lista `fontes`.
> Em quadros com termos de emergência, o aviso `emergencia` aparece com `destaque: true`.

---

## Exames Pendentes

### `GET /v1/pacientes/{numero_prontuario}/exames-pendentes`

Recupera a lista de exames pendentes (Solicitado, Coletado ou Em Análise) de um paciente.

```bash
curl -s http://localhost:8000/v1/pacientes/PRT-12345/exames-pendentes | jq .
```

**Resposta 200:**

```json
{
  "texto_resposta": "Exames pendentes para o paciente PRT-12345:\n  • Hemograma — Em Análise (solicitado em 2024-01-10, por DR-SILVA)\n  • PCR — Solicitado (solicitado em 2024-01-11, por DR-SILVA)",
  "fontes": [],
  "avisos": [
    {
      "tipo": "apoio_decisao",
      "mensagem": "...",
      "destaque": false
    }
  ],
  "confianca": 1.0
}
```

**Erros:**

| Status | Código | Situação |
|---|---|---|
| 404 | `patient_not_found` | Prontuário não cadastrado |
| 503 | `database_unavailable` | Banco de dados indisponível |

---

## Sugestão de Tratamento

### `POST /v1/pacientes/{numero_prontuario}/tratamento`

Sugere tratamentos personalizados com base no prontuário do paciente, incluindo verificação de interações medicamentosas e contraindicações.

```bash
curl -s -X POST http://localhost:8000/v1/pacientes/PRT-12345/tratamento \
  -H "Content-Type: application/json" \
  -d '{
    "sessao_id": "3f1a2b4c-...",
    "medicamentos_sugeridos": ["Amoxicilina", "Ibuprofeno"]
  }' | jq .
```

**Corpo da requisição:**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `sessao_id` | string | sim | ID da sessão ativa |
| `medicamentos_sugeridos` | array[string] | não | Medicamentos a verificar interações |

**Resposta 200:**

```json
{
  "texto_resposta": "Tratamento sugerido com base no diagnóstico ativo (pneumonia):\n...\n\n**Interações medicamentosas detectadas:**\n- [MODERADA] Amoxicilina ✕ Warfarina: monitorar INR.",
  "fontes": [...],
  "avisos": [
    {"tipo": "apoio_decisao", "mensagem": "...", "destaque": false},
    {"tipo": "baixa_confianca", "mensagem": "...", "destaque": false}
  ],
  "confianca": 0.72
}
```

**Prontuário incompleto (200):**

```json
{
  "texto_resposta": "Prontuário incompleto. Campos obrigatórios ausentes: diagnostico_ativo, alergias. Complete o prontuário antes de solicitar sugestão de tratamento.",
  ...
}
```

**Erros:**

| Status | Código | Situação |
|---|---|---|
| 404 | `patient_not_found` | Prontuário não cadastrado |
| 503 | `interaction_service_unavailable` | Serviço de interações indisponível |
| 503 | `database_unavailable` | Banco de dados indisponível |

---

## Formato de Erro

Todas as respostas de erro seguem o formato:

```json
{
  "error": {
    "code": "knowledge_base_unavailable",
    "message": "O serviço de base de conhecimento está temporariamente indisponível. Tente novamente em instantes.",
    "detalhes": {}
  }
}
```

---

## Tipos de Aviso (`avisos[].tipo`)

| Tipo | Situação |
|---|---|
| `apoio_decisao` | Sempre presente — lembra que o sistema não substitui o julgamento clínico |
| `baixa_confianca` | Confiança abaixo do limiar configurado (padrão: 0.65) |
| `evidencia_inconclusiva` | Artigo com `final_decision = "maybe"` utilizado na resposta |
| `raciocinio_necessario` | Artigo com `reasoning_required_pred = "yes"` — exige análise aprofundada |
| `emergencia` | Quadro contém termos de emergência — exibido com `destaque: true` |
| `fora_protocolo` | Conduta/tratamento não coberto por protocolos internos vigentes |
