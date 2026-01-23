## Conversation Engine (LLM-first, guiado por catálogo)

- Catálogo enriquecido em `app/catalog_schema.py` define categorias, atributos, opções e perguntas.
- Extractor genérico em `app/nlu/extractor.py` (rule-based hoje, pronto para LLM) produz JSON:
  - `intent`, `product_query`, `category_guess`, `attributes`, `constraints`, `not_found_signal`.
- Policy determinística em `app/conversation/policy.py` decide a próxima ação:
  - Pergunta só atributos faltantes que afetam SKU (1 por vez) ou retorna `not_found`.
  - Limita re-perguntas a 2 vezes por atributo.
  - Pede quantidade quando atributos obrigatórios preenchidos.
- Integração no fluxo (`app/flow_controller.py`):
  - Detecta categoria, acumula atributos/asked, guarda últimos candidatos.
  - Respeita fluxo transacional (checkout intacto).

### Adicionar nova categoria
1. Edite `app/catalog_schema.py` e acrescente um item em `CATEGORY_SCHEMA` com:
   - `searchable_terms` (sinônimos)
   - `attributes`: `key`, `type`, `required_for_purchase`, `affects_sku`, `options/units`, `question_template`.
   - `related_items` (cross-sell sugerido)
2. O extractor usa as opções para normalizar valores; policy usa os atributos para decidir perguntas.
3. Se precisar ajustar pergunta, altere o `question_template` no schema (sem mudar código).

### NOT_FOUND e alternativas
- Se retrieval não retorna candidatos (ou `not_found_signal` for alto), a policy retorna ação `not_found`:
  - Mensagem: “Não encontrei esse item... Quer equivalente/alternativa?”
  - Pode sugerir até 3 `related_items` da categoria.
- Se usuário quiser exatamente aquele item, encaminhar para atendimento ou encerrar de forma útil (não inventar SKU).

### Configurar LLM
- A implementação atual do extractor é heurística para testes. Para usar LLM:
  - Defina um env (ex.: `LLM_MODE=production` e configure a chave, p. ex. `GROQ_API_KEY`).
  - No extractor, ramifique para usar o cliente de LLM mantendo o mesmo schema de saída.
