from app.ui.transition_scenarios import transition_notation_to_text


def test_transition_notation_create_success() -> None:
    text, error = transition_notation_to_text("CREATE + H1 OB")
    assert error is None
    assert text is not None
    assert "сформировать" in text
    assert "бычий H1 OB" in text


def test_transition_notation_not_create_success() -> None:
    text, error = transition_notation_to_text("NOT CREATE - M15 FVG")
    assert error is None
    assert text is not None
    assert "не сформировать" in text
    assert "медвежий M15 FVG" in text


def test_transition_notation_get_success() -> None:
    notation = "GET + H1 OB ACTUAL - H4 DR Premium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "получить реакцию" in text
    assert "бычьего H1 OB" in text
    assert "актуальном медвежьем торговом диапазоне на H4" in text
    assert "Premium" in text


def test_transition_notation_not_get_with_underscore_success() -> None:
    notation = "NOT_GET - M30 FVG PREV + D1 DR Equilibrium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "не получить реакцию" in text
    assert "предыдущем бычьем торговом диапазоне на D1" in text
    assert "Equilibrium" in text


def test_transition_notation_invalid_format() -> None:
    text, error = transition_notation_to_text("SOMETHING + H1 OB")
    assert text is None
    assert error is not None
    assert "Формат нотации" in error


def test_transition_notation_create_rejects_get_tail() -> None:
    notation = "CREATE + H1 OB ACTUAL - H4 DR Premium"
    text, error = transition_notation_to_text(notation)
    assert text is None
    assert error is not None
    assert "для create/not create" in error.casefold()
