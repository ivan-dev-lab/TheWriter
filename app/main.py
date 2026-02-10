from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.ui.main_window import MainWindow
else:
    from .ui.main_window import MainWindow


def apply_light_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f7fb"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1b2430"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f2f5fb"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1b2430"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1b2430"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1b2430"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2e6fd1"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", sans-serif;
            font-size: 13px;
        }
        QMainWindow {
            background: #f5f7fb;
        }
        QToolBar {
            background: #ffffff;
            border: 1px solid #d8dde6;
            border-radius: 8px;
            padding: 6px;
            spacing: 4px;
        }
        QToolButton {
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 5px 8px;
        }
        QToolButton:hover {
            background: #f0f4fb;
            border-color: #d9e2f2;
        }
        QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget {
            background: #ffffff;
            border: 1px solid #d8dde6;
            border-radius: 8px;
            padding: 6px;
            selection-background-color: #2e6fd1;
            selection-color: #ffffff;
        }
        QPlainTextEdit, QTextBrowser {
            padding: 8px;
        }
        QPushButton {
            background: #eef3fc;
            border: 1px solid #cad6eb;
            border-radius: 7px;
            padding: 6px 10px;
        }
        QPushButton:hover {
            background: #e4ecfa;
        }
        QStatusBar {
            background: #ffffff;
            border-top: 1px solid #d8dde6;
        }
        """
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TheWriter")
    app.setOrganizationName("TheWriter")

    apply_light_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
