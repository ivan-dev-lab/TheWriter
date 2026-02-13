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


def _ensure_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return path.exists() and path.is_dir()


def get_default_workspace_dir(app_name: str = APP_NAME) -> Path:
    candidates: list[Path] = []

    if os.name == "nt":
        program_w6432 = os.environ.get("ProgramW6432")
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        program_data = os.environ.get("ProgramData")

        if program_w6432:
            candidates.append(Path(program_w6432) / app_name)
        if program_files:
            pf = Path(program_files) / app_name
            if pf not in candidates:
                candidates.append(pf)
        if program_files_x86:
            pf86 = Path(program_files_x86) / app_name
            if pf86 not in candidates:
                candidates.append(pf86)
        if program_data:
            candidates.append(Path(program_data) / app_name)

    candidates.append(get_data_dir(app_name))

    for candidate in candidates:
        if _ensure_directory(candidate):
            return candidate

    fallback = get_data_dir(app_name)
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass(slots=True)
class AppSettings:
    last_directory: str = ""
    recent_files: list[str] = field(default_factory=list)
    autosave_debounce_ms: int = 1200
    autosave_periodic_ms: int = 15000
    ui_theme: str = "dark"
    sidebar_visible: bool = True
    preview_visible: bool = False
    sidebar_width: int = 290
    preview_size: int = 420
    preview_orientation: str = "vertical"
    last_open_file: str = ""

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

        if data.get("ui_theme") in ("dark", "light"):
            settings.ui_theme = str(data["ui_theme"])

        if isinstance(data.get("sidebar_visible"), bool):
            settings.sidebar_visible = bool(data["sidebar_visible"])
        if isinstance(data.get("preview_visible"), bool):
            settings.preview_visible = bool(data["preview_visible"])

        sidebar_width = data.get("sidebar_width")
        if isinstance(sidebar_width, int) and 120 <= sidebar_width <= 1200:
            settings.sidebar_width = sidebar_width

        preview_size = data.get("preview_size")
        if isinstance(preview_size, int) and 160 <= preview_size <= 1600:
            settings.preview_size = preview_size

        if data.get("preview_orientation") in ("vertical", "horizontal"):
            settings.preview_orientation = str(data["preview_orientation"])

        if isinstance(data.get("last_open_file"), str):
            settings.last_open_file = str(data["last_open_file"])

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
            "ui_theme": self.ui_theme,
            "sidebar_visible": self.sidebar_visible,
            "preview_visible": self.preview_visible,
            "sidebar_width": self.sidebar_width,
            "preview_size": self.preview_size,
            "preview_orientation": self.preview_orientation,
            "last_open_file": self.last_open_file,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def touch_recent_file(self, path: str, max_items: int = 10) -> None:
        normalized = str(path)
        if normalized in self.recent_files:
            self.recent_files.remove(normalized)
        self.recent_files.insert(0, normalized)
        self.recent_files = self.recent_files[:max_items]
