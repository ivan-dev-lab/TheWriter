from app.ui.transition_scenarios import (
    TransitionScenariosEditor,
    transition_action_from_notation,
    transition_meaning_notation_to_text,
    transition_notation_to_text,
)


def test_transition_notation_create_success() -> None:
    text, error = transition_notation_to_text("CREATE + H1 OB")
    assert error is None
    assert text is not None
    assert "H1 OB" in text


def test_transition_notation_not_create_success() -> None:
    text, error = transition_notation_to_text("NOT CREATE - M15 FVG")
    assert error is None
    assert text is not None
    assert "M15 FVG" in text


def test_transition_notation_get_success() -> None:
    notation = "GET + H1 OB ACTUAL - H4 DR Premium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "H1 OB" in text
    assert "H4" in text
    assert "Premium" in text


def test_transition_notation_not_get_with_underscore_success() -> None:
    notation = "NOT_GET - M30 FVG PREV + D1 DR Equilibrium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "M30 FVG" in text
    assert "D1" in text
    assert "Equilibrium" in text


def test_transition_notation_invalid_format() -> None:
    text, error = transition_notation_to_text("SOMETHING + H1 OB")
    assert text is None
    assert error is not None
    assert "CREATE/NOT CREATE" in error


def test_transition_notation_create_rejects_get_tail() -> None:
    notation = "CREATE + H1 OB ACTUAL - H4 DR Premium"
    text, error = transition_notation_to_text(notation)
    assert text is None
    assert error is not None
    assert "create/not create" in error.casefold()


def test_transition_action_from_notation_detects_action_early() -> None:
    assert transition_action_from_notation("CREATE") == "CREATE"
    assert transition_action_from_notation("NOT CREATE + H1 OB") == "NOT CREATE"
    assert transition_action_from_notation("GET") == "GET"
    assert transition_action_from_notation("NOT GET + H1 OB") == "NOT GET"
    assert transition_action_from_notation("OTHER") is None


def test_transition_meaning_notation_element_success() -> None:
    notation = "ADV BUY UP + H1 OB"
    text, error = transition_meaning_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "H1 OB" in text
    assert "OB" in text


def test_transition_meaning_notation_dr_success() -> None:
    notation = "NOT ADV SELL LOW PREV - M15 DR Discount"
    text, error = transition_meaning_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "M15" in text
    assert "Discount" in text


def test_transition_meaning_notation_invalid() -> None:
    text, error = transition_meaning_notation_to_text("ADV BUY UP DR Premium")
    assert text is None
    assert error is not None
    assert "ADV/NOT ADV" in error


def test_parse_transition_scenarios_with_new_comments() -> None:
    markdown = """#### Сценарий 1
![scenario_1](img.png)

<!-- TRANSITION_NOTATION
CREATE + H1 OB
-->

<!-- TRANSITION_MEANING_NOTATION
ADV BUY UP + H1 OB
-->

<!-- TRANSITION_WHY
Because liquidity remains above the prior high.
-->
"""
    entries = TransitionScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.image_path == "img.png"
    assert entry.notation == "CREATE + H1 OB"
    assert entry.meaning_notation == "ADV BUY UP + H1 OB"
    assert entry.why_text == "Because liquidity remains above the prior high."
