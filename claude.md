# claude.md

**Authoritative reference. Always loaded. Always trusted. Never repeat.**

---

## 1. Project Overview

- **Purpose**: Chatbot inteligente para loja de materiais de construção (PT-BR). Busca de produtos, carrinho, checkout, criação de pedidos, e **modo consultivo com IA**.
- **Stack**: Python 3.10+, FastAPI, SQLAlchemy (sync ORM), PostgreSQL, sentence-transformers (RAG), Chroma (vector DB), **Groq LLM** (llama-3.3-70b).
- **UI**: Streamlit (apenas teste). Produção espera integração externa de chat.
- **Core flow**: Message → `flow_controller.py` → routing → response → DB persistence.

### Diferenciais de Inteligência

1. **Interpretação Semântica** - Entende respostas naturais: "sim, a 2", "essa segunda", "quero o primeiro"
2. **Síntese Técnica Contextual** - Gera explicações técnicas usando TODOS os fatores coletados
3. **Investigação Progressiva** - Coleta contexto de uso antes de recomendar (vendedor consultivo)

---

## 2. Directory & File Map

```
/
├── app/
│   ├── api_routes.py               # FastAPI /chat endpoint
│   ├── flow_controller.py          # Main message router/orchestrator
│   ├── session_state.py            # Persistent user state (DB-backed JSONB)
│   ├── cart_service.py             # Cart (Orcamento) CRUD
│   ├── product_search.py           # Product search (RAG + SQL fallback)
│   ├── rag_products.py             # Vector store (Chroma) management
│   ├── parsing.py                  # Extract product hints, quantities, kg
│   ├── text_utils.py               # Normalization, intent detection, sanitization
│   ├── guardrails.py               # Block forbidden claims (email/tracking)
│   ├── persistence.py              # Save chat history to DB
│   ├── preferences.py              # Extract delivery/payment/address
│   ├── constants.py                # Static strings (greetings, keywords, regex)
│   ├── mercadopago_payments.py     # PIX/card payment generation
│   ├── llm_service.py              # **LLM (Groq) - interpretação semântica + síntese técnica**
│   ├── consultive_mode.py          # **Modo consultivo - responde perguntas abertas (RAG)**
│   ├── checkout.py                 # Alias for checkout_handlers (backward compat)
│   ├── checkout_handlers/
│   │   ├── main.py                 # Checkout flow orchestration
│   │   ├── extractors.py           # Extract name, phone, email, payment, delivery
│   │   ├── validators.py           # Check finalize intent, readiness
│   │   ├── order_creation.py       # Create Pedido + PedidoChat from Orcamento
│   │   ├── payment_handling.py     # Generate payment block (PIX/card/cash)
│   ├── flows/
│   │   ├── quantity.py             # Handle pending quantity input
│   │   ├── product_selection.py    # Handle suggestion choice (+ LLM fallback)
│   │   ├── removal.py              # Item removal flow
│   │   ├── usage_context.py        # **Pergunta contexto de uso para produtos genéricos**
│   │   ├── consultive_investigation.py  # **Investigação progressiva (coleta contexto)**
│   │   ├── technical_recommendations.py # **Regras técnicas + síntese LLM**
├── tests/
│   ├── test_checkout_fix.py        # Unit tests for extractors
│   ├── test_text_utils.py          # Unit tests for text utils + guardrails
│   ├── test_no_premature_inference.py  # Testes de bloqueio de inferência prematura
│   ├── conftest.py                 # Pytest setup
├── database.py                      # SQLAlchemy models + session factory
├── main.py                          # FastAPI app + lifespan (init DB, rebuild index)
├── streamlit_app.py                 # Streamlit UI (testing only)
├── requirements.txt                 # Dependencies
├── .env                             # Config (DB, MP tokens, GROQ_API_KEY)
├── data/chroma_products/            # Chroma vector store (persisted)
└── INTELLIGENCE_UPGRADE.md          # Documentação das melhorias de inteligência
```

---

## 3. Responsibility Matrix

