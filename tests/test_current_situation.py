from app.ui.current_situation import notation_to_text


def test_notation_to_text_success() -> None:
    notation = "IN + H1 OB\nActual - H1 DR"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "внутри" in text
    assert "бычьего H1 OB" in text
    assert "актуального медвежьего торгового диапазона на H1" in text


def test_notation_to_text_wrong_first_line() -> None:
    text, error = notation_to_text("WRONG\nActual + H1 DR")
    assert text is None
    assert error == "1 строка: IN/OUT [+/- TF Element]"


def test_notation_to_text_wrong_second_line() -> None:
    text, error = notation_to_text("OUT - H4 FVG\nActual + H4 RANGE")
    assert text is None
    assert error == "2 строка: Actual/Prev [+/- TF DR]"

