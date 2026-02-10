from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys

APP_NAME = "TheWriter"
SETTINGS_FILENAME = "settings.json"


def get_config_dir(app_name: str = APP_NAME) -> Path:
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return base / app_name
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / app_name
    base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return base / app_name.lower()


def get_data_dir(app_name: str = APP_NAME) -> Path:
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return base / app_name
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / app_name
    base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return base / app_name.lower()


@dataclass(slots=True)
class AppSettings:
    last_directory: str = ""
    recent_files: list[str] = field(default_factory=list)
    autosave_debounce_ms: int = 1200
    autosave_periodic_ms: int = 15000

    @classmethod
    def load(cls) -> "AppSettings":
        path = get_config_dir() / SETTINGS_FILENAME
        if not path.exists():
            return cls()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()

        settings = cls()
        if isinstance(data.get("last_directory"), str):
            settings.last_directory = data["last_directory"]

        recent_files = data.get("recent_files")
        if isinstance(recent_files, list):
            settings.recent_files = [str(item) for item in recent_files if isinstance(item, str)]

        debounce = data.get("autosave_debounce_ms")
        periodic = data.get("autosave_periodic_ms")

        if isinstance(debounce, int) and debounce >= 100:
            settings.autosave_debounce_ms = debounce
        if isinstance(periodic, int) and periodic >= 1000:
            settings.autosave_periodic_ms = periodic

        return settings

    def save(self) -> None:
        target_dir = get_config_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / SETTINGS_FILENAME

        payload = {
            "last_directory": self.last_directory,
            "recent_files": self.recent_files[:20],
            "autosave_debounce_ms": self.autosave_debounce_ms,
            "autosave_periodic_ms": self.autosave_periodic_ms,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def touch_recent_file(self, path: str, max_items: int = 10) -> None:
        normalized = str(path)
        if normalized in self.recent_files:
            self.recent_files.remove(normalized)
        self.recent_files.insert(0, normalized)
        self.recent_files = self.recent_files[:max_items]
