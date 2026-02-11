from app.ui.deal_scenarios import DealScenariosEditor


def test_parse_deal_scenarios_markdown() -> None:
    markdown = """#### Сделка 1
![deal_1](img1.png)
**Сценарий перехода:** GET + H1 OB ACTUAL - H4 DR Premium

**Идея сделки**
Идея

**Entry: почему именно так? Можно ли выгоднее? Обосновать**
Entry rationale

**SL: Почему именно так? Что он отменяет? Обосновать**
SL rationale

**TP: Почему именно так? Это оптимальная цель? Обосновать**
TP rationale
"""

    entries = DealScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.image_path == "img1.png"
    assert entry.transition_ref == "GET + H1 OB ACTUAL - H4 DR Premium"
    assert entry.idea == "Идея"
    assert entry.entry == "Entry rationale"
    assert entry.sl == "SL rationale"
    assert entry.tp == "TP rationale"


def test_parse_deal_scenarios_without_sections() -> None:
    markdown = "![deal](img.png)\nТекст без заголовков"
    entries = DealScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.image_path == "img.png"
    assert entry.transition_ref == ""
    assert entry.idea == "Текст без заголовков"
    assert entry.entry == ""
    assert entry.sl == ""
    assert entry.tp == ""


def test_parse_deal_scenarios_without_image_keeps_text() -> None:
    markdown = "Старый формат блока 3 без картинки"
    entries = DealScenariosEditor._parse_entries(markdown)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.image_path == ""
    assert entry.idea == "Старый формат блока 3 без картинки"
