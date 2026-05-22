# Requirements Document

## Introduction

O Assistente Virtual Médico Hospitalar é um sistema de inteligência artificial treinado com dados e protocolos internos do hospital e com uma base de conhecimento científico estruturada no formato PubMedQA, projetado para apoiar a equipe médica em decisões clínicas. O sistema auxilia médicos respondendo dúvidas clínicas com base em evidências científicas e protocolos institucionais, sugerindo condutas e tratamentos personalizados, e verificando exames pendentes de pacientes. O sistema atua como ferramenta de suporte à decisão, sem substituir o julgamento clínico do profissional de saúde.

## Glossary

- **Assistente**: O sistema de assistente virtual médico hospitalar descrito neste documento.
- **Médico**: Profissional de saúde habilitado que utiliza o sistema para apoio clínico.
- **Paciente**: Indivíduo cadastrado no sistema hospitalar que está sob cuidados médicos.
- **Protocolo**: Conjunto de diretrizes clínicas internas do hospital que orientam condutas e procedimentos médicos.
- **Base_de_Conhecimento**: Repositório que combina protocolos internos do hospital e artigos científicos estruturados no formato PubMedQA, contendo perguntas clínicas, contextos extraídos de artigos, termos MeSH, ano de publicação e decisão final (yes/no/maybe).
- **Artigo_Científico**: Entrada da Base_de_Conhecimento no formato PubMedQA, composta por: identificador único, pergunta clínica (QUESTION), trechos de contexto (CONTEXTS) com seus rótulos de seção (LABELS), termos MeSH (MESHES), ano de publicação (YEAR), indicador de raciocínio necessário (reasoning_required_pred) e decisão final (final_decision) com justificativa (LONG_ANSWER).
- **Termo_MeSH**: Descritor padronizado do Medical Subject Headings utilizado para categorizar e recuperar Artigos_Científicos por especialidade ou condição clínica.
- **Decisão_Final**: Campo do Artigo_Científico que indica se a evidência suporta (yes), refuta (no) ou é inconclusiva (maybe) em relação à pergunta clínica do artigo.
- **Prontuário**: Registro eletrônico contendo o histórico clínico, diagnósticos, prescrições e exames de um Paciente.
- **Exame**: Procedimento diagnóstico (laboratorial, de imagem ou outro) solicitado para um Paciente. Um Exame é considerado pendente quando seu status é Solicitado, Coletado ou Em Análise.
- **Conduta_Clínica**: Decisão ou conjunto de ações médicas tomadas em relação ao cuidado de um Paciente.

---

## Requirements

### Requirement 1: Interface de Consulta Clínica por Linguagem Natural com Evidências Científicas

**User Story:** Como Médico, quero fazer perguntas clínicas ao Assistente em linguagem natural, para que eu obtenha respostas embasadas em evidências científicas e nos protocolos internos do hospital de forma rápida e contextualizada.

#### Acceptance Criteria

