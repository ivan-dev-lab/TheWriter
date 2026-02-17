from pathlib import Path

from app.ui.scenario_template_dialog import load_scenario_templates


def test_load_scenario_templates_contains_breakout() -> None:
    templates = load_scenario_templates(Path("app/ui/templates"))
    assert templates
    template = templates[0]
    assert template.template_id == "breakout_inefficiency"
    assert template.name
    assert template.image_path.name == "template_breakout.jpg"
