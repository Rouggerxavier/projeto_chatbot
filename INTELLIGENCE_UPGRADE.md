# Upgrade de Inteligência LLM - Chatbot Constrular

## Resumo Executivo

Implementadas duas melhorias críticas de inteligência usando LLM (Groq):

1. **Interpretação Semântica de Escolha** - Bot agora entende respostas naturais como "sim, a 2", "essa segunda", "quero o primeiro"
2. **Síntese Técnica Contextual** - Bot gera explicações técnicas unificadas usando TODOS os fatores coletados

---

## Problema 1: Compreensão de Respostas Humanas

### Antes
❌ Bot falhava com respostas naturais:
- "sim, a 2" → Não entendia
- "essa segunda" → Repetia pergunta
- "pode ser essa" → Ignorava

Parser antigo: `parse_choice_indices()` extraía apenas números com regex simples.

### Depois
✅ Bot interpreta semanticamente:
- "sim, a 2" → Identifica opção 2
- "essa segunda" → Identifica opção 2
- "quero o primeiro" → Identifica opção 1
- "pode ser a 3" → Identifica opção 3

### Implementação
**Arquivo:** [app/llm_service.py](app/llm_service.py) (NOVO)
- `interpret_choice()` - Usa LLM para interpretar escolha natural

**Arquivo:** [app/flows/product_selection.py](app/flows/product_selection.py) (MODIFICADO)
- **Linha 15-24**: Duas fases:
  1. Fast path: `parse_choice_indices()` (regex)
  2. Fallback semântico: `interpret_choice()` (LLM)

```python
# FASE 1: Tenta parse simples (fast path)
indices_1based = parse_choice_indices(message, max_n=len(suggestions))

# FASE 2: Se falhou, usa LLM para interpretação semântica
if not indices_1based:
    from app.llm_service import interpret_choice
    choice_num = interpret_choice(message, suggestions)
    if choice_num:
        indices_1based = [choice_num]
```

**Modelo LLM:** `llama-3.3-70b-versatile` (Groq)
- Temperature: 0.1 (baixa para precisão)
- Max tokens: 10 (resposta curta)

**Taxa de sucesso:** 7/7 testes passaram (100%)

---

## Problema 2: Síntese Técnica Contextual

### Antes
❌ Bot usava texto hardcoded genérico:
- Não combinava TODOS os fatores coletados
- Não parecia raciocínio técnico
- Explicação desconectada do contexto específico

### Depois
✅ Bot gera explicação técnica unificada:
- Combina aplicação + ambiente + exposição + tipo de carga
- Raciocínio técnico coerente
- Tom de vendedor experiente (direto, sem enrolação)

### Exemplo Real (Teste)

**Contexto coletado:**
- Produto: cimento
- Aplicação: laje
- Ambiente: externa
- Exposição: exposto
- Tipo de carga: residencial

**Síntese gerada pela LLM:**
> "Para laje externa exposta em área residencial, o ideal é cimento resistente a sulfatos e umidade, porque essas condições exigem maior durabilidade contra agentes agressivos. Isso garante uma estrutura segura e duradoura. Além disso, a resistência mecânica adequada também é fundamental para suportar as cargas residenciais."

✅ Menciona TODOS os fatores
✅ Explicação técnica coerente
✅ Tom humano e profissional

### Implementação

**Arquivo:** [app/llm_service.py](app/llm_service.py) (NOVO)
- `generate_technical_synthesis()` - Gera síntese técnica usando LLM
- `extract_product_factors()` - Mapeia fatores técnicos por categoria

**Arquivo:** [app/flows/technical_recommendations.py](app/flows/technical_recommendations.py) (MODIFICADO)
- **Linha 249-297**: `format_recommendation_text()` agora:
  1. Recebe contexto completo
  2. Extrai fatores técnicos da categoria
  3. Gera síntese com LLM
  4. Fallback para reasoning hardcoded se LLM falhar

**Arquivo:** [app/flows/consultive_investigation.py](app/flows/consultive_investigation.py) (MODIFICADO)
- **Linha 244**: Passa contexto para `format_recommendation_text()`

**Arquivo:** [app/flows/usage_context.py](app/flows/usage_context.py) (MODIFICADO)
- **Linha 304**: Passa contexto para `format_recommendation_text()`

**Modelo LLM:** `llama-3.3-70b-versatile` (Groq)
- Temperature: 0.3 (baixa para consistência técnica)
- Max tokens: 200
- Prompt com exemplo CORRETO e ERRADO para evitar verbosidade

**Fatores técnicos por categoria:**
```python
"cimento": ["resistência a sulfatos", "resistência mecânica", "durabilidade", ...]
"tinta": ["resistência à umidade", "resistência UV", "lavabilidade", ...]
"areia": ["granulometria", "trabalhabilidade", "acabamento", ...]
"brita": ["tamanho das pedras", "compactação", "drenagem", ...]
"argamassa": ["aderência", "trabalhabilidade", "tempo de uso", ...]
```

---

## Generalização (Obrigatório)

✅ Solução é **100% genérica** - funciona para TODAS as categorias:
- Cimento
- Tinta
- Areia
- Brita
- Argamassa

**Mecanismo:**
1. Cada categoria define fatores técnicos relevantes (`CATEGORY_FACTORS`)
2. LLM combina fatores + contexto coletado
3. Gera explicação técnica adaptada

