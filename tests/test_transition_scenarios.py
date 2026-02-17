from app.ui.transition_scenarios import (
    TransitionScenariosEditor,
    transition_action_from_notation,
    transition_meaning_notation_to_text,
    transition_notation_to_text,
)


SCENARIO_HEADER = "\u0421\u0446\u0435\u043d\u0430\u0440\u0438\u0439 \u043f\u0435\u0440\u0435\u0445\u043e\u0434\u0430 \u043a \u0441\u0434\u0435\u043b\u043a\u0435"
MEANING_HEADER = "\u0427\u0442\u043e \u044d\u0442\u043e \u0431\u0443\u0434\u0435\u0442 \u043e\u0437\u043d\u0430\u0447\u0430\u0442\u044c?"


def test_transition_notation_create_success() -> None:
    text, error = transition_notation_to_text("CREATE + H1 OB")
    assert error is None
    assert text is not None
    assert "[+H1 OB]" in text


def test_transition_notation_not_create_success() -> None:
    text, error = transition_notation_to_text("NOT CREATE - M15 FVG")
    assert error is None
    assert text is not None
    assert "[-M15 FVG]" in text


def test_transition_notation_get_success() -> None:
    notation = "GET + H1 OB ACTUAL - H4 DR Premium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[+H1 OB]" in text
    assert "[-H4 DR]" in text
    assert "Premium" in text


def test_transition_notation_not_get_with_underscore_success() -> None:
    notation = "NOT_GET - M30 FVG PREV + D1 DR Equilibrium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[-M30 FVG]" in text
    assert "[+D1 DR]" in text
    assert "Equilibrium" in text


def test_transition_notation_invalid_format() -> None:
    text, error = transition_notation_to_text("SOMETHING + H1 OB")
    assert text is None
    assert error is not None


def test_transition_notation_create_with_range_success() -> None:
    notation = "CREATE + H1 OB ACTUAL - H4 DR Premium"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[+H1 OB]" in text
    assert "[-H4 DR]" in text
    assert "Premium" in text


def test_transition_notation_not_create_with_clause_success() -> None:
    notation = "NOT CREATE + M5 FVG WITH - H1 OB PREV + D1 DR Discount"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[+M5 FVG]" in text
    assert "[-H1 OB]" in text
    assert "[+D1 DR]" in text
    assert "Discount" in text


def test_transition_notation_create_with_clause_break_success() -> None:
    notation = "CREATE + M5 FVG WITH - H1 OB PREV + D1 DR Discount BREAK"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[-H1 OB]" in text
    assert "[+D1 DR]" in text


def test_transition_notation_create_with_clause_not_break_success() -> None:
    notation = "CREATE + M5 FVG WITH - H1 OB PREV + D1 DR Discount NOT BREAK"
    text, error = transition_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[-H1 OB]" in text


def test_transition_notation_create_with_clause_requires_break_mode() -> None:
    notation = "CREATE + M5 FVG WITH - H1 OB PREV + D1 DR Discount"
    text, error = transition_notation_to_text(notation)
    assert text is None
    assert error is not None
    assert "BREAK" in error


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
    assert "[+H1 OB]" in text


def test_transition_meaning_notation_dr_success() -> None:
    notation = "NOT ADV SELL LOW PREV - M15 DR Discount"
    text, error = transition_meaning_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[-M15 DR]" in text
    assert "Discount" in text


def test_transition_meaning_notation_down_alias_success() -> None:
    notation = "ADV SELL DOWN PREV - M15 DR Discount"
    text, error = transition_meaning_notation_to_text(notation)
    assert error is None
    assert text is not None
    assert "[-M15 DR]" in text


def test_transition_meaning_notation_invalid() -> None:
    text, error = transition_meaning_notation_to_text("ADV BUY UP DR Premium")
    assert text is None
    assert error is not None


def test_parse_transition_scenarios_with_new_comments() -> None:
    markdown = """#### Scenario 1
![scenario_1](img.png)
**TF:** H1

<!-- TRANSITION_NOTATION
CREATE + H1 OB
-->

<!-- TRANSITION_SCENARIO_TEXT
For transition to a trade, price should create [+H1 OB].
-->

<!-- TRANSITION_MEANING_NOTATION
ADV BUY UP + H1 OB
-->

<!-- TRANSITION_MEANING_TEXT
Interpretation placeholder text.
-->

<!-- TRANSITION_WHY
Because liquidity remains above the prior high.
-->
"""
    entries = TransitionScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert len(entry.images) == 1
    assert entry.images[0].image_path == "img.png"
    assert entry.images[0].timeframe == "H1"
    assert entry.notation == "CREATE + H1 OB"
    assert entry.scenario_text == "For transition to a trade, price should create [+H1 OB]."
    assert entry.meaning_notation == "ADV BUY UP + H1 OB"
    assert entry.meaning_text == "Interpretation placeholder text."
    assert entry.why_text == "Because liquidity remains above the prior high."


def test_parse_transition_scenarios_multiple_images_in_one_scenario() -> None:
    markdown = """#### Scenario 1
![scenario_1](img_1.png)
**TF:** H1

![scenario_2](img_2.png)
**TF:** M15

<!-- TRANSITION_NOTATION
CREATE + H1 OB WITH - M5 FVG ACTUAL + D1 DR Premium BREAK
-->
"""
    entries = TransitionScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert len(entry.images) == 2
    assert entry.images[0].image_path == "img_1.png"
    assert entry.images[0].timeframe == "H1"
    assert entry.images[1].image_path == "img_2.png"
    assert entry.images[1].timeframe == "M15"


def test_parse_transition_scenarios_fallback_from_visible_blocks() -> None:
    markdown = f"""#### Scenario 1
![scenario_1](img.png)
**TF:** H1

<!-- TRANSITION_NOTATION
CREATE + H1 OB
-->

**{SCENARIO_HEADER}:**
Visible scenario fallback with [+H1 OB].

**{MEANING_HEADER}:** Visible meaning fallback text.
"""
    entries = TransitionScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.scenario_text.startswith("Visible scenario fallback")
    assert entry.meaning_text == "Visible meaning fallback text."