1. WHEN um Médico envia uma pergunta clínica em linguagem natural, THE Assistente SHALL processar a pergunta e retornar uma resposta em até 5 segundos para perguntas que não exijam recuperação de dados externos ao Assistente.
2. WHEN o Assistente gera uma resposta clínica, THE Assistente SHALL exibir, junto à resposta, as fontes utilizadas, incluindo: para Artigos_Científicos, o identificador único, o título da pergunta (QUESTION) e o ano de publicação (YEAR); para Protocolos, o identificador e o título do Protocolo.
3. WHEN o Assistente utiliza um Artigo_Científico cuja Decisão_Final for "maybe", THE Assistente SHALL indicar explicitamente que a evidência é inconclusiva e apresentar os trechos de contexto (CONTEXTS) relevantes para que o Médico avalie a aplicabilidade.
4. WHEN o Assistente utiliza um Artigo_Científico cujo campo reasoning_required_pred for "yes", THE Assistente SHALL exibir a justificativa longa (LONG_ANSWER) do artigo junto à resposta, indicando que a interpretação requer raciocínio clínico adicional.
5. IF a pergunta do Médico não puder ser respondida com base na Base_de_Conhecimento disponível, THEN THE Assistente SHALL informar que não possui informação suficiente para responder e indicar ao menos um Termo_MeSH ou especialidade médica relevante para orientar a busca do Médico.
6. IF o nível de confiança do Assistente na relevância da resposta for inferior ao limiar definido na configuração do sistema, THEN THE Assistente SHALL exibir um aviso de baixa confiança junto à resposta, indicando que a informação pode não ser totalmente aplicável ao contexto clínico descrito.
7. THE Assistente SHALL exibir, em todas as respostas clínicas, um aviso fixo indicando que as sugestões são de apoio à decisão e não substituem o julgamento clínico do Médico.
8. WHEN o Assistente não conseguir mapear a pergunta do Médico a nenhuma intenção clínica reconhecida, THE Assistente SHALL solicitar esclarecimento por meio de no máximo 3 perguntas objetivas antes de emitir qualquer resposta clínica.
9. WHEN o Assistente recebe uma pergunta redigida em português do Brasil, THE Assistente SHALL processar a pergunta e retornar a resposta em português do Brasil.
10. IF a Base_de_Conhecimento estiver indisponível no momento da consulta, THEN THE Assistente SHALL informar ao Médico que o serviço está temporariamente indisponível e não retornar nenhuma resposta clínica parcial.
11. WHEN o Assistente não receber resposta do serviço de processamento de linguagem natural dentro de 10 segundos, THE Assistente SHALL cancelar a requisição e informar o Médico sobre o timeout.

---

### Requirement 2: Sugestão de Condutas Clínicas Baseadas em Protocolos e Evidências

**User Story:** Como Médico, quero receber sugestões de condutas clínicas baseadas nos protocolos internos do hospital e em evidências científicas indexadas, para que eu tome decisões mais seguras e alinhadas às melhores práticas disponíveis.

#### Acceptance Criteria

1. WHEN um Médico descreve o quadro clínico de um Paciente, THE Assistente SHALL sugerir Condutas_Clínicas recuperando tanto Protocolos vigentes do hospital quanto Artigos_Científicos da Base_de_Conhecimento cujos Termos_MeSH correspondam às condições clínicas descritas.
2. WHEN o Assistente sugere uma Conduta_Clínica baseada em um Protocolo, THE Assistente SHALL apresentar o identificador e o título do Protocolo, o nível de evidência classificado conforme o Protocolo e todas as contraindicações listadas no Protocolo de referência.
3. WHEN o Assistente sugere uma Conduta_Clínica baseada em um Artigo_Científico, THE Assistente SHALL apresentar o identificador do artigo, a pergunta clínica (QUESTION), a Decisão_Final e os trechos de contexto (CONTEXTS) mais relevantes para o quadro descrito.
4. WHEN o Assistente apresenta sugestões de Conduta_Clínica, THE Assistente SHALL ordenar os resultados exibindo primeiro os Protocolos vigentes do hospital e, em seguida, os Artigos_Científicos ordenados do mais recente para o mais antigo pelo campo YEAR.
5. IF o quadro clínico descrito pelo Médico contiver ao menos um termo explicitamente classificado como emergência ou urgência nos Protocolos do hospital, THEN THE Assistente SHALL exibir a sugestão de Conduta_Clínica em destaque visual diferenciado antes de quaisquer outras sugestões e recomendar o acionamento imediato da equipe de emergência.
6. WHEN múltiplos Protocolos forem aplicáveis ao quadro clínico descrito, THE Assistente SHALL apresentar no máximo 5 Protocolos relevantes, ordenados de forma decrescente pelo número de características clínicas descritas que correspondem ao escopo de aplicabilidade de cada Protocolo.
7. IF nenhum Protocolo vigente e nenhum Artigo_Científico da Base_de_Conhecimento cobrir o quadro clínico descrito pelo Médico, THEN THE Assistente SHALL informar que não há evidência disponível para o quadro descrito e recomendar que o Médico consulte um especialista.

---

### Requirement 3: Verificação de Exames Pendentes do Paciente

**User Story:** Como Médico, quero consultar os exames pendentes de um Paciente, para que eu acompanhe o status diagnóstico e tome decisões clínicas com informações atualizadas.

#### Acceptance Criteria

