from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.ui.main_window import MainWindow
else:
    from .ui.main_window import MainWindow


_APP_ID = "TheWriter.TradingPlans"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
    except Exception:
        # Keep startup resilient even if Windows API call fails.
        pass


def _load_app_icon() -> QIcon:
    icon_path = Path(__file__).resolve().parent / "ui" / "icon.ico"
    if not icon_path.exists():
        return QIcon()
    return QIcon(str(icon_path))


def main() -> int:
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("TheWriter")
    app.setOrganizationName("TheWriter")
    app.setStyle("Fusion")

    icon = _load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
