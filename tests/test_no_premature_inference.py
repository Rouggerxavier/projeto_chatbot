"""
Testes para validar que NÃO há inferência prematura de contexto técnico.

REGRA ABSOLUTA: Nenhuma recomendação técnica pode ser gerada enquanto
o usuário não tiver explicitamente informado o uso.

TESTES OBRIGATÓRIOS:
1. "quero comprar 200kg de cimento" → pergunta de uso, NÃO recomendação
2. "cimento" → pergunta de investigação, NÃO síntese técnica
3. Fluxo completo: cimento → laje → externa → exposta → residencial → SÓ NO FINAL recomendação
"""
import pytest


class TestCanGenerateTechnicalAnswer:
    """Testes para o gate central can_generate_technical_answer()."""

    def test_blocks_empty_context(self):
        """Contexto vazio deve ser BLOQUEADO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Contexto completamente vazio
        assert can_generate_technical_answer("cimento", {}) is False
        assert can_generate_technical_answer("cimento", None) is False

    def test_blocks_missing_application(self):
        """Contexto sem application deve ser BLOQUEADO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Sem application
        context = {"environment": "externa", "exposure": "exposto"}
        assert can_generate_technical_answer("cimento", context) is False

    def test_blocks_unknown_application(self):
        """Application com valor 'unknown' deve ser BLOQUEADO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        invalid_values = ["unknown", "desconhecido", "nao informado", "", None, "default", "generico"]

        for invalid in invalid_values:
            context = {"application": invalid}
            result = can_generate_technical_answer("cimento", context)
            assert result is False, f"Deveria bloquear application='{invalid}'"

    def test_blocks_cimento_without_environment(self):
        """Cimento com application 'laje' mas sem environment deve ser BLOQUEADO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Laje exige ambiente (interna/externa)
        context = {"application": "laje"}
        assert can_generate_technical_answer("cimento", context) is False

        context = {"application": "contrapiso"}
        assert can_generate_technical_answer("cimento", context) is False

    def test_allows_cimento_reboco_without_environment(self):
        """Cimento com application 'reboco' NÃO exige ambiente."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Reboco, fundação, piso só precisam de application
        assert can_generate_technical_answer("cimento", {"application": "reboco"}) is True
        assert can_generate_technical_answer("cimento", {"application": "fundacao"}) is True
        assert can_generate_technical_answer("cimento", {"application": "piso"}) is True

    def test_allows_cimento_laje_with_environment(self):
        """Cimento com application 'laje' + environment deve ser PERMITIDO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        context = {"application": "laje", "environment": "externa"}
        assert can_generate_technical_answer("cimento", context) is True

        context = {"application": "laje", "environment": "interna"}
        assert can_generate_technical_answer("cimento", context) is True

    def test_blocks_tinta_without_surface_or_environment(self):
        """Tinta exige superfície E ambiente."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Só superfície
        assert can_generate_technical_answer("tinta", {"application": "pintura", "surface": "parede"}) is False

        # Só ambiente (sem surface explícito)
        assert can_generate_technical_answer("tinta", {"application": "pintura", "environment": "interna"}) is False

    def test_allows_tinta_with_surface_and_environment(self):
        """Tinta com superfície + ambiente deve ser PERMITIDO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        context = {"application": "pintura", "surface": "parede", "environment": "externa"}
        assert can_generate_technical_answer("tinta", context) is True


class TestIsValidContextValue:
    """Testes para validação de valores de contexto."""

    def test_rejects_invalid_values(self):
        """Valores inválidos devem ser rejeitados."""
        from app.flows.technical_recommendations import _is_valid_context_value

        invalid_values = [
            None,
            "",
            "unknown",
            "desconhecido",
            "nao informado",
            "none",
            "null",
            "default",
            "padrao",
            "generico",
            "geral",
            "qualquer",
        ]

        for val in invalid_values:
            assert _is_valid_context_value(val) is False, f"Deveria rejeitar '{val}'"

    def test_accepts_valid_values(self):
        """Valores válidos devem ser aceitos."""
        from app.flows.technical_recommendations import _is_valid_context_value

        valid_values = ["laje", "reboco", "externa", "interna", "exposto", "residencial"]

        for val in valid_values:
            assert _is_valid_context_value(val) is True, f"Deveria aceitar '{val}'"


class TestResetConsultiveContext:
    """Testes para reset_consultive_context()."""

    def test_resets_all_consultive_fields(self):
        """Deve resetar TODOS os campos consultivos."""
        from app.session_state import patch_state, get_state, reset_consultive_context

        session_id = "test_reset_consultive_001"

        # Simula contexto anterior
        patch_state(session_id, {
            "consultive_investigation": True,
            "consultive_application": "laje",
            "consultive_environment": "externa",
            "consultive_exposure": "exposto",
            "consultive_load_type": "residencial",
            "consultive_product_hint": "cimento",
            "consultive_investigation_step": 3,
            "consultive_recommendation_shown": True,
        })

        # Verifica que foi salvo
        st = get_state(session_id)
        assert st["consultive_investigation"] is True
        assert st["consultive_application"] == "laje"

        # Reseta
        reset_consultive_context(session_id)

        # Verifica que foi limpo
        st = get_state(session_id)
        assert st["consultive_investigation"] is False
        assert st["consultive_application"] is None
        assert st["consultive_environment"] is None
        assert st["consultive_exposure"] is None
        assert st["consultive_load_type"] is None
        assert st["consultive_product_hint"] is None
        assert st["consultive_investigation_step"] == 0
        assert st["consultive_recommendation_shown"] is False

    def test_preserves_client_data(self):
        """Reset consultivo NÃO deve apagar dados do cliente."""
        from app.session_state import patch_state, get_state, reset_consultive_context

        session_id = "test_reset_preserve_001"

        # Simula dados do cliente + contexto consultivo
        patch_state(session_id, {
            "cliente_nome": "João",
            "cliente_email": "joao@teste.com",
            "consultive_investigation": True,
            "consultive_application": "laje",
        })

        # Reseta consultivo
        reset_consultive_context(session_id)

        # Cliente deve estar preservado
        st = get_state(session_id)
        assert st["cliente_nome"] == "João"
        assert st["cliente_email"] == "joao@teste.com"

        # Consultivo deve estar limpo
        assert st["consultive_investigation"] is False
        assert st["consultive_application"] is None


