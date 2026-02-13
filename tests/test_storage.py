from pathlib import Path

from app.core.storage import list_markdown_files


def test_list_markdown_files_includes_root_and_plans_subfolders(tmp_path: Path) -> None:
    root_plan = tmp_path / "root_plan.md"
    root_plan.write_text("# Root plan\n", encoding="utf-8")

    nested_dir = tmp_path / "Plans" / "MyPlan"
    nested_dir.mkdir(parents=True)
    nested_plan = nested_dir / "MyPlan.md"
    nested_plan.write_text("# Nested plan\n", encoding="utf-8")

    infos = list_markdown_files(tmp_path)
    result_paths = {info.path for info in infos}

    assert root_plan in result_paths
    assert nested_plan in result_paths


def test_list_markdown_files_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert list_markdown_files(missing) == []
