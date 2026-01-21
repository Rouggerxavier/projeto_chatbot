# CODEX - arquitetura do projeto

## Visao geral

Este projeto e um chatbot de materiais de construcao com:
- API FastAPI para chat e webhook WhatsApp
- camada consultiva (perguntas tecnicas + recomendacao)
- busca de produtos via SQL + RAG (Chroma)
- fluxo de carrinho e checkout com persistencia em banco
- guardrails para reduzir alucinacao

## Fluxo principal (alto nivel)

1) Entrada do usuario -> `app/api_routes.py` (`/chat`) ou `app/whatsapp_webhook.py` (webhook).
2) Orquestracao -> `app/flow_controller.py` (`handle_message`).
3) Detecao de intents/estado -> parsing + regras + LLM router/planner.
4) Busca e recomendacao -> `app/product_search.py`, `app/rag_products.py`, `app/rag_knowledge.py`.
5) Resposta final -> `app/text_utils.py` (sanitize + guardrails).
6) Persistencia -> `database.py`, `app/persistence.py`, `app/session_state.py`.
7) Checkout -> `app/checkout_handlers/*` + `app/cart_service.py`.

## Mapa de arquivos e responsabilidades

### Raiz do projeto

- `main.py`
  - Responsavel: cria o app FastAPI e executa init e reindex.
  - Funcoes principais: `lifespan` (init_db + rebuild indices).

- `database.py`
  - Responsavel: modelos SQLAlchemy e conexao.
  - Funcoes principais: `init_db`.
  - Classes principais: `Produto`, `Pedido`, `Orcamento`, `ItemOrcamento`, `ChatSessionState`, `ChatHistory`, `PedidoChat`.

- `requirements.txt`
  - Dependencias do projeto.

- `streamlit_app.py`
  - UI local para teste do chatbot via API.

- `simulate_whatsapp.py`
  - Envia payload de teste para webhook do WhatsApp.

- `demo_intelligence.py`
  - Demo local das funcoes LLM (interpretacao e sintese).
  - Funcoes principais: `demo_choice_interpretation`, `demo_technical_synthesis`.

- `COMO_USAR_NOVAS_FUNCIONALIDADES.md`
  - Guia de uso das features.

- `INTELLIGENCE_UPGRADE.md`
  - Documento tecnico das melhorias LLM.

- `ULTIMAS_ATUALIZACOES.md`
  - Changelog resumido.

- `claude.md`
  - Instrucoes internas/operacionais.

- `data/knowledge/faq.json`
  - Base de conhecimento usada no RAG tecnico.

- `data/chroma_products/*`
  - Indice vetorial do catalogo (gerado).

### API e entrada de mensagens

- `app/api_routes.py`
  - Responsavel: endpoint `/chat` da API.
  - Funcoes principais: `chat_endpoint`.

- `app/whatsapp_webhook.py`
  - Responsavel: webhook do WhatsApp (GET verify + POST messages).
  - Funcoes principais: `verify_webhook` (GET), `receive_whatsapp_message` (POST), `send_whatsapp_reply`.

### Orquestracao central

- `app/flow_controller.py`
  - Responsavel: fluxo principal do chatbot.
  - Funcoes principais: `handle_message`, `_handle_consultive_planner`, `_search_consultive_catalog`,
    `_build_state_summary`, `_gate_generic_usage`, `_catalog_reply_for_query`.

### Guardrails e utilitarios de texto

- `app/guardrails.py`
  - Responsavel: remover claims proibidos e anexar nota segura.
  - Funcoes principais: `apply_guardrails`.

- `app/text_utils.py`
  - Responsavel: normalizacao e filtros antes de responder.
  - Funcoes principais: `norm`, `sanitize_reply`, `is_consultive_question`, `has_product_intent`.

### Parsing e regras de busca

- `app/parsing.py`
  - Responsavel: extrair quantidade, unidades e hint de produto.
  - Funcoes principais: `extract_kg_quantity`, `extract_units_quantity`, `extract_product_hint`.

- `app/search_utils.py`
  - Responsavel: extrair constraints do contexto consultivo.
  - Funcoes principais: `extract_catalog_constraints_from_consultive`.

- `app/product_search.py`
  - Responsavel: busca SQL + fallback e formatacao do catalogo.
  - Funcoes principais: `db_find_best_products`, `db_find_best_products_with_constraints`,
    `format_options`, `parse_choice_indices`.

### RAG e indices vetoriais

- `app/rag_products.py`
  - Responsavel: embeddings e busca semantica no catalogo.
  - Funcoes principais: `search_products`, `search_products_semantic`, `rebuild_products_index`.

- `app/rag_knowledge.py`
  - Responsavel: busca semantica no FAQ tecnico.
  - Funcoes principais: `format_knowledge_answer`, `search_knowledge`, `rebuild_knowledge_index`.

### LLM e inteligencia

- `app/llm_service.py`
  - Responsavel: chamadas LLM (Groq) e validacao de saida.
  - Funcoes principais: `route_intent`, `plan_consultive_next_step`,
    `interpret_choice`, `generate_technical_synthesis`, `render_customer_message`.

- `app/consultive_mode.py`
  - Responsavel: respostas consultivas com base em RAG e regras.
  - Funcoes principais: `answer_consultive_question`, `_answer_usage_question`,
    `_answer_comparison_question`.

