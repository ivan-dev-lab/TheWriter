from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.ui.main_window import MainWindow
else:
    from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TheWriter")
    app.setOrganizationName("TheWriter")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
