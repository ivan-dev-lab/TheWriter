from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from ..settings import get_data_dir


@dataclass(slots=True)
class PlanFileInfo:
    path: Path
    modified_at: datetime


def list_markdown_files(directory: Path) -> list[PlanFileInfo]:
    if not directory.exists() or not directory.is_dir():
        return []

    entries: list[PlanFileInfo] = []
    for file_path in directory.glob("*.md"):
        if not file_path.is_file():
            continue
        try:
            stat = file_path.stat()
        except OSError:
            continue
        entries.append(PlanFileInfo(path=file_path, modified_at=datetime.fromtimestamp(stat.st_mtime)))

    entries.sort(key=lambda item: (-item.modified_at.timestamp(), item.path.name.casefold()))
    return entries


def read_markdown(path: Path) -> str:
    encodings = ("utf-8", "utf-8-sig", "cp1251")
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    temp_path = path.parent / temp_name

    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def save_markdown(path: Path, markdown: str) -> None:
    atomic_write_text(path=path, text=markdown)


def build_draft_path(preferred_directory: Path | None) -> Path:
    base_dir = preferred_directory if preferred_directory else get_data_dir() / "drafts"
    base_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base_dir / f"_draft_{stamp}.md"
    counter = 1

    while candidate.exists():
        counter += 1
        candidate = base_dir / f"_draft_{stamp}_{counter}.md"

    return candidate


def save_draft(markdown: str, preferred_directory: Path | None) -> Path:
    draft_path = build_draft_path(preferred_directory=preferred_directory)
    save_markdown(path=draft_path, markdown=markdown)
    return draft_path
