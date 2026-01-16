# Ultimos 5 prompts: o que foi feito e como usar

Este arquivo resume as ultimas mudancas (router, planner consultivo, render LLM e feature flag).
Tudo segue com fallback seguro: se LLM falhar, o fluxo atual continua igual.

## 1) LLM Router integrado no flow_controller

### O que foi implementado
- Um roteador LLM decide a intencao e a acao (JSON).
- O router so roda quando nao ha fluxos pendentes (quantidade, escolha, checkout, etc.).
- Se o router falhar ou retornar None, o fluxo atual continua.

### Onde foi aplicado
- `app/llm_service.py`: `route_intent(...)` + validacao.
- `app/flow_controller.py`: chamada opt-in do router com gating.
- `tests/test_llm_router_integration.py`: testes de integracao (mock).

### Como usar
- O router ja esta ativo no fluxo, mas so entra quando:
  - nao ha escolha pendente (ex: responder "2")
  - nao ha quantidade pendente
  - nao esta em checkout
  - nao esta em investigacao consultiva ou aguardando contexto

## 2) Planner consultivo (diagnostico curto)

### O que foi implementado
- Planner LLM decide o proximo passo no modo consultivo.
- Ele pergunta 1 coisa por vez e evita repetir.
- So permite sintese tecnica quando o gate `can_generate_technical_answer()` permite.

### Onde foi aplicado
- `app/llm_service.py`: `plan_consultive_next_step(...)` + validacao.
- `app/session_state.py`: novos campos anti-repeticao:
  - `asked_context_fields`
  - `last_consultive_question_key`
- `app/flow_controller.py`: uso do planner nas acoes:
  - `ASK_USAGE_CONTEXT`
  - `ANSWER_WITH_RAG`
- `tests/test_consultive_planner.py`: testes do planner e fallback.

### Como usar (exemplos)
1) Usuario: "qual melhor cimento pra laje externa?"
   - Planner pergunta 1 campo faltante (ex: carga).
2) Usuario: "tinta pro banheiro"
   - Planner pergunta umidade ou tipo de area.
3) Quando o contexto ja esta completo:
   - Planner retorna READY_TO_ANSWER.
   - O sistema gera sintese tecnica com o gate.

## 3) Renderizacao final por LLM (opcional)

### O que foi implementado
- A LLM pode "redigir" a resposta final com base em facts.
- Ela nao pode inventar dados. Se inventar, cai em fallback.

### Onde foi aplicado
- `app/llm_service.py`: `render_customer_message(...)`
- `app/flow_controller.py`: aplicado apenas em:
  - resposta de catalogo
  - resposta consultiva final (sintese tecnica)
- `tests/test_render_customer_message.py`: testes do render.

### Como usar (facts)
- Catalogo:
  {
    "type": "catalog",
    "query": "cimento",
    "items": [{"id":"1","name":"Cimento CP II","price":"30.00","unit":"UN"}],
    "next_question": "Qual voce quer?"
  }
- Consultivo final:
  {
    "type": "consultive_answer",
    "summary": "texto da sintese tecnica",
    "recommended_next_steps": ["Quer que eu te ajude a escolher e comprar?"],
    "suggested_items": []
  }

## 4) Feature flag para renderizacao

### O que foi implementado
- Flag de ambiente para ligar/desligar a renderizacao LLM.
- Default: desligado (false).

### Onde foi aplicado
- `app/settings.py`: `LLM_RENDERING_ENABLED`
- `app/llm_service.py`: `maybe_render_customer_message(...)`
- `app/flow_controller.py`: usa o helper no catalogo e no consultivo final.

### Como usar
- Desligado (default):
  - nao defina a variavel, ou use `LLM_RENDERING_ENABLED=false`.
  - o sistema usa templates atuais direto.
- Ligado:
  - `LLM_RENDERING_ENABLED=true`
  - a renderizacao e tentada apenas nos 2 pontos previstos.

## 5) Como testar rapidamente

Com o venv ativo:
- `python -m pytest -q`

Observacoes:
- Warnings existentes do pytest continuam iguais (retorno bool em testes antigos).
- Nao ha impacto em checkout, carrinho ou fluxos pendentes.
