import re

HORARIO_LOJA = "Nosso horário é de segunda a sexta, 7h às 18h; sábado, 7h às 12h."
BAIRROS_ENTREGA = ["manaíra", "intermares", "aeroclube", "tambaú", "bessa"]
CEP_REGEX = re.compile(r"\b\d{5}-\d{3}\b")

FORBIDDEN_REPLY_PATTERNS = [
    r"código de rastreamento",
    r"rastreamento",
    r"você receberá um e-?mail",
    r"enviaremos um e-?mail",
    r"código de barras do seu pedido",
    r"código de referência",
    r"pedido foi enviado",
    r"pedido enviado",
    r"rastreio",
    r"tracking",    r"produto com o id",
    r"id \d+",
    r"por favor, aguarde",
]
FORBIDDEN_REPLY_REGEX = re.compile("|".join(FORBIDDEN_REPLY_PATTERNS), flags=re.IGNORECASE)

STOPWORDS = {
    "para", "pro", "pra", "com", "sem", "e", "ou",
    "da", "do", "de", "a", "o", "os", "as", "um", "uma",
    "no", "na", "nos", "nas", "por", "favor", "pf", "isso",
    "quero", "queria", "preciso", "gostaria", "me", "manda",
    "sim", "ok", "beleza", "certo", "confirmo", "confirmar",
    "tambem", "também", "tb"
}


GREETINGS = {"bom dia", "boa tarde", "boa noite", "oi", "olá", "ola", "e ai", "eai", "fala", "tudo bem"}
INTENT_KEYWORDS = [
    "quero", "queria", "preciso", "gostaria", "tem", "vende", "vcs tem", "vocês tem",
    "quanto custa", "preço", "valor", "orçamento", "orcamento", "comprar", "pedido",
    "adiciona", "coloca", "colocar", "pegar", "me da", "me dá", "vou levar",
]

CART_SHOW_KEYWORDS = [
    "meu orçamento", "meu orcamento", "ver orçamento", "ver orcamento",
    "resumo", "carrinho", "itens", "meu pedido",
    "ja fez o orçamento", "já fez o orçamento", "ja fez o orcamento", "já fez o orcamento",
    "mostra o orçamento", "mostrar o orçamento", "qual o total", "quanto deu", "quanto ficou"
]
CART_RESET_KEYWORDS = [
    "limpar orçamento", "limpar orcamento", "zerar orçamento", "zerar orcamento",
    "retirar tudo", "tirar tudo", "esvaziar carrinho", "começar do zero", "comecar do zero"
]
