from app.core.plans import SECTION_DEFINITIONS, TradingPlan, apply_title_to_markdown


def test_structured_parse_and_extras_preserved() -> None:
    markdown = """
# План A

Вступительный комментарий.

## 1. Описание текущей ситуации
Блок 1

## Дополнительный раздел
Нужно сохранить.

## 2. Описание сценариев перехода к сделкам
Блок 2

## 3. Описание сценариев сделок
Блок 3
""".strip()

    plan = TradingPlan.from_markdown(markdown, fallback_title="Fallback")
    assert plan.structured is True
    assert plan.title == "План A"
    assert plan.block1 == "Блок 1"
    assert plan.block2 == "Блок 2"
    assert plan.block3 == "Блок 3"
    assert "## Дополнительный раздел" in plan.extras

    rebuilt = plan.to_markdown()
    for heading, _ in SECTION_DEFINITIONS:
        assert f"## {heading}" in rebuilt
    assert "## Дополнительный раздел" in rebuilt


def test_invalid_template_falls_back_to_raw_mode() -> None:
    markdown = """
# Кривой план

## Совсем другой заголовок
Текст
""".strip()

    plan = TradingPlan.from_markdown(markdown, fallback_title="Fallback")
    assert plan.structured is False
    assert "Совсем другой заголовок" in plan.raw_markdown


def test_apply_title_to_markdown_prepends_title_if_missing() -> None:
    result = apply_title_to_markdown("Просто текст", "Новый заголовок")
    assert result.startswith("# Новый заголовок")
    assert "Просто текст" in result


def test_normalize_raw_creates_structured_plan() -> None:
    normalized = TradingPlan.normalize_raw("Старый произвольный текст", "Нормализация")
    assert normalized.structured is True
    assert normalized.title == "Нормализация"
    assert normalized.block1 == "Старый произвольный текст"
    assert normalized.block2 == ""
    assert normalized.block3 == ""

