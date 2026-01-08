# claude.md

**Authoritative reference. Always loaded. Always trusted. Never repeat.**

---

## 1. Project Overview

- **Purpose**: Chatbot for construction materials store (Portuguese). Product search, cart, checkout, order creation.
- **Stack**: Python 3.x, FastAPI, SQLAlchemy (sync ORM), PostgreSQL, sentence-transformers (RAG), Chroma (vector DB).
- **UI**: Streamlit (testing only). Production expects external chat integration.
- **Core flow**: Message → `flow_controller.py` → routing → response → DB persistence.

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
│   ├── checkout.py                 # Alias for checkout_handlers (backward compat)
│   ├── checkout_handlers/
│   │   ├── main.py                 # Checkout flow orchestration
│   │   ├── extractors.py           # Extract name, phone, email, payment, delivery
│   │   ├── validators.py           # Check finalize intent, readiness
│   │   ├── order_creation.py       # Create Pedido + PedidoChat from Orcamento
│   │   ├── payment_handling.py     # Generate payment block (PIX/card/cash)
│   ├── flows/
│   │   ├── quantity.py             # Handle pending quantity input
│   │   ├── product_selection.py    # Handle suggestion choice
│   │   ├── removal.py              # Item removal flow
├── tests/
│   ├── test_checkout_fix.py        # Unit tests for extractors
│   ├── test_text_utils.py          # Unit tests for text utils + guardrails
│   ├── conftest.py                 # Pytest setup
├── database.py                      # SQLAlchemy models + session factory
├── main.py                          # FastAPI app + lifespan (init DB, rebuild index)
├── streamlit_app.py                 # Streamlit UI (testing only)
├── requirements.txt                 # Dependencies
├── .env                             # Config (DB, MP tokens, etc.)
└── data/chroma_products/            # Chroma vector store (persisted)
```

---

## 3. Responsibility Matrix

| **What**                          | **Where**                                      |
|-----------------------------------|------------------------------------------------|
| Message routing                   | `flow_controller.py` → `handle_message()`      |
| Product search (RAG + SQL)        | `product_search.py` → `db_find_best_products()`|
| Vector store (embeddings)         | `rag_products.py`                              |
| Cart operations                   | `cart_service.py`                              |
| User state (persistent)           | `session_state.py` (DB: `chat_session_state`)  |
| Checkout flow                     | `checkout_handlers/main.py` → `handle_checkout()`|
| Order creation                    | `checkout_handlers/order_creation.py`          |
| Payment (PIX/card)                | `mercadopago_payments.py`                      |
| Extractors (name, phone, email)   | `checkout_handlers/extractors.py`              |
| Text normalization                | `text_utils.py` → `norm()`, `sanitize_reply()` |
| Guardrails (forbidden claims)     | `guardrails.py` → `apply_guardrails()`         |
| Chat history persistence          | `persistence.py` → `save_chat_db()`            |
| Product hint extraction           | `parsing.py` → `extract_product_hint()`        |
| Preferences (delivery/payment)    | `preferences.py`                               |
| Streamlit UI (test only)          | `streamlit_app.py`                             |
| FastAPI endpoint                  | `app/api_routes.py` → `/chat`                  |
| DB models                         | `database.py`                                  |

---

## 4. Data & Persistence

- **DB**: PostgreSQL, sync SQLAlchemy ORM.
- **Session factory**: `database.SessionLocal()` (context manager pattern).
- **State**: `chat_session_state` table (JSONB column). Accessed via `session_state.py`.
- **Cart**: `orcamentos` + `itens_orcamento` tables. Status: `aberto` / `fechado`.
- **Orders**: `pedidos` + `itens_pedido` + `pedidos_chat` (chat-specific metadata).
- **Vector store**: Chroma (local disk, `data/chroma_products/`). Rebuilt on startup.
- **No async**: All DB ops are synchronous.

---

## 5. Runtime & Execution

- **Python**: 3.10+
- **Run chatbot API**: `uvicorn main:app --reload`
- **Run Streamlit (test)**: `streamlit run streamlit_app.py`
- **Environment**: `.env` file (DB creds, MP tokens, etc.)
- **Init on startup**: `main.py` lifespan → `init_db()` + `rebuild_product_index()`

---

## 6. Architectural Rules

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

### NEVER

- Bypass `flow_controller.py` for message handling.
- Mutate state without `patch_state()`.
- Return raw LLM output without `sanitize_reply()`.
- Create orders without closing the `Orcamento` (status → `fechado`).
- Generate PIX payment without valid email.
- Use async DB operations (project is fully sync).
- Hardcode product IDs or catalog data.
- Repeat explanations of project structure in responses.

---

## 7. Common Pitfalls

| **Problem**                                  | **Fix**                                                                 |
|----------------------------------------------|-------------------------------------------------------------------------|
| Cart appears empty after checkout            | Cart closes when order is created. Explain to user. Check `last_order_summary` in state. |
| Payment generation fails                     | Check email validity. PIX requires real email (not `@example.com`).    |
| Vector search returns nothing                | Fallback to SQL ILIKE. Check embeddings loaded (`rag_products._ensure_index_ready()`). |
| State not persisting across sessions         | Ensure `session_id` matches across requests. Check DB connection.      |
| Guardrails trigger unnecessarily             | Review `guardrails.py` patterns. Ensure bot doesn't claim email/tracking. |
| Duplicate products in suggestions            | `product_search._normalize_candidate()` dedupes by ID.                 |
| Checkout stuck asking for data repeatedly    | Check `validators.ready_to_checkout()`. Verify all fields collected.   |
| Streamlit chat doesn't reuse session         | Pass `session_id` from API response back to next request.              |

---

## 8. Token Economy Rules

### Default Response Mode

- **Brevity first**: Assume all context is in `claude.md`.
- **Diffs only**: When editing files, show minimal diff. No full file unless requested.
- **No repetition**: Never restate project structure, architecture, or file map.
- **No teaching**: Skip Python/SQL basics. Assume competence.
- **Locate, don't explain**: Point to file:line instead of describing logic.

### When Explanations Are Allowed

- User explicitly asks "why" or "explain".
- Debugging complex edge case (after narrowing down).
- Proposing architectural change (after confirming intent).

### Preferred Formats

- **Code changes**: Diff format or inline with `# CHANGE:` comments.
- **File location**: `file.py:123` or `module.function()`.
- **Lists**: Bullets, no prose.
- **Answers**: Direct, <3 sentences unless debugging.

