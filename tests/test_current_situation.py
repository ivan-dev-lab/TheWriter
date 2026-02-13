from app.ui.current_situation import notation_to_text


def test_notation_to_text_in_success() -> None:
    notation = "IN + H1 RB\nActual - H1 DR Premium"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[+H1 RB]" in text
    assert "Premium" in text
    assert "[-H1 DR]" in text


def test_notation_to_text_range_two_elements_success() -> None:
    notation = "RANGE + H1 RB - H4 FVG\nActual + H1 DR Premium | Prev - H4 DR Discount"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[+H1 RB]" in text
    assert "[-H4 FVG]" in text
    assert "Premium" in text
    assert "Discount" in text
    assert "[+H1 DR]" in text
    assert "[-H4 DR]" in text


def test_notation_to_text_range_one_element_success() -> None:
    notation = "RANGE + H1 RB DOWN\nPrev - H4 DR Equilibrium"
    text, error = notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "ATL" in text
    assert "[+H1 RB]" in text
    assert "Equilibrium" in text
    assert "[-H4 DR]" in text


def test_notation_to_text_wrong_first_line() -> None:
    text, error = notation_to_text("WRONG\nActual + H1 DR Premium")
    assert text is None
    assert error is not None
    assert "IN +/- TF Element" in error
    assert "RANGE +/- TF Element" in error


def test_notation_to_text_wrong_second_line() -> None:
    text, error = notation_to_text("IN + H1 RB\nActual + H1 RANGE")
    assert text is None
    assert error is not None
    assert "Actual/Prev +/- TF DR Premium/Equilibrium/Discount" in error