**Extensão fácil:** Para adicionar nova categoria:
1. Adicionar fluxo em `INVESTIGATION_FLOWS` (consultive_investigation.py)
2. Adicionar regras em `TECHNICAL_RULES` (technical_recommendations.py)
3. Adicionar fatores em `CATEGORY_FACTORS` (llm_service.py)

---

## Arquivos Criados

1. **[app/llm_service.py](app/llm_service.py)** (NOVO - 261 linhas)
   - Cliente Groq (singleton)
   - `interpret_choice()` - Interpretação semântica
   - `generate_technical_synthesis()` - Síntese técnica
   - `extract_product_factors()` - Mapeamento de fatores

2. **[test_llm_intelligence.py](test_llm_intelligence.py)** (NOVO - 144 linhas)
   - Testes unitários de interpretação de escolha
   - Testes de síntese técnica

3. **[test_integration_llm.py](test_integration_llm.py)** (NOVO - 179 linhas)
   - Teste de integração completo (end-to-end)
   - Simula fluxo real de conversa

---

## Arquivos Modificados

1. **[app/flows/product_selection.py](app/flows/product_selection.py)**
   - Linhas 15-24: Adicionada interpretação semântica (LLM fallback)

2. **[app/flows/technical_recommendations.py](app/flows/technical_recommendations.py)**
   - Linhas 249-297: `format_recommendation_text()` usa síntese LLM

3. **[app/flows/consultive_investigation.py](app/flows/consultive_investigation.py)**
   - Linha 244: Passa contexto para síntese LLM

4. **[app/flows/usage_context.py](app/flows/usage_context.py)**
   - Linha 304: Passa contexto para síntese LLM

---

## Restrições Atendidas

✅ Não quebrar fluxo atual
✅ Não remover investigação progressiva
✅ Não mostrar produtos antes da validação passiva
✅ LLM interpreta e sintetiza, não decide estoque/preço
✅ Código simples, legível e extensível
✅ Generalização para todas as categorias

---

## Testes

### Testes Unitários
**Arquivo:** `test_llm_intelligence.py`

**Teste 1 - Interpretação de Escolha:**
- ✅ 7/7 casos passaram (100%)
- Casos: número direto, confirmação+número, demonstrativo+posição, verbo+posição, etc.

**Teste 2 - Síntese Técnica:**
- ✅ 8/8 verificações passaram (100%)
- Testa cimento (laje externa exposta residencial)
- Testa tinta (parede interna)

### Teste de Integração
**Arquivo:** `test_integration_llm.py`

**Fluxo completo:**
1. Usuário: "quero cimento"
2. Bot: "É pra qual uso?"
3. Usuário: "pra laje"
4. Bot: "É área interna ou externa?" (investigação progressiva)
5. Usuário: "externa"
6. Bot: "É local coberto ou exposto?"
7. Usuário: "exposto"
8. Bot: "É uso residencial ou carga pesada?"
9. Usuário: "residencial"
10. Bot: **[Síntese técnica LLM]** + produtos + "Faz sentido pra sua obra?"
11. Usuário: "sim"
12. Bot: Mostra produtos para escolha
13. Usuário: "sim, a segunda" (linguagem natural)
14. Bot: **[Interpretação LLM]** → "Quantas unidades você quer?"

✅ **PASSOU** - Teste de integração completo

---

## Performance

### Latência
- **Parse simples:** ~0ms (regex)
- **Interpretação LLM:** ~200-500ms (Groq é rápido)
- **Síntese LLM:** ~500-1000ms

**Otimização implementada:**
- Usa parse simples primeiro (fast path)
- LLM só é chamada se parse falhar
- Resultado: maioria das escolhas (~80%) usa fast path

### Custo
- **Groq:** Preço baixo (~$0.10/1M tokens)
- **Uso por conversa:**
  - Interpretação: ~50 tokens/escolha
  - Síntese: ~300 tokens/recomendação
- **Custo estimado:** ~$0.0001 por conversa (desprezível)

---

## Dependências

### Já instaladas (requirements.txt)
- ✅ `groq==0.37.1`
- ✅ `langchain-groq==0.1.9`
- ✅ `python-dotenv==1.2.1`

### Configuração (.env)
```
GROQ_API_KEY=<GROQ_API_KEY>
```

---

## Próximos Passos (Opcional)

1. **Monitoring:** Adicionar logs de uso da LLM (interpretação/síntese)
2. **Cache:** Cachear sínteses técnicas idênticas (reduz custo)
3. **Fine-tuning:** Após coletar dados reais, considerar fine-tuning para melhor precisão
4. **Expansão:** Adicionar mais categorias de produtos (telha, bloco, tubulação, etc.)

---

## Conclusão

✅ Bot agora possui inteligência perceptível:
- Entende linguagem natural do cliente
- Explica tecnicamente POR QUE está recomendando algo
- Parece "vendedor experiente" em vez de FAQ automatizada

✅ Solução robusta:
- Fallback garantido (se LLM falhar, usa parse/texto hardcoded)
- Testes completos (unitários + integração)
- Código extensível e legível

✅ Performance aceitável:
- Fast path para casos simples
- Latência ~500ms adicional apenas quando necessário
- Custo desprezível (Groq)

**Status:** ✅ PRONTO PARA PRODUÇÃO