---

## 9. Prompt Shortcuts

Use these to get concise, targeted responses:

| **Shortcut**       | **Meaning**                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| `debug X`          | Trace issue X. Show file:line, minimal explanation.                        |
| `refactor X`       | Improve X. Show diff only.                                                 |
| `add feature X`    | Implement X. Locate integration point, show minimal code.                  |
| `trace flow X`     | Follow data/message flow for X. List functions, no prose.                 |
| `locate logic X`   | Find where X happens. Return file:line.                                    |
| `fix bug X`        | Diagnose and patch X. Diff format.                                         |
| `optimize X`       | Reduce tokens/latency/DB calls in X. Show changes only.                    |

---

## 10. What NOT to Explain or Repeat

### Never Repeat

- Project structure (it's in §2).
- File responsibilities (it's in §3).
- Architectural rules (it's in §6).
- How FastAPI/SQLAlchemy/Streamlit work (assumed knowledge).
- How to run the project (it's in §5).

### Assume Known

- Python syntax and stdlib.
- SQL basics and ORM patterns.
- FastAPI routing and Pydantic models.
- Streamlit components.
- PostgreSQL, JSONB, vector stores (conceptually).
- Portuguese chatbot domain (construction materials, checkout flow).

### Only Explain When

- Debugging reveals unexpected behavior.
- User asks "why does X happen?"
- Proposing breaking change.

---

**End of claude.md. All future interactions must honor token economy rules.**