| **What**                              | **Where**                                          |
|---------------------------------------|----------------------------------------------------|
| Message routing                       | `flow_controller.py` → `handle_message()`          |
| Product search (RAG + SQL)            | `product_search.py` → `db_find_best_products()`    |
| Vector store (embeddings)             | `rag_products.py`                                  |
| Cart operations                       | `cart_service.py`                                  |
| User state (persistent)               | `session_state.py` (DB: `chat_session_state`)      |
| Checkout flow                         | `checkout_handlers/main.py` → `handle_checkout()`  |
| Order creation                        | `checkout_handlers/order_creation.py`              |
| Payment (PIX/card)                    | `mercadopago_payments.py`                          |
| Extractors (name, phone, email)       | `checkout_handlers/extractors.py`                  |
| Text normalization                    | `text_utils.py` → `norm()`, `sanitize_reply()`     |
| Guardrails (forbidden claims)         | `guardrails.py` → `apply_guardrails()`             |
| Chat history persistence              | `persistence.py` → `save_chat_db()`                |
| Product hint extraction               | `parsing.py` → `extract_product_hint()`            |
| Preferences (delivery/payment)        | `preferences.py`                                   |
| **LLM - Interpretação de escolha**    | `llm_service.py` → `interpret_choice()`            |
| **LLM - Síntese técnica**             | `llm_service.py` → `generate_technical_synthesis()`|
| **Perguntas consultivas (RAG)**       | `consultive_mode.py` → `answer_consultive_question()`|
| **Contexto de uso (pré-venda)**       | `flows/usage_context.py` → `ask_usage_context()`   |
| **Investigação progressiva**          | `flows/consultive_investigation.py` → `continue_investigation()` |
| **Regras técnicas por produto**       | `flows/technical_recommendations.py` → `get_technical_recommendation()` |
| **Gate de validação de contexto**     | `flows/technical_recommendations.py` → `can_generate_technical_answer()` |
| Streamlit UI (test only)              | `streamlit_app.py`                                 |
| FastAPI endpoint                      | `app/api_routes.py` → `/chat`                      |
| DB models                             | `database.py`                                      |

---

## 4. Fluxos de Conversa

### 4.1 Fluxo Padrão (Produto Específico)

```
User: "quero trena 5m"
Bot: "Encontrei estas opções: [lista]. Qual você quer?"
User: "a 2"
Bot: "Quantas unidades?"
User: "3"
Bot: "Adicionei 3x Trena 5m ao carrinho."
```

### 4.2 Fluxo Consultivo (Produto Genérico)

```
User: "quero cimento"
Bot: "Claro! É pra qual uso?"                    ← Pergunta contexto
User: "pra laje"
Bot: "É área interna ou externa?"                ← Investigação progressiva
User: "externa"
Bot: "Coberta ou exposta à chuva/sol?"
User: "exposta"
Bot: "Uso residencial ou carga pesada?"
User: "residencial"
Bot: [Síntese técnica LLM] + [produtos] + "Faz sentido pra sua obra?"
User: "sim, a segunda"                           ← Interpretação semântica LLM
Bot: "Quantas unidades?"
```

### 4.3 Produtos Genéricos (Investigação Obrigatória)

| Produto    | Contextos Coletados                    |
|------------|----------------------------------------|
| cimento    | aplicação, ambiente, exposição, carga  |
| tinta      | superfície, ambiente                   |
| areia      | aplicação, granulometria               |
| brita      | aplicação, tamanho                     |
| argamassa  | aplicação, tipo                        |

---

## 5. Inteligência LLM (Groq)

### 5.1 Modelo

- **Provider**: Groq (API)
- **Model**: `llama-3.3-70b-versatile`
- **Config**: `.env` → `GROQ_API_KEY`

### 5.2 Funções LLM

| Função                         | Uso                                    | Temperature | Tokens |
|--------------------------------|----------------------------------------|-------------|--------|
| `interpret_choice()`           | Interpreta "sim, a 2", "essa segunda"  | 0.1         | 10     |
| `generate_technical_synthesis()` | Gera explicação técnica contextual   | 0.3         | 200    |
| `extract_product_factors()`    | Mapeia fatores técnicos por categoria  | N/A         | N/A    |

### 5.3 Arquitetura de Fallback

```
1. Fast path: parse_choice_indices() (regex simples)
2. Se falhou: interpret_choice() (LLM)
3. Se LLM falhou: retorna None (não identificou)
```

```
1. Gate: can_generate_technical_answer() valida contexto
2. Se válido: generate_technical_synthesis() (LLM)
3. Se LLM falhou: usa reasoning hardcoded (TECHNICAL_RULES)
```

### 5.4 Fatores Técnicos por Categoria

```python
CATEGORY_FACTORS = {
    "cimento": ["resistência a sulfatos", "resistência mecânica", "durabilidade", ...],
    "tinta": ["resistência à umidade", "resistência UV", "lavabilidade", ...],
    "areia": ["granulometria", "trabalhabilidade", "acabamento", ...],
    "brita": ["tamanho das pedras", "compactação", "drenagem", ...],
    "argamassa": ["aderência", "trabalhabilidade", "tempo de uso", ...],
}
```