1. WHEN um Médico solicita a verificação de exames de um Paciente com número de prontuário não vazio e no formato registrado no sistema hospitalar, THE Assistente SHALL recuperar e exibir a lista de Exames com status Solicitado, Coletado ou Em Análise do Prontuário do Paciente.
2. WHEN o Assistente exibe a lista de Exames pendentes, THE Assistente SHALL apresentar para cada Exame: o nome, a data de solicitação, o nome do solicitante e o status atual, sendo os valores válidos de status: Solicitado, Coletado, Em Análise, Concluído e Cancelado.
3. IF o número de prontuário fornecido não corresponder a nenhum Paciente cadastrado no sistema hospitalar, THEN THE Assistente SHALL exibir a mensagem "Paciente não encontrado" e solicitar que o Médico verifique e corrija o número de prontuário informado.
4. IF o Paciente identificado não possuir nenhum Exame com status Solicitado, Coletado ou Em Análise, THEN THE Assistente SHALL exibir a mensagem "Nenhum exame pendente encontrado para este paciente" em vez de uma lista vazia.
5. WHEN um resultado de Exame for disponibilizado no sistema hospitalar, THE Assistente SHALL atualizar o status do Exame para Concluído em até 60 segundos após a disponibilização, realizando novas tentativas de atualização a cada 10 segundos até que a atualização seja confirmada.

---

### Requirement 4: Sugestão de Tratamentos Baseada no Perfil do Paciente e em Evidências Científicas

**User Story:** Como Médico, quero receber sugestões de tratamento personalizadas com base no perfil clínico do Paciente e em evidências científicas indexadas, para que eu considere tanto as características individuais do Paciente quanto as melhores práticas disponíveis ao definir a conduta terapêutica.

#### Acceptance Criteria

1. WHEN um Médico solicita sugestões de tratamento para um Paciente identificado, THE Assistente SHALL analisar o Prontuário do Paciente e sugerir tratamentos recuperando Protocolos vigentes do hospital e Artigos_Científicos cujos Termos_MeSH correspondam ao diagnóstico ativo registrado no Prontuário.
2. WHEN o Assistente apresenta sugestões de tratamento, THE Assistente SHALL exibir separadamente as sugestões baseadas em Protocolos e as baseadas em Artigos_Científicos, indicando para cada Artigo_Científico a Decisão_Final e o ano de publicação (YEAR).
3. IF a Decisão_Final de um Artigo_Científico utilizado na sugestão de tratamento for "no", THEN THE Assistente SHALL não incluir esse artigo como suporte à sugestão e poderá exibi-lo como evidência contrária, se relevante para o quadro clínico.
4. IF nenhum tratamento compatível com os Protocolos vigentes existir para a condição identificada no Prontuário do Paciente, THEN THE Assistente SHALL sugerir os tratamentos clinicamente mais adequados disponíveis nos Artigos_Científicos acompanhados de um aviso explícito indicando que estão fora dos Protocolos padrão do hospital.
5. WHEN o Assistente sugere um tratamento e o Prontuário do Paciente contém ao menos um medicamento em uso registrado, THE Assistente SHALL verificar e exibir todas as interações medicamentosas identificadas entre o tratamento sugerido e os medicamentos em uso.
6. IF o Prontuário do Paciente não contiver nenhum medicamento em uso registrado, THEN THE Assistente SHALL informar ao Médico que não há medicamentos em uso registrados e prosseguir com a sugestão de tratamento sem verificação de interações.
7. IF o processo de verificação de interações medicamentosas estiver indisponível, THEN THE Assistente SHALL bloquear a exibição da sugestão de tratamento e informar ao Médico que a verificação de interações não pôde ser realizada, solicitando que tente novamente mais tarde.
8. WHEN o Assistente sugere um tratamento, THE Assistente SHALL verificar e exibir todas as contraindicações identificadas com base nas alergias, comorbidades e histórico clínico registrados no Prontuário do Paciente.
9. IF o Prontuário do Paciente não contiver ao menos um dos seguintes campos preenchidos — diagnóstico ativo, lista de medicamentos em uso ou alergias registradas — THEN THE Assistente SHALL informar ao Médico quais campos estão ausentes e solicitar que os forneça ou os registre no Prontuário antes de prosseguir com a sugestão.