- `app/flows/technical_recommendations.py`
  - Responsavel: regras tecnicas e gate de contexto.
  - Funcoes principais: `can_generate_technical_answer`,
    `get_technical_recommendation`, `format_recommendation_text`.

### Fluxos consultivos e de escolha

- `app/flows/usage_context.py`
  - Responsavel: coletar contexto de uso para produtos genericos.
  - Funcoes principais: `ask_usage_context`, `handle_usage_context_response`,
    `start_usage_context_flow`.

- `app/flows/consultive_investigation.py`
  - Responsavel: investigacao progressiva por categoria.
  - Funcoes principais: `start_investigation`, `continue_investigation`.

- `app/flows/product_selection.py`
  - Responsavel: interpretar escolha do usuario nas sugestoes.
  - Funcoes principais: `handle_suggestions_choice`.

- `app/flows/quantity.py`
  - Responsavel: coletar quantidade e adicionar ao orcamento.
  - Funcoes principais: `set_pending_for_qty`, `handle_pending_qty`.

- `app/flows/removal.py`
  - Responsavel: remover itens do orcamento.
  - Funcoes principais: `start_remove_flow`, `handle_remove_choice`, `handle_remove_qty`.

### Carrinho, checkout e pagamento

- `app/cart_service.py`
  - Responsavel: CRUD de orcamento e itens.
  - Funcoes principais: `add_item_to_orcamento`, `format_orcamento`,
    `remove_item_from_orcamento`, `list_orcamento_items`.

- `app/checkout.py`
  - Responsavel: reexport de `handle_more_products_question`.

- `app/checkout_handlers/main.py`
  - Responsavel: fluxo de checkout (coleta dados e finaliza pedido).
  - Funcoes principais: `handle_more_products_question`, `handle_checkout`.

- `app/checkout_handlers/validators.py`
  - Responsavel: detectar intencao de finalizar.
  - Funcoes principais: `is_finalize_intent`.

- `app/checkout_handlers/order_creation.py`
  - Responsavel: cria pedido e fecha orcamento no banco.
  - Funcoes principais: `create_pedido_from_orcamento`, `summary_from_orcamento_items`.

- `app/checkout_handlers/payment_handling.py`
  - Responsavel: gerar bloco de pagamento (Mercado Pago).
  - Funcoes principais: `generate_payment_block`.

- `app/checkout_handlers/extractors.py`
  - Responsavel: extrair nome, email, telefone e preferencias.
  - Funcoes principais: `extract_phone`, `extract_email`, `extract_name`.

- `app/mercadopago_payments.py`
  - Responsavel: integracao com Mercado Pago.
  - Funcoes principais: `create_checkout_preference`, `_auth_headers`.

### Estado, preferencias e persistencia

- `app/session_state.py`
  - Responsavel: estado da sessao no banco.
  - Funcoes principais: `get_state`, `patch_state`, `reset_consultive_context`.

- `app/preferences.py`
  - Responsavel: detectar e atualizar preferencias de entrega/pagamento/endereco.
  - Funcoes principais: `maybe_register_address`, `handle_preferences`.

- `app/persistence.py`
  - Responsavel: grava historico da conversa.
  - Funcoes principais: `save_chat_db`.

- `app/constants.py`
  - Responsavel: constantes e regex globais.

- `app/settings.py`
  - Responsavel: flags via env.
  - Funcoes principais: `_env_bool`.

- `app/init.py`
  - Responsavel: marcador de pacote.

### Testes

- `tests/test_choice_parsing.py`
  - Valida parse de escolhas.
- `tests/test_llm_router.py`
  - Valida schema e regras do router.
- `tests/test_llm_router_integration.py`
  - Integracao do router no fluxo.
- `tests/test_consultive_planner.py`
  - Planner consultivo.
- `tests/test_consultive_catalog_search.py`
  - Busca consultiva com constraints.
- `tests/test_catalog_constraints.py`
  - Extracao de constraints.
- `tests/test_render_customer_message.py`
  - Renderizacao LLM segura.
- `tests/test_no_premature_inference.py`
  - Gate contra inferencia prematura.
- `tests/test_text_utils.py`
  - Normalizacao e detectores.
- `tests/test_checkout_fix.py`
  - Checkout e validacoes.
- `tests/conftest.py`
  - Fixtures.

- `test_consultive.py`
  - Fluxo consultivo geral (raiz).
- `test_full_flow.py`
  - Fluxo ponta a ponta.
- `test_integration_llm.py`
  - Integracao com LLM.
- `test_llm_intelligence.py`
  - Interpretacao e sintese LLM.
- `test_no_premature_inference.py`
  - Gate de contexto.
- `test_progressive_investigation.py`
  - Investigacao progressiva.
- `test_simple_validation.py`
  - Validacoes simples.
- `test_usage_context.py`
  - Fluxo de contexto de uso.
- `test_output.txt`
  - Saida de testes (arquivo auxiliar).

## Pontos de extensao comuns

- Guardrails e filtros: `app/guardrails.py`, `app/text_utils.py`
- Regras tecnicas: `app/flows/technical_recommendations.py`
- Fluxos consultivos: `app/flows/consultive_investigation.py`, `app/flows/usage_context.py`
- LLM router/planner: `app/llm_service.py`
- Busca: `app/product_search.py`, `app/rag_products.py`, `app/rag_knowledge.py`