---

## 6. Gate de Segurança (Inferência Prematura)

### Função Central: `can_generate_technical_answer()`

**Localização**: `flows/technical_recommendations.py:198`

**REGRA ABSOLUTA**: Retorna `False` se NÃO houver contexto explícito coletado.

```python
# NUNCA gerar síntese sem contexto explícito
if not can_generate_technical_answer(product, context):
    return ""  # Bloqueia LLM
```

### Validações por Produto

| Produto   | Requisitos Mínimos                           |
|-----------|----------------------------------------------|
| cimento   | application + environment (exceto fundação/reboco/piso) |
| tinta     | surface + environment                        |
| areia     | application                                  |
| brita     | application                                  |
| argamassa | application                                  |

---

## 7. Data & Persistence

- **DB**: PostgreSQL, sync SQLAlchemy ORM.
- **Session factory**: `database.SessionLocal()` (context manager pattern).
- **State**: `chat_session_state` table (JSONB column). Accessed via `session_state.py`.
- **Cart**: `orcamentos` + `itens_orcamento` tables. Status: `aberto` / `fechado`.
- **Orders**: `pedidos` + `itens_pedido` + `pedidos_chat` (chat-specific metadata).
- **Vector store**: Chroma (local disk, `data/chroma_products/`). Rebuilt on startup.
- **No async**: All DB ops are synchronous.

### State Fields (Modo Consultivo)

| Field                            | Tipo    | Descrição                              |
|----------------------------------|---------|----------------------------------------|
| `awaiting_usage_context`         | bool    | Aguardando resposta de contexto        |
| `usage_context_product_hint`     | str     | Produto genérico sendo investigado     |
| `consultive_investigation`       | bool    | Investigação progressiva ativa         |
| `consultive_investigation_step`  | int     | Passo atual da investigação            |
| `consultive_application`         | str     | Aplicação informada (laje, reboco...)  |
| `consultive_environment`         | str     | Ambiente (interna/externa)             |
| `consultive_exposure`            | str     | Exposição (coberto/exposto)            |
| `consultive_load_type`           | str     | Carga (residencial/pesada)             |
| `consultive_surface`             | str     | Superfície (parede/madeira/metal)      |
| `consultive_grain`               | str     | Granulometria (fino/médio/grosso)      |
| `consultive_size`                | str     | Tamanho brita (1/2/3/4)                |
| `consultive_product_hint`        | str     | Produto em investigação                |
| `consultive_recommendation_shown`| bool    | Já mostrou recomendação técnica        |

---

## 8. Runtime & Execution

- **Python**: 3.10+
- **Run chatbot API**: `uvicorn main:app --reload`
- **Run Streamlit (test)**: `streamlit run streamlit_app.py`
- **Run tests**: `pytest tests/`
- **Environment**: `.env` file (DB creds, MP tokens, GROQ_API_KEY)
- **Init on startup**: `main.py` lifespan → `init_db()` + `rebuild_product_index()`

### Variáveis de Ambiente (.env)

```
DATABASE_URL=postgresql://...
MERCADOPAGO_ACCESS_TOKEN=...
GROQ_API_KEY=<GROQ_API_KEY>
```

---

## 9. Architectural Rules

### ALWAYS

- Route messages through `flow_controller.py`.
- Extract user state via `session_state.get_state(session_id)`.
- Update state via `session_state.patch_state(session_id, {...})`.
- Sanitize all bot replies via `text_utils.sanitize_reply()`.
- Persist chat history via `persistence.save_chat_db()`.
- Use `cart_service` for all cart operations (never raw SQL).
- Create orders via `checkout_handlers/order_creation.py`.
- Extract user inputs (name, phone, email) via `checkout_handlers/extractors.py`.
- Validate email before payment generation (`mercadopago_payments._validate_email()`).
- Return `(reply: str, needs_human: bool)` from handlers.
- **Use `can_generate_technical_answer()` antes de chamar LLM para síntese.**
- **Resetar contexto consultivo quando novo produto genérico é solicitado.**

### NEVER

- Bypass `flow_controller.py` for message handling.
- Mutate state without `patch_state()`.
- Return raw LLM output without `sanitize_reply()`.
- Create orders without closing the `Orcamento` (status → `fechado`).
- Generate PIX payment without valid email.
- Use async DB operations (project is fully sync).
- Hardcode product IDs or catalog data.
- Repeat explanations of project structure in responses.
- **Gerar síntese técnica sem contexto explícito coletado.**
- **Chamar LLM sem fallback hardcoded.**

