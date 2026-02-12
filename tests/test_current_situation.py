from app.ui.current_situation import notation_to_text


def test_notation_to_text_in_success() -> None:
    notation = "IN + H1 RB\nActual - H1 DR Premium"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "внутри" in text
    assert "бычьего H1 RB" in text
    assert "в отметках Premium актуального медвежьего торгового диапазона на H1 TF" in text


def test_notation_to_text_range_two_elements_success() -> None:
    notation = "RANGE + H1 RB - H4 FVG\nActual + H1 DR Premium | Prev - H4 DR Discount"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "в диапазоне между" in text
    assert "бычьего H1 RB" in text
    assert "медвежьего H4 FVG" in text
    assert "Premium актуального бычьего торгового диапазона на H1 TF" in text
    assert "Discount предыдущего медвежьего торгового диапазона на H4 TF" in text


def test_notation_to_text_range_one_element_success() -> None:
    notation = "RANGE + H1 RB\nPrev - H4 DR Equilibrium DOWN"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "Цена устанавливает ATL." in text
    assert "Ближайшая опорная область - бычьего H1 RB" in text
    assert "Equilibrium предыдущего медвежьего торгового диапазона на H4 TF" in text


def test_notation_to_text_wrong_first_line() -> None:
    text, error = notation_to_text("WRONG\nActual + H1 DR Premium")
    assert text is None
    assert error == "1 строка: IN +/- TF Element или RANGE +/- TF Element [+/- TF Element]"


def test_notation_to_text_wrong_second_line() -> None:
    text, error = notation_to_text("IN + H1 RB\nActual + H1 RANGE")
    assert text is None
    assert error == "2 строка: Actual/Prev +/- TF DR Premium/Equilibrium/Discount"
