"""
Logging silencioso de decisões de inteligência (observabilidade).

Registra decisões internas sem impactar respostas ao usuário.
Logs estruturados para análise de comportamento em produção.
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime


# Configuração de logger dedicado
_intelligence_logger = None


def _get_logger():
    """Retorna logger dedicado para inteligência."""
    global _intelligence_logger
    if _intelligence_logger is None:
        _intelligence_logger = logging.getLogger("intelligence")
        _intelligence_logger.setLevel(logging.INFO)

        # Handler: arquivo dedicado
        handler = logging.FileHandler("intelligence.log", encoding="utf-8")
        handler.setLevel(logging.INFO)

        # Formato JSON estruturado
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)

        _intelligence_logger.addHandler(handler)

    return _intelligence_logger


def log_choice_interpretation(
    session_id: str,
    user_message: str,
    method: str,  # "fast_path" | "llm_semantic"
    choice_num: Optional[int],
    confidence: Optional[str] = None,  # "high" | "medium" | "low"
    ambiguous: bool = False
):
    """
    Registra decisão de interpretação de escolha.

    Args:
        session_id: ID da sessão
        user_message: Mensagem do usuário
        method: Método usado (fast_path ou llm_semantic)
        choice_num: Número da escolha identificada (ou None)
        confidence: Nível de confiança (opcional)
        ambiguous: Se havia ambiguidade
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "stage": "choice_interpretation",
        "decision_type": method,
        "user_message": user_message,
        "choice_num": choice_num,
        "confidence": confidence,
        "ambiguous": ambiguous,
        "success": choice_num is not None
    }

    logger = _get_logger()
    logger.info(json.dumps(log_entry, ensure_ascii=False))


def log_technical_synthesis(
    session_id: str,
    product_category: str,
    context: Dict[str, Any],
    method: str,  # "llm_generated" | "hardcoded_fallback"
    synthesis_length: int
):
    """
    Registra geração de síntese técnica.

    Args:
        session_id: ID da sessão
        product_category: Categoria do produto
        context: Contexto coletado
        method: Método usado
        synthesis_length: Tamanho da síntese gerada (caracteres)
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "stage": "technical_synthesis",
        "decision_type": method,
        "product_category": product_category,
        "context": context,
        "synthesis_length": synthesis_length,
    }

    logger = _get_logger()
    logger.info(json.dumps(log_entry, ensure_ascii=False))


def log_investigation_summary(
    session_id: str,
    questions_asked: int,
    context_collected: Dict[str, Any],
    triggered_limit: bool
):
    """
    Registra conclusão de investigação progressiva.

    Args:
        session_id: ID da sessão
        questions_asked: Número de perguntas feitas
        context_collected: Contexto coletado
        triggered_limit: Se atingiu limite de perguntas
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "stage": "investigation_complete",
        "questions_asked": questions_asked,
        "context_collected": context_collected,
        "triggered_limit": triggered_limit,
    }

    logger = _get_logger()
    logger.info(json.dumps(log_entry, ensure_ascii=False))


def log_passive_validation(
    session_id: str,
    validation_type: str,  # "interest_confirmed" | "interest_declined" | "clarification_needed"
    user_response: str
):
    """
    Registra resposta de validação passiva.

    Args:
        session_id: ID da sessão
        validation_type: Tipo de validação
        user_response: Resposta do usuário
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "stage": "passive_validation",
        "decision_type": validation_type,
        "user_response": user_response,
    }

    logger = _get_logger()
    logger.info(json.dumps(log_entry, ensure_ascii=False))