---

## 10. Common Pitfalls

| **Problem**                                  | **Fix**                                                                 |
|----------------------------------------------|-------------------------------------------------------------------------|
| Cart appears empty after checkout            | Cart closes when order is created. Check `last_order_summary` in state. |
| Payment generation fails                     | Check email validity. PIX requires real email.                         |
| Vector search returns nothing                | Fallback to SQL ILIKE. Check `rag_products._ensure_index_ready()`.     |
| State not persisting across sessions         | Ensure `session_id` matches across requests.                           |
| Guardrails trigger unnecessarily             | Review `guardrails.py` patterns.                                       |
| Duplicate products in suggestions            | `product_search._normalize_candidate()` dedupes by ID.                 |
| Checkout stuck asking for data repeatedly    | Check `validators.ready_to_checkout()`.                                |
| LLM não interpreta escolha                   | Verificar se `GROQ_API_KEY` está no `.env`.                            |
| Síntese técnica genérica demais              | Verificar se contexto está completo antes de chamar LLM.               |
| Investigação não inicia                      | Produto precisa estar em `GENERIC_PRODUCTS` (usage_context.py).        |
| Bot mostra produtos antes de coletar contexto| Gate `can_generate_technical_answer()` deveria bloquear.               |

---

## 11. Extensibilidade

### Adicionar Nova Categoria de Produto

1. **usage_context.py**: Adicionar em `GENERIC_PRODUCTS`
2. **consultive_investigation.py**: Adicionar fluxo em `INVESTIGATION_FLOWS`
3. **technical_recommendations.py**: Adicionar regras em `TECHNICAL_RULES`
4. **llm_service.py**: Adicionar fatores em `CATEGORY_FACTORS`

### Exemplo: Adicionar "telha"

```python
# usage_context.py
GENERIC_PRODUCTS["telha"] = {
    "question": "Certo! É telha pra qual tipo de telhado?",
    "contexts": {...}
}

# consultive_investigation.py
INVESTIGATION_FLOWS["telha"] = [
    {"step": 1, "question": "...", "field": "consultive_telha_type", ...}
]

# technical_recommendations.py
TECHNICAL_RULES["telha"] = {
    ("telhado", "residencial"): {...}
}

# llm_service.py
CATEGORY_FACTORS["telha"] = ["resistência", "impermeabilidade", ...]
```

---

## 12. Token Economy Rules

### Default Response Mode

- **Brevity first**: Assume all context is in `claude.md`.
- **Diffs only**: When editing files, show minimal diff.
- **No repetition**: Never restate project structure, architecture, or file map.
- **No teaching**: Skip Python/SQL basics. Assume competence.
- **Locate, don't explain**: Point to file:line instead of describing logic.

### Preferred Formats

- **Code changes**: Diff format or inline with `# CHANGE:` comments.
- **File location**: `file.py:123` or `module.function()`.
- **Lists**: Bullets, no prose.
- **Answers**: Direct, <3 sentences unless debugging.

---

## 13. Prompt Shortcuts

| **Shortcut**       | **Meaning**                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| `debug X`          | Trace issue X. Show file:line, minimal explanation.                        |
| `refactor X`       | Improve X. Show diff only.                                                 |
| `add feature X`    | Implement X. Locate integration point, show minimal code.                  |
| `trace flow X`     | Follow data/message flow for X. List functions, no prose.                 |
| `locate logic X`   | Find where X happens. Return file:line.                                    |
| `fix bug X`        | Diagnose and patch X. Diff format.                                         |
| `optimize X`       | Reduce tokens/latency/DB calls in X. Show changes only.                    |
| `add product X`    | Adicionar categoria X. Mostrar 4 arquivos a modificar.                     |

---

## 14. What NOT to Explain or Repeat

### Never Repeat

- Project structure (it's in §2).
- File responsibilities (it's in §3).
- Flow diagrams (it's in §4).
- LLM architecture (it's in §5).
- Gate rules (it's in §6).
- Architectural rules (it's in §9).

### Assume Known

- Python syntax and stdlib.
- SQL basics and ORM patterns.
- FastAPI routing and Pydantic models.
- Groq/LLM API basics.
- PostgreSQL, JSONB, vector stores.
- Portuguese chatbot domain (construction materials).

---

**End of claude.md. All future interactions must honor token economy rules.**
