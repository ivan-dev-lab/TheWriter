from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path
import re

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QStackedWidget,
)

from ..core.autosave import AutoSaveController
from ..core.plans import TradingPlan, apply_title_to_markdown
from ..core.storage import PlanFileInfo, build_draft_path, list_markdown_files, read_markdown, save_markdown
from ..settings import AppSettings

try:
    import markdown as markdown_renderer
except ImportError:
    markdown_renderer = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.settings = AppSettings.load()
        self.current_directory: Path | None = None
        if self.settings.last_directory:
            candidate = Path(self.settings.last_directory)
            if candidate.exists() and candidate.is_dir():
                self.current_directory = candidate

        self.current_file: Path | None = None
        self.current_draft_path: Path | None = None
        self.current_plan = TradingPlan.empty()
        self.file_cache: list[PlanFileInfo] = []
        self._updating = False

        self.setWindowTitle("TheWriter - Торговые планы[*]")
        self.setMinimumSize(1180, 760)

        self._create_actions()
        self._build_ui()
        self._connect_signals()

        self.autosave = AutoSaveController(
            debounce_ms=self.settings.autosave_debounce_ms,
            periodic_ms=self.settings.autosave_periodic_ms,
            parent=self,
        )
        self.autosave.save_requested.connect(self._on_autosave_requested)
        self.autosave.dirty_changed.connect(self.setWindowModified)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(180)
        self._preview_timer.timeout.connect(self._update_preview)

        if self.current_directory:
            self._refresh_file_list(show_message=False)
        self._load_plan_into_ui(TradingPlan.empty())
        self._update_file_status_label()

    def _create_actions(self) -> None:
        self.open_directory_action = QAction("Открыть папку", self)
        self.open_directory_action.setShortcut(QKeySequence("Ctrl+O"))
        self.open_directory_action.triggered.connect(self._choose_directory)

        self.new_plan_action = QAction("Новый план", self)
        self.new_plan_action.setShortcut(QKeySequence("Ctrl+N"))
        self.new_plan_action.triggered.connect(self._new_plan)

        self.save_action = QAction("Сохранить", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self._save)

        self.save_as_action = QAction("Сохранить как...", self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.triggered.connect(self._save_as)

        self.refresh_action = QAction("Обновить список", self)
        self.refresh_action.setShortcut(QKeySequence("F5"))
        self.refresh_action.triggered.connect(self._refresh_file_list)

    def _build_ui(self) -> None:
        toolbar = QToolBar("Панель")
        toolbar.setMovable(False)
        toolbar.addAction(self.open_directory_action)
        toolbar.addAction(self.new_plan_action)
        toolbar.addSeparator()
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.save_as_action)
        toolbar.addSeparator()
        toolbar.addAction(self.refresh_action)
        self.addToolBar(toolbar)

        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer_splitter.addWidget(self._build_sidebar())
        outer_splitter.addWidget(self._build_editor_with_preview())
        outer_splitter.setStretchFactor(0, 0)
        outer_splitter.setStretchFactor(1, 1)
        outer_splitter.setSizes([290, 890])
        root_layout.addWidget(outer_splitter)

        self.setCentralWidget(root)
        self._build_status_bar()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)

        self.folder_label = QLabel("Папка: не выбрана")
        self.folder_label.setWordWrap(True)
        sidebar_layout.addWidget(self.folder_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Фильтр по имени файла...")
        sidebar_layout.addWidget(self.search_edit)

        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        sidebar_layout.addWidget(self.file_list, 1)
        return sidebar

    def _build_editor_with_preview(self) -> QWidget:
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        title_label = QLabel("Название плана")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Введите название плана")
        left_layout.addWidget(title_label)
        left_layout.addWidget(self.title_edit)

        self.editor_stack = QStackedWidget(self)
        self.structured_page = self._build_structured_page()
        self.raw_page = self._build_raw_page()
        self.editor_stack.addWidget(self.structured_page)
        self.editor_stack.addWidget(self.raw_page)
        left_layout.addWidget(self.editor_stack, 1)

        preview_panel = QWidget(self)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(QLabel("Markdown-превью"))
        self.preview_browser = QTextBrowser()
        preview_layout.addWidget(self.preview_browser, 1)

        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(preview_panel)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setSizes([590, 450])

        wrapper = QWidget(self)
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(content_splitter)
        return wrapper

    def _build_structured_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(QLabel("1. Описание текущей ситуации"))
        self.block1_editor = QPlainTextEdit()
        self.block1_editor.setPlaceholderText("Контекст рынка, ключевые факторы, текущие уровни...")
        self.block1_editor.setMinimumHeight(150)
        layout.addWidget(self.block1_editor, 1)

        layout.addWidget(QLabel("2. Описание сценариев перехода к сделкам"))
        self.block2_editor = QPlainTextEdit()
        self.block2_editor.setPlaceholderText("Условия, при которых вы переходите к открытию позиции...")
        self.block2_editor.setMinimumHeight(150)
        layout.addWidget(self.block2_editor, 1)

        layout.addWidget(QLabel("3. Описание сценариев сделок"))
        self.block3_editor = QPlainTextEdit()
        self.block3_editor.setPlaceholderText("Точки входа, риски, цели, сопровождение позиции...")
        self.block3_editor.setMinimumHeight(150)
        layout.addWidget(self.block3_editor, 1)
        return page

    def _build_raw_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        notice = QLabel(
            "Шаблон из 3 секций не найден. Вы редактируете сырой Markdown. "
            "Можно нормализовать документ в стандартный шаблон."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self.normalize_button = QPushButton("Нормализовать в шаблон")
        layout.addWidget(self.normalize_button)

        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setPlaceholderText("Сырой Markdown")
        layout.addWidget(self.raw_editor, 1)
        return page

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

        self.file_status_label = QLabel("Файл: новый документ")
        self.autosave_status_label = QLabel("Автосохранение: ✓")
        self.last_saved_label = QLabel("Последнее сохранение: -")

        status_bar.addWidget(self.file_status_label, 1)
        status_bar.addPermanentWidget(self.autosave_status_label)
        status_bar.addPermanentWidget(self.last_saved_label)

    def _connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self._apply_filter)
        self.file_list.itemDoubleClicked.connect(self._open_item)
        self.file_list.itemActivated.connect(self._open_item)

        self.title_edit.textChanged.connect(self._on_editor_changed)
        self.block1_editor.textChanged.connect(self._on_editor_changed)
        self.block2_editor.textChanged.connect(self._on_editor_changed)
        self.block3_editor.textChanged.connect(self._on_editor_changed)
        self.raw_editor.textChanged.connect(self._on_editor_changed)
        self.normalize_button.clicked.connect(self._normalize_raw_document)

    def _set_autosave_status(self, text: str) -> None:
        self.autosave_status_label.setText(text)

    def _set_saved_now(self) -> None:
        self.last_saved_label.setText(f"Последнее сохранение: {datetime.now().strftime('%H:%M:%S')}")

    def _update_file_status_label(self) -> None:
        if self.current_file:
            self.file_status_label.setText(f"Файл: {self.current_file}")
            return
        if self.current_draft_path:
            self.file_status_label.setText(f"Черновик: {self.current_draft_path}")
            return
        self.file_status_label.setText("Файл: новый документ")

    def _editor_in_structured_mode(self) -> bool:
        return self.editor_stack.currentWidget() is self.structured_page

    def _schedule_preview_refresh(self) -> None:
        self._preview_timer.start()

    def _on_editor_changed(self) -> None:
        if self._updating:
            return
        self.autosave.mark_dirty()
        self._set_autosave_status("Автосохранение: ожидает...")
        self._schedule_preview_refresh()

    def _choose_directory(self) -> None:
        if not self._ensure_saved_before_navigation():
            return

        start_dir = str(self.current_directory) if self.current_directory else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Выберите папку с планами", start_dir)
        if not selected:
            return

        self.current_directory = Path(selected)
        self.settings.last_directory = str(self.current_directory)
        self.settings.save()
        self._refresh_file_list()

    def _refresh_file_list(self, show_message: bool = True) -> None:
        self.file_list.clear()

        if not self.current_directory:
            self.folder_label.setText("Папка: не выбрана")
            self.file_cache = []
            return

        self.folder_label.setText(f"Папка: {self.current_directory}")
        try:
            self.file_cache = list_markdown_files(self.current_directory)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка чтения папки", f"Не удалось прочитать папку:\n{exc}")
            self.file_cache = []

        self._apply_filter()
        if show_message:
            self.statusBar().showMessage("Список файлов обновлён", 3000)

    def _apply_filter(self) -> None:
        self.file_list.clear()
        filter_text = self.search_edit.text().strip().casefold()

        shown = 0
        for info in self.file_cache:
            name = info.path.name
            if filter_text and filter_text not in name.casefold():
                continue
            shown += 1
            modified = info.modified_at.strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{name}    {modified}")
            item.setData(Qt.ItemDataRole.UserRole, str(info.path))
            item.setToolTip(str(info.path))
            self.file_list.addItem(item)

        if shown == 0:
            placeholder = QListWidgetItem("(файлы .md не найдены)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.file_list.addItem(placeholder)

    def _open_item(self, item: QListWidgetItem) -> None:
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return

        if not self._ensure_saved_before_navigation():
            return
        self._open_file(Path(file_path))

    def _open_file(self, path: Path) -> None:
        try:
            markdown = read_markdown(path)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка чтения файла", f"Не удалось открыть файл:\n{path}\n\n{exc}")
            return

        plan = TradingPlan.from_markdown(markdown, fallback_title=path.stem)
        self.current_file = path
        self.current_draft_path = None
        self.current_plan = plan
        self._load_plan_into_ui(plan)
        self.autosave.clear_dirty()
        self._set_autosave_status("Автосохранение: ✓")
        self.last_saved_label.setText("Последнее сохранение: открыт файл")
        self._update_file_status_label()
        self.settings.touch_recent_file(str(path))
        self.settings.save()

        if not plan.structured:
            self.statusBar().showMessage("Шаблон не найден: включён режим сырого Markdown", 6000)
        else:
            self.statusBar().showMessage(f"Открыт файл: {path.name}", 3000)

    def _load_plan_into_ui(self, plan: TradingPlan) -> None:
        self._updating = True
        self.title_edit.setText(plan.title)

        if plan.structured:
            self.editor_stack.setCurrentWidget(self.structured_page)
            self.block1_editor.setPlainText(plan.block1)
            self.block2_editor.setPlainText(plan.block2)
            self.block3_editor.setPlainText(plan.block3)
            self.raw_editor.setPlainText("")
        else:
            self.editor_stack.setCurrentWidget(self.raw_page)
            self.raw_editor.setPlainText(plan.raw_markdown)
            self.block1_editor.setPlainText("")
            self.block2_editor.setPlainText("")
            self.block3_editor.setPlainText("")

        self._updating = False
        self._update_preview()

    def _new_plan(self) -> None:
        if not self._ensure_saved_before_navigation():
            return

        title, accepted = QInputDialog.getText(self, "Новый план", "Название плана:")
        if not accepted:
            return

        plan = TradingPlan.empty(title.strip() or "Новый торговый план")
        self.current_plan = plan
        self.current_file = None
        self.current_draft_path = None
        self._load_plan_into_ui(plan)
        self.autosave.clear_dirty()
        self._set_autosave_status("Автосохранение: ✓")
        self.last_saved_label.setText("Последнее сохранение: -")
        self._update_file_status_label()
        self.statusBar().showMessage("Создан новый план", 3000)

    def _suggest_file_name(self) -> str:
        title = self.title_edit.text().strip() or "trade_plan"
        cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", title).strip(". ")
        cleaned = cleaned or "trade_plan"
        return f"{cleaned}.md"

    def _ask_save_path(self) -> Path | None:
        if self.current_directory:
            start_dir = self.current_directory
        elif self.settings.last_directory:
            start_dir = Path(self.settings.last_directory)
        else:
            start_dir = Path.home()
        suggested = str(start_dir / self._suggest_file_name())
        selected, _ = QFileDialog.getSaveFileName(self, "Сохранить план как", suggested, "Markdown (*.md)")
        if not selected:
            return None

        path = Path(selected)
        if path.suffix.lower() != ".md":
            path = path.with_suffix(".md")
        return path

    def _compose_current_markdown(self) -> tuple[str, TradingPlan | None]:
        title = self.title_edit.text().strip() or "Без названия"

        if self._editor_in_structured_mode():
            extras = self.current_plan.extras if self.current_plan.structured else ""
            plan = TradingPlan(
                title=title,
                block1=self.block1_editor.toPlainText(),
                block2=self.block2_editor.toPlainText(),
                block3=self.block3_editor.toPlainText(),
                extras=extras,
                structured=True,
            )
            return plan.to_markdown(), plan

        raw_markdown = apply_title_to_markdown(self.raw_editor.toPlainText(), title)
        return raw_markdown, None

    def _save_to_target(self, target: Path, markdown: str, explicit: bool) -> bool:
        try:
            save_markdown(target, markdown)
        except OSError as exc:
            self._set_autosave_status("Автосохранение: ошибка")
            self.statusBar().showMessage(f"Ошибка сохранения: {exc}", 7000)
            if explicit:
                QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить файл:\n{target}\n\n{exc}")
            return False
        return True

    def _save_internal(self, explicit: bool, save_as: bool = False, autosave: bool = False) -> bool:
        markdown, plan = self._compose_current_markdown()

        target_path: Path | None = None
        if save_as:
            target_path = self._ask_save_path()
            if not target_path:
                return False
        elif self.current_file:
            target_path = self.current_file
        elif autosave:
            if self.current_draft_path is None:
                self.current_draft_path = build_draft_path(self.current_directory)
            target_path = self.current_draft_path
        elif explicit:
            target_path = self._ask_save_path()
            if not target_path:
                return False
        else:
            if self.current_draft_path is None:
                self.current_draft_path = build_draft_path(self.current_directory)
            target_path = self.current_draft_path

        if not self._save_to_target(target=target_path, markdown=markdown, explicit=explicit):
            return False

        if plan is not None:
            self.current_plan = plan
        else:
            self.current_plan = TradingPlan.from_markdown(markdown, fallback_title=self.title_edit.text().strip())

        if save_as or explicit:
            self.current_file = target_path
            self.current_draft_path = None
            self.current_directory = target_path.parent
            self.settings.last_directory = str(self.current_directory)
            self.settings.touch_recent_file(str(target_path))
            self.settings.save()
            self._refresh_file_list(show_message=False)
        elif autosave and self.current_file is None:
            self.current_draft_path = target_path

        self.autosave.clear_dirty()
        self._set_autosave_status("Автосохранение: ✓")
        self._set_saved_now()
        self._update_file_status_label()

        if explicit:
            self.statusBar().showMessage(f"Сохранено: {target_path.name}", 3000)
        return True

    def _save(self) -> None:
        self._save_internal(explicit=True, save_as=False, autosave=False)

    def _save_as(self) -> None:
        self._save_internal(explicit=True, save_as=True, autosave=False)

    def _on_autosave_requested(self, _: str) -> None:
        if not self.autosave.dirty:
            return
        self._set_autosave_status("Автосохранение...")
        ok = self._save_internal(explicit=False, save_as=False, autosave=True)
        if not ok:
            self._set_autosave_status("Автосохранение: ошибка")

    def _ensure_saved_before_navigation(self) -> bool:
        if not self.autosave.dirty:
            return True

        self._set_autosave_status("Автосохранение...")
        if self._save_internal(explicit=False, save_as=False, autosave=True):
            return True

        answer = QMessageBox.question(
            self,
            "Изменения не сохранены",
            "Не удалось сохранить изменения автоматически. Продолжить и потерять несохранённые правки?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _normalize_raw_document(self) -> None:
        if self.editor_stack.currentWidget() is not self.raw_page:
            return

        normalized = TradingPlan.normalize_raw(
            raw_markdown=self.raw_editor.toPlainText(),
            title=self.title_edit.text().strip() or "Новый торговый план",
        )
        self.current_plan = normalized
        self._load_plan_into_ui(normalized)
        self.autosave.mark_dirty()
        self._set_autosave_status("Автосохранение: ожидает...")
        self.statusBar().showMessage("Документ нормализован в шаблон из 3 секций", 4000)

    def _preview_markdown(self) -> str:
        markdown, _ = self._compose_current_markdown()
        return markdown

    def _update_preview(self) -> None:
        markdown = self._preview_markdown()
        if markdown_renderer is None:
            body = f"<pre>{html.escape(markdown)}</pre>"
        else:
            body = markdown_renderer.markdown(markdown, extensions=["fenced_code", "tables", "sane_lists"])

        rendered = f"""
        <html>
          <head>
            <style>
              body {{
                font-family: "Segoe UI", "Noto Sans", sans-serif;
                font-size: 14px;
                line-height: 1.5;
                color: #1c2530;
                background: #ffffff;
                margin: 12px;
              }}
              pre {{
                background: #f7f8fa;
                border: 1px solid #d8dde6;
                border-radius: 8px;
                padding: 10px;
                white-space: pre-wrap;
                word-wrap: break-word;
              }}
              code {{
                background: #f2f4f8;
                padding: 1px 3px;
                border-radius: 4px;
              }}
              table, th, td {{
                border: 1px solid #d8dde6;
                border-collapse: collapse;
                padding: 5px 7px;
              }}
            </style>
          </head>
          <body>{body}</body>
        </html>
        """
        self.preview_browser.setHtml(rendered)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._ensure_saved_before_navigation():
            event.accept()
            return
        event.ignore()