class TestIsGenericProduct:
    """Testes para detecção de produtos genéricos."""

    def test_detects_generic_cimento(self):
        """'cimento' sozinho é genérico."""
        from app.flows.usage_context import is_generic_product

        assert is_generic_product("cimento") is True
        assert is_generic_product("quero cimento") is True
        assert is_generic_product("200kg de cimento") is True

    def test_detects_specific_cimento(self):
        """'cimento cp ii' é específico, NÃO genérico."""
        from app.flows.usage_context import is_generic_product

        assert is_generic_product("cimento cp ii") is False
        assert is_generic_product("cimento cp iii") is False
        assert is_generic_product("cimento cp iv") is False


class TestAskUsageContext:
    """Testes para ask_usage_context()."""

    def test_asks_usage_question(self):
        """Deve retornar pergunta de uso."""
        from app.flows.usage_context import ask_usage_context

        session_id = "test_ask_usage_001"
        reply = ask_usage_context(session_id, "cimento")

        # Deve conter pergunta de uso
        assert "uso" in reply.lower() or "qual" in reply.lower()
        assert "laje" in reply.lower() or "reboco" in reply.lower()

    def test_sets_awaiting_state(self):
        """Deve setar estado awaiting_usage_context."""
        from app.flows.usage_context import ask_usage_context
        from app.session_state import get_state

        session_id = "test_ask_usage_002"
        ask_usage_context(session_id, "cimento")

        st = get_state(session_id)
        assert st["awaiting_usage_context"] is True
        assert st["usage_context_product_hint"] == "cimento"

    def test_canonicalizes_generic_hint(self):
        """Hint genérico deve ser canonicalizado no estado."""
        from app.flows.usage_context import ask_usage_context
        from app.session_state import get_state

        session_id = "test_ask_usage_003"
        ask_usage_context(session_id, "to precisando de cimento para uma obra")

        st = get_state(session_id)
        assert st["usage_context_product_hint"] == "cimento"


class TestUsageContextParsing:
    """Testes para extração de contexto em mensagens mistas."""

    def test_extracts_known_context_from_mixed_message(self):
        from app.flows.usage_context import extract_known_usage_context

        msg = "eu falei que era para reboco o cimento"
        assert extract_known_usage_context(msg) == "reboco"


class TestFlowIntegration:
    """Testes de integração do fluxo completo."""

    def test_generic_product_asks_usage_first(self):
        """Produto genérico SEMPRE pergunta uso primeiro."""
        from app.flows.usage_context import is_generic_product, ask_usage_context
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Simula: "quero comprar 200kg de cimento"
        hint = "cimento"

        # 1. Detecta como genérico
        assert is_generic_product(hint) is True

        # 2. Não pode gerar resposta técnica ainda (contexto vazio)
        assert can_generate_technical_answer(hint, {}) is False
        assert can_generate_technical_answer(hint, {"application": None}) is False

        # 3. Deve perguntar uso
        session_id = "test_flow_001"
        reply = ask_usage_context(session_id, hint)
        assert "uso" in reply.lower() or "qual" in reply.lower()

    def test_complete_flow_only_allows_recommendation_at_end(self):
        """Fluxo completo: recomendação SÓ após coletar TUDO."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Passo 0: Só produto - BLOQUEADO
        context = {"product": "cimento"}
        assert can_generate_technical_answer("cimento", context) is False

        # Passo 1: Adiciona application - ainda BLOQUEADO (laje precisa ambiente)
        context["application"] = "laje"
        assert can_generate_technical_answer("cimento", context) is False

        # Passo 2: Adiciona environment - PERMITIDO
        context["environment"] = "externa"
        assert can_generate_technical_answer("cimento", context) is True

        # Contexto completo com todos os detalhes
        context["exposure"] = "exposto"
        context["load_type"] = "residencial"
        assert can_generate_technical_answer("cimento", context) is True


class TestNoInferenceFromQuantity:
    """
    TESTE CRÍTICO: Quantidade NÃO implica contexto técnico.

    "quero comprar 200kg de cimento" NÃO pode gerar recomendação.
    """

    def test_quantity_does_not_enable_recommendation(self):
        """Quantidade informada NÃO habilita recomendação técnica."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Usuário disse quantidade, mas NÃO disse uso
        context = {
            "quantity": "200kg",
            "product": "cimento",
            # application está VAZIO - usuário não informou
        }

        # DEVE ser bloqueado
        assert can_generate_technical_answer("cimento", context) is False

    def test_product_intent_does_not_enable_recommendation(self):
        """Intenção de compra NÃO habilita recomendação técnica."""
        from app.flows.technical_recommendations import can_generate_technical_answer

        # Usuário disse "quero comprar", mas NÃO disse uso
        context = {
            "intent": "comprar",
            "product": "cimento",
            # application está VAZIO
        }

        # DEVE ser bloqueado
        assert can_generate_technical_answer("cimento", context) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
