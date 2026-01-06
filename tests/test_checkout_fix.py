from app.checkout_handlers.extractors import extract_name, extract_phone


def test_extract_name_simple():
    assert extract_name("Rougger") == "Rougger"


def test_extract_name_full():
    assert extract_name("Joao Silva") == "Joao Silva"


def test_extract_name_with_pattern():
    assert extract_name("meu nome e Maria") == "Maria"


def test_extract_name_returns_none_for_empty():
    assert extract_name("") is None


def test_extract_phone_digits_only():
    assert extract_phone("11987654321") == "11987654321"


def test_extract_phone_formatted():
    assert extract_phone("(11) 98765-4321") == "11987654321"


def test_extract_phone_with_country_code():
    assert extract_phone("5511987654321") == "5511987654321"


def test_extract_phone_returns_none_for_short():
    assert extract_phone("12345") is None
