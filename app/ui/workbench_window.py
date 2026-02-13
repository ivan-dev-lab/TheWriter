from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
from pathlib import Path
import re
import shutil

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTabBar,
    QButtonGroup,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.autosave import AutoSaveController
from ..core.plans import TradingPlan, apply_title_to_markdown
from ..core.storage import PlanFileInfo, build_draft_path, list_markdown_files, read_markdown, save_markdown
from ..settings import AppSettings, get_default_workspace_dir
from .current_situation import CurrentSituationEditor, notation_to_text as current_situation_notation_to_text
from .deal_scenarios import DealScenariosEditor
from .theme import ThemeTokens, build_app_stylesheet, build_markdown_css, get_theme_tokens
from .transition_scenarios import TransitionScenariosEditor

try:
    import markdown as markdown_renderer
except ImportError:
    markdown_renderer = None


@dataclass(slots=True)
class QuickPickItem:
    label: str
    detail: str
    payload: object


@dataclass(slots=True)
class TfPanelPreview:
    timeframe: str
    image_path: str
    notation: str
    text: str


@dataclass(slots=True)
class SituationPreview:
    title: str
    panels: list[TfPanelPreview]


_IMAGE_MD_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
_SITUATION_H4_RE = re.compile(r"(?mi)^####\s+(.+?)\s*$")
_TF_LINE_RE = re.compile(r"(?mi)^(?:\*\*TF:\*\*|TF:)\s*(.+?)\s*$")
_NOTATION_COMMENT_RE = re.compile(r"(?is)<!--\s*NOTATION\s*(.*?)\s*-->")
_INLINE_CODE_RE = re.compile(r"\[([^\]\n]{1,120})\](?!\()")
_IMAGE_THEN_TF_RE = re.compile(
    r"(?mis)(!\[[^\]]*]\([^)]+\))\s*\n(?:\s*\n)?((?:\*\*TF:\*\*|TF:)\s*[^\n]+)"
)


class QuickPickDialog(QDialog):
    def __init__(self, title: str, placeholder: str, items: list[QuickPickItem], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(720, 420)
        self._items = items
        self._payload: object | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(placeholder)
        root.addWidget(self.search_edit)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        root.addWidget(self.list_widget, 1)

        self.search_edit.textChanged.connect(self._apply_filter)
        self.search_edit.returnPressed.connect(self._accept_current)
        self.list_widget.itemActivated.connect(self._accept_item)
        self.list_widget.itemDoubleClicked.connect(self._accept_item)
        self._apply_filter()

    def selected_payload(self) -> object | None:
        return self._payload

    def _accept_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None and self.list_widget.count() > 0:
            item = self.list_widget.item(0)
        if item is not None:
            self._accept_item(item)

    def _accept_item(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if payload is None:
            return
        self._payload = payload
        self.accept()

    def _apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        self.list_widget.clear()
        for entry in self._items:
            haystack = f"{entry.label} {entry.detail}".casefold()
            if query and query not in haystack:
                continue
            text = entry.label if not entry.detail else f"{entry.label}\n{entry.detail}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry.payload)
            item.setToolTip(entry.detail or entry.label)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)


class CollapsibleSection(QFrame):
    toggled = Signal(bool)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(8)

        self.toggle_button = QToolButton(header)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle_button.setText(title)
        header_layout.addWidget(self.toggle_button, 1)

        self.status_label = QLabel("", header)
        self.status_label.setObjectName("muted")
        header_layout.addWidget(self.status_label)
        root.addWidget(header)

        self.body = QFrame(self)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(10, 6, 10, 10)
        body_layout.setSpacing(8)
        root.addWidget(self.body)

        self.toggle_button.toggled.connect(self._on_toggled)

    def set_content(self, widget: QWidget) -> None:
        layout = self.body.layout()
        if layout is None:
            return
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        layout.addWidget(widget)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_toggled(self, checked: bool) -> None:
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.body.setVisible(checked)
        self.toggled.emit(checked)


class MainWindow(QMainWindow):
    SIDEBAR_COLLAPSE_WIDTH = 120
    SIDEBAR_DEFAULT_WIDTH = 290

    @staticmethod
    def _normalize_root_directory(directory: Path) -> Path:
        if directory.name.casefold() == "plans" and directory.parent != directory:
            return directory.parent
        return directory

    @staticmethod
    def _should_ignore_saved_directory(directory: Path) -> bool:
        return (directory / "app" / "main.py").exists() and (directory / "AGENTS.md").exists()

    def __init__(self) -> None:
        super().__init__()
        self.settings = AppSettings.load()
        self._theme_tokens: ThemeTokens = get_theme_tokens(self.settings.ui_theme)

        self.current_directory: Path | None = None
        default_root = self._normalize_root_directory(get_default_workspace_dir())
        if self.settings.last_directory:
            candidate = Path(self.settings.last_directory)
            if candidate.exists() and candidate.is_dir():
                normalized = self._normalize_root_directory(candidate)
                if not self._should_ignore_saved_directory(normalized):
                    self.current_directory = normalized

        if self.current_directory is None:
            self.current_directory = default_root
            self.settings.last_directory = str(default_root)
            self.settings.save()

        self.current_file: Path | None = None
        self.current_draft_path: Path | None = None
        self.current_plan = TradingPlan.empty()
        self.file_cache: list[PlanFileInfo] = []
        self._updating = False
        self._sidebar_last_width = self.settings.sidebar_width or self.SIDEBAR_DEFAULT_WIDTH
        self._sidebar_mode = "plans"
        self._editor_mode = "edit"

        self.setWindowTitle("TheWriter - Торговые планы[*]")
        self.setMinimumSize(1260, 780)

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
        self.autosave.dirty_changed.connect(lambda _dirty: self._update_editor_tab_caption())

        self._apply_theme(self.settings.ui_theme, persist=False)
        self._apply_sidebar_visibility(self.settings.sidebar_visible, persist=False)

        if self.current_directory:
            self._refresh_file_list(show_message=False)

        opened_last = False
        if self.settings.last_open_file:
            last_file = Path(self.settings.last_open_file)
            last_root = self._resolve_root_directory_from_plan_path(last_file) if last_file.exists() else None
            ignore_last = bool(last_root and self._should_ignore_saved_directory(last_root))
            if ignore_last:
                self.settings.last_open_file = ""
                self.settings.save()
            if (not ignore_last) and last_file.exists() and last_file.is_file() and last_file.suffix.lower() == ".md":
                self._open_file(last_file)
                opened_last = True

        if not opened_last:
            self._load_plan_into_ui(TradingPlan.empty())
        self._apply_editor_mode("edit", emit_change=False)
        self._update_file_status_label()
        self._refresh_section_statuses()
        self._refresh_context_status()

    def _create_actions(self) -> None:
        self.open_directory_action = QAction("Открыть папку", self)
        self.open_directory_action.setShortcut(QKeySequence("Ctrl+O"))
        self.open_directory_action.triggered.connect(self._choose_directory)
        self.open_directory_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))

        self.new_plan_action = QAction("Новый план", self)
        self.new_plan_action.setShortcut(QKeySequence("Ctrl+N"))
        self.new_plan_action.triggered.connect(self._new_plan)
        self.new_plan_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))

        self.save_action = QAction("Сохранить", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self._save)
        self.save_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))

        self.save_as_action = QAction("Сохранить как...", self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.triggered.connect(self._save_as)
        self.save_as_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))

        self.refresh_action = QAction("Обновить список", self)
        self.refresh_action.setShortcut(QKeySequence("F5"))
        self.refresh_action.triggered.connect(self._refresh_file_list)
        self.refresh_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))

        self.toggle_sidebar_action = QAction("Показать файлы", self)
        self.toggle_sidebar_action.setCheckable(True)
        self.toggle_sidebar_action.setChecked(True)
        self.toggle_sidebar_action.setShortcut(QKeySequence("Ctrl+B"))
        self.toggle_sidebar_action.toggled.connect(self._toggle_sidebar)

        self.toggle_theme_action = QAction("Переключить тему", self)
        self.toggle_theme_action.setShortcut(QKeySequence("Ctrl+Alt+T"))
        self.toggle_theme_action.triggered.connect(self._toggle_theme)

        self.command_palette_action = QAction("Командная палитра", self)
        self.command_palette_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.command_palette_action.triggered.connect(self._show_command_palette)

        self.quick_open_action = QAction("Быстрое открытие", self)
        self.quick_open_action.setShortcut(QKeySequence("Ctrl+P"))
        self.quick_open_action.triggered.connect(self._show_quick_open)

        self.addAction(self.command_palette_action)
        self.addAction(self.quick_open_action)
        self._update_toggle_icons()

    def _build_ui(self) -> None:
        root = QFrame(self)
        root.setObjectName("workbenchRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.activity_bar = self._build_activity_bar()
        root_layout.addWidget(self.activity_bar)

        self.outer_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.outer_splitter.setChildrenCollapsible(True)
        root_layout.addWidget(self.outer_splitter, 1)

        self.sidebar_panel = self._build_sidebar()
        self.outer_splitter.addWidget(self.sidebar_panel)

        self.editor_shell = self._build_editor_shell()
        self.outer_splitter.addWidget(self.editor_shell)
        self.outer_splitter.setStretchFactor(0, 0)
        self.outer_splitter.setStretchFactor(1, 1)
        self.outer_splitter.setCollapsible(0, True)
        self.outer_splitter.setCollapsible(1, False)
        self.outer_splitter.setSizes([self._sidebar_last_width, 900])
        self.outer_splitter.splitterMoved.connect(self._on_outer_splitter_moved)

        self.setCentralWidget(root)
        self._build_status_bar()

    def _build_activity_bar(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("activityBar")
        frame.setFixedWidth(50)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(6)

        self.activity_plans_button = QToolButton(frame)
        self.activity_plans_button.setCheckable(True)
        self.activity_plans_button.setChecked(True)
        self.activity_plans_button.setToolTip("Планы")
        self.activity_plans_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon))
        self.activity_plans_button.clicked.connect(lambda: self._set_sidebar_mode("plans"))
        layout.addWidget(self.activity_plans_button)

        self.activity_templates_button = QToolButton(frame)
        self.activity_templates_button.setCheckable(True)
        self.activity_templates_button.setToolTip("Шаблоны")
        self.activity_templates_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.activity_templates_button.clicked.connect(lambda: self._set_sidebar_mode("templates"))
        layout.addWidget(self.activity_templates_button)

        self.activity_settings_button = QToolButton(frame)
        self.activity_settings_button.setCheckable(True)
        self.activity_settings_button.setToolTip("Настройки")
        self.activity_settings_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
        self.activity_settings_button.clicked.connect(lambda: self._set_sidebar_mode("settings"))
        layout.addWidget(self.activity_settings_button)

        layout.addStretch(1)

        self.activity_group = [self.activity_plans_button, self.activity_templates_button, self.activity_settings_button]
        return frame

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("sideBar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.sidebar_title_label = QLabel("Планы")
        layout.addWidget(self.sidebar_title_label)

        self.sidebar_stack = QStackedWidget(sidebar)
        layout.addWidget(self.sidebar_stack, 1)

        plans_page = QWidget(sidebar)
        plans_layout = QVBoxLayout(plans_page)
        plans_layout.setContentsMargins(0, 0, 0, 0)
        plans_layout.setSpacing(8)

        self.folder_label = QLabel("Папка: не выбрана")
        self.folder_label.setWordWrap(True)
        self.folder_label.setObjectName("muted")
        plans_layout.addWidget(self.folder_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Фильтр по имени файла...")
        plans_layout.addWidget(self.search_edit)

        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(False)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        plans_layout.addWidget(self.file_list, 1)
        self.sidebar_stack.addWidget(plans_page)

        templates_page = QWidget(sidebar)
        templates_layout = QVBoxLayout(templates_page)
        templates_layout.setContentsMargins(0, 0, 0, 0)
        templates_layout.setSpacing(8)
        templates_hint = QLabel("Раздел шаблонов пока в разработке.")
        templates_hint.setWordWrap(True)
        templates_hint.setObjectName("muted")
        templates_layout.addWidget(templates_hint)
        templates_layout.addStretch(1)
        self.sidebar_stack.addWidget(templates_page)

        settings_page = QWidget(sidebar)
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(8)

        settings_layout.addWidget(QLabel("Тема"))
        self.theme_combo = QComboBox(settings_page)
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        settings_layout.addWidget(self.theme_combo)

        quick_hint = QLabel("Ctrl+P - Quick Open\nCtrl+Shift+P - Command Palette")
        quick_hint.setObjectName("muted")
        quick_hint.setWordWrap(True)
        settings_layout.addWidget(quick_hint)
        settings_layout.addStretch(1)
        self.sidebar_stack.addWidget(settings_page)

        self._set_sidebar_mode("plans")
        return sidebar

    def _build_editor_shell(self) -> QWidget:
        shell = QFrame(self)
        shell.setObjectName("editorSurface")
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_toolbar = self._build_title_toolbar()
        layout.addWidget(self.title_toolbar)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal, shell)
        self.content_splitter.setChildrenCollapsible(True)
        layout.addWidget(self.content_splitter, 1)

        self.editor_panel = self._build_editor_panel()
        self.content_splitter.addWidget(self.editor_panel)
        self.content_splitter.setCollapsible(0, False)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setSizes([900])
        return shell

    def _build_title_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Workbench", self)
        toolbar.setObjectName("titleToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.addAction(self.open_directory_action)
        toolbar.addAction(self.new_plan_action)
        toolbar.addSeparator()
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.save_as_action)
        toolbar.addAction(self.refresh_action)
        toolbar.addSeparator()
        toolbar.addAction(self.toggle_sidebar_action)
        toolbar.addSeparator()
        mode_switcher = QWidget(toolbar)
        mode_layout = QHBoxLayout(mode_switcher)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)

        self.edit_mode_button = QToolButton(mode_switcher)
        self.edit_mode_button.setText("Режим редактирования")
        self.edit_mode_button.setCheckable(True)
        self.edit_mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.edit_mode_button.clicked.connect(lambda: self._apply_editor_mode("edit"))

        self.read_mode_button = QToolButton(mode_switcher)
        self.read_mode_button.setText("Режим чтения")
        self.read_mode_button.setCheckable(True)
        self.read_mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.read_mode_button.clicked.connect(lambda: self._apply_editor_mode("read"))

        self.mode_group = QButtonGroup(mode_switcher)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.edit_mode_button)
        self.mode_group.addButton(self.read_mode_button)

        mode_layout.addWidget(self.edit_mode_button)
        mode_layout.addWidget(self.read_mode_button)
        toolbar.addWidget(mode_switcher)
        toolbar.addSeparator()
        toolbar.addAction(self.toggle_theme_action)
        return toolbar

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.editor_tabs = QTabBar(panel)
        self.editor_tabs.setDocumentMode(True)
        self.editor_tabs.setExpanding(False)
        self.editor_tabs.addTab("Новый план")
        layout.addWidget(self.editor_tabs)

        self.editor_stack = QStackedWidget(panel)
        self.structured_page = self._build_structured_page()
        self.raw_page = self._build_raw_page()
        self.editor_stack.addWidget(self.structured_page)
        self.editor_stack.addWidget(self.raw_page)
        layout.addWidget(self.editor_stack, 1)
        return panel

    def _build_structured_page(self) -> QWidget:
        content = QWidget(self)
        content.setObjectName("editorSurface")
        page_layout = QVBoxLayout(content)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Название плана"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Введите название плана")
        title_row.addWidget(self.title_edit, 1)
        page_layout.addLayout(title_row)

        self.current_situation_editor = CurrentSituationEditor(self)
        self.current_situation_editor.setMinimumHeight(260)
        self.section_current = CollapsibleSection("1. Описание текущей ситуации", content)
        self.section_current.set_content(self.current_situation_editor)
        page_layout.addWidget(self.section_current)

        self.transition_scenarios_editor = TransitionScenariosEditor(self)
        self.transition_scenarios_editor.setMinimumHeight(260)
        self.section_transition = CollapsibleSection("2. Описание сценариев перехода к сделкам", content)
        self.section_transition.set_content(self.transition_scenarios_editor)
        page_layout.addWidget(self.section_transition)

        self.deal_scenarios_editor = DealScenariosEditor(self)
        self.deal_scenarios_editor.setMinimumHeight(260)
        self.section_deal = CollapsibleSection("3. Описание сценариев сделок", content)
        self.section_deal.set_content(self.deal_scenarios_editor)
        page_layout.addWidget(self.section_deal)
        page_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _build_raw_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        notice = QLabel(
            "Шаблон из 3 секций не найден. Вы редактируете сырой Markdown. "
            "Можно нормализовать документ в стандартный шаблон."
        )
        notice.setWordWrap(True)
        notice.setObjectName("muted")
        layout.addWidget(notice)

        self.normalize_button = QPushButton("Нормализовать в шаблон")
        layout.addWidget(self.normalize_button)

        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setPlaceholderText("Сырой Markdown")
        layout.addWidget(self.raw_editor, 1)
        return page

    def _apply_editor_mode(self, mode: str, emit_change: bool = True) -> None:
        normalized = "read" if mode == "read" else "edit"
        self._editor_mode = normalized
        is_read = normalized == "read"

        if hasattr(self, "edit_mode_button"):
            self.edit_mode_button.blockSignals(True)
            self.edit_mode_button.setChecked(not is_read)
            self.edit_mode_button.blockSignals(False)
        if hasattr(self, "read_mode_button"):
            self.read_mode_button.blockSignals(True)
            self.read_mode_button.setChecked(is_read)
            self.read_mode_button.blockSignals(False)

        if hasattr(self, "current_situation_editor"):
            self.current_situation_editor.set_read_mode(is_read)
        if hasattr(self, "transition_scenarios_editor"):
            self.transition_scenarios_editor.set_read_mode(is_read)
        if hasattr(self, "deal_scenarios_editor"):
            self.deal_scenarios_editor.set_read_mode(is_read)
        if hasattr(self, "title_edit"):
            self.title_edit.setReadOnly(is_read)

        if emit_change:
            self._refresh_section_statuses()
            self.statusBar().showMessage("Режим чтения" if is_read else "Режим редактирования", 1500)

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

        self.file_status_label = QLabel("Файл: новый документ")
        self.autosave_status_label = QLabel("Автосохранение: ON")
        self.last_saved_label = QLabel("Сохранение: -")
        self.tf_status_label = QLabel("TF: -")
        self.validation_status_label = QLabel("Валидность: -")
        self.hint_status_label = QLabel("Ctrl+P открыть план · Ctrl+Shift+P команды")

        status_bar.addWidget(self.file_status_label, 1)
        status_bar.addPermanentWidget(self.autosave_status_label)
        status_bar.addPermanentWidget(self.last_saved_label)
        status_bar.addPermanentWidget(self.tf_status_label)
        status_bar.addPermanentWidget(self.validation_status_label)
        status_bar.addPermanentWidget(self.hint_status_label)

    def _connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self._apply_filter)
        self.file_list.itemDoubleClicked.connect(self._open_item)
        self.file_list.itemActivated.connect(self._open_item)
        self.file_list.customContextMenuRequested.connect(self._show_file_context_menu)

        self.title_edit.textChanged.connect(self._on_editor_changed)
        self.current_situation_editor.content_changed.connect(self._on_editor_changed)
        self.transition_scenarios_editor.content_changed.connect(self._sync_deal_transition_choices)
        self.transition_scenarios_editor.content_changed.connect(self._on_editor_changed)
        self.deal_scenarios_editor.content_changed.connect(self._on_editor_changed)
        self.raw_editor.textChanged.connect(self._on_editor_changed)
        self.normalize_button.clicked.connect(self._normalize_raw_document)

        self.theme_combo.currentIndexChanged.connect(self._theme_from_settings_panel)

    def _set_sidebar_mode(self, mode: str) -> None:
        self._sidebar_mode = mode
        self.activity_plans_button.setChecked(mode == "plans")
        self.activity_templates_button.setChecked(mode == "templates")
        self.activity_settings_button.setChecked(mode == "settings")

        index_map = {"plans": 0, "templates": 1, "settings": 2}
        title_map = {"plans": "Планы", "templates": "Шаблоны", "settings": "Настройки"}
        self.sidebar_stack.setCurrentIndex(index_map.get(mode, 0))
        self.sidebar_title_label.setText(title_map.get(mode, "Планы"))

    def _theme_from_settings_panel(self) -> None:
        theme = self.theme_combo.currentData()
        if isinstance(theme, str):
            self._apply_theme(theme)


    def _toggle_theme(self) -> None:
        next_theme = "light" if self.settings.ui_theme == "dark" else "dark"
        self._apply_theme(next_theme)

    def _apply_theme(self, theme_name: str, persist: bool = True) -> None:
        tokens = get_theme_tokens(theme_name)
        self._theme_tokens = tokens
        self.settings.ui_theme = tokens.name

        app = self.window().windowHandle()
        _ = app
        if self.theme_combo.currentData() != tokens.name:
            self.theme_combo.blockSignals(True)
            idx = self.theme_combo.findData(tokens.name)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)

        self.setStyleSheet(build_app_stylesheet(tokens))
        self._update_preview()
        if persist:
            self.settings.save()

    def _toggle_sidebar(self, visible: bool) -> None:
        self._apply_sidebar_visibility(visible)
        self._update_toggle_icons()

    def _apply_sidebar_visibility(self, visible: bool, persist: bool = True) -> None:
        self.settings.sidebar_visible = visible
        if visible:
            self.sidebar_panel.show()
            total = max(760, self.outer_splitter.size().width())
            width = max(self.SIDEBAR_COLLAPSE_WIDTH + 40, self._sidebar_last_width)
            width = min(width, total - 420)
            self.outer_splitter.setSizes([width, total - width])
        else:
            sizes = self.outer_splitter.sizes()
            if len(sizes) > 1 and sizes[0] > self.SIDEBAR_COLLAPSE_WIDTH:
                self._sidebar_last_width = sizes[0]
            self.sidebar_panel.hide()
            self.outer_splitter.setSizes([0, 1])

        if persist:
            self.settings.sidebar_width = int(self._sidebar_last_width)
            self.settings.save()

    def _on_outer_splitter_moved(self, _: int, __: int) -> None:
        if not self.toggle_sidebar_action.isChecked():
            return
        sizes = self.outer_splitter.sizes()
        if len(sizes) < 2:
            return
        sidebar_width = sizes[0]
        if sidebar_width <= self.SIDEBAR_COLLAPSE_WIDTH:
            self.toggle_sidebar_action.blockSignals(True)
            self.toggle_sidebar_action.setChecked(False)
            self.toggle_sidebar_action.blockSignals(False)
            self._apply_sidebar_visibility(False)
            self._update_toggle_icons()
            return
        self._sidebar_last_width = sidebar_width
        self.settings.sidebar_width = int(sidebar_width)

    def _update_toggle_icons(self) -> None:
        if self.toggle_sidebar_action.isChecked():
            self.toggle_sidebar_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        else:
            self.toggle_sidebar_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))

        self.toggle_theme_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon))

    def _show_file_context_menu(self, pos) -> None:
        item = self.file_list.itemAt(pos)
        if item is None:
            return
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            return
        path = Path(file_path)
        menu = QMenu(self)
        open_action = menu.addAction("Открыть")
        rename_action = menu.addAction("Переименовать")
        delete_action = menu.addAction("Удалить")
        menu.addSeparator()
        reveal_action = menu.addAction("Показать в папке")
        selected = menu.exec(self.file_list.mapToGlobal(pos))
        if selected is None:
            return
        if selected == open_action:
            if self._ensure_saved_before_navigation():
                self._open_file(path)
            return
        if selected == rename_action:
            self._rename_plan(path)
            return
        if selected == delete_action:
            self._delete_plan(path)
            return
        if selected == reveal_action:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _rename_plan(self, path: Path) -> None:
        new_name, accepted = QInputDialog.getText(self, "Переименование", "Новое имя файла:", text=path.stem)
        if not accepted:
            return
        cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", new_name.strip()).strip(". ")
        if not cleaned:
            return
        target = path.with_name(f"{cleaned}.md")
        if target == path:
            return
        if target.exists():
            QMessageBox.warning(self, "Переименование", "Файл с таким именем уже существует.")
            return
        try:
            path.rename(target)
        except OSError as exc:
            QMessageBox.critical(self, "Переименование", f"Не удалось переименовать файл:\n{exc}")
            return

        if self.current_file == path:
            self.current_file = target
            self._update_file_status_label()
            self.settings.last_open_file = str(target)
            self.settings.touch_recent_file(str(target))
            self.settings.save()
        self._refresh_file_list(show_message=False)
        self.statusBar().showMessage("Файл переименован", 2500)

    def _delete_plan(self, path: Path) -> None:
        answer = QMessageBox.question(
            self,
            "Удаление файла",
            f"Удалить файл?\n{path.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink(missing_ok=False)
        except OSError as exc:
            QMessageBox.critical(self, "Удаление файла", f"Не удалось удалить файл:\n{exc}")
            return

        if self.current_file == path:
            self.current_file = None
            self.current_draft_path = None
            self.current_plan = TradingPlan.empty()
            self._load_plan_into_ui(self.current_plan)
            self.settings.last_open_file = ""
            self.settings.save()
        self._refresh_file_list(show_message=False)
        self.statusBar().showMessage("Файл удален", 2500)

    def _show_command_palette(self) -> None:
        commands: list[QuickPickItem] = [
            QuickPickItem("Открыть папку", "Ctrl+O", self._choose_directory),
            QuickPickItem("Новый план", "Ctrl+N", self._new_plan),
            QuickPickItem("Сохранить", "Ctrl+S", self._save),
            QuickPickItem("Сохранить как...", "Ctrl+Shift+S", self._save_as),
            QuickPickItem("Обновить список", "F5", self._refresh_file_list),
            QuickPickItem("Показать/скрыть sidebar", "Ctrl+B", lambda: self.toggle_sidebar_action.trigger()),
            QuickPickItem("Переключить тему", "Ctrl+Alt+T", self._toggle_theme),
        ]
        dialog = QuickPickDialog("Command Palette", "Введите команду...", commands, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.selected_payload()
        if callable(payload):
            payload()

    def _show_quick_open(self) -> None:
        if self.current_directory and not self.file_cache:
            self._refresh_file_list(show_message=False)

        entries: list[QuickPickItem] = []
        known: set[str] = set()
        for info in self.file_cache:
            path = str(info.path)
            known.add(path)
            entries.append(
                QuickPickItem(
                    label=info.path.name,
                    detail=path,
                    payload=Path(path),
                )
            )
        for item in self.settings.recent_files:
            if item in known:
                continue
            path = Path(item)
            entries.append(QuickPickItem(label=path.name, detail=item, payload=path))

        dialog = QuickPickDialog("Quick Open", "Введите имя плана...", entries, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.selected_payload()
        if not isinstance(payload, Path):
            return
        if not payload.exists():
            QMessageBox.warning(self, "Quick Open", "Файл не найден.")
            return
        if self._ensure_saved_before_navigation():
            self._open_file(payload)

    def _validate_image_text_rules(self, explicit: bool) -> bool:
        if not self._editor_in_structured_mode():
            return True

        ok, message = self.current_situation_editor.validate_content()
        if not ok:
            self._set_autosave_status("Автосохранение: заполните блок 1")
            self.statusBar().showMessage(message, 8000)
            if explicit:
                QMessageBox.warning(self, "Проверьте блок 1", message)
            return False

        if self.transition_scenarios_editor.has_content():
            ok, message = self.transition_scenarios_editor.validate_content()
            if not ok:
                self._set_autosave_status("Автосохранение: заполните блок 2")
                self.statusBar().showMessage(message, 8000)
                if explicit:
                    QMessageBox.warning(self, "Проверьте блок 2", message)
                return False

        if self.deal_scenarios_editor.has_content():
            ok, message = self.deal_scenarios_editor.validate_content()
            if not ok:
                self._set_autosave_status("Автосохранение: заполните блок 3")
                self.statusBar().showMessage(message, 8000)
                if explicit:
                    QMessageBox.warning(self, "Проверьте блок 3", message)
                return False
        return True

    def _refresh_section_statuses(self) -> None:
        if not self._editor_in_structured_mode():
            self.section_current.set_status("RAW")
            self.section_transition.set_status("RAW")
            self.section_deal.set_status("RAW")
            self.validation_status_label.setText("Валидность: RAW")
            return

        current_filled = bool(self.current_situation_editor.to_markdown().strip())
        transition_filled = bool(self.transition_scenarios_editor.to_markdown().strip())
        deal_filled = bool(self.deal_scenarios_editor.to_markdown().strip())

        self.section_current.set_status("Заполнен" if current_filled else "Пусто")
        self.section_transition.set_status("Заполнен" if transition_filled else "Пусто")
        self.section_deal.set_status("Заполнен" if deal_filled else "Пусто")

        v1, _ = self.current_situation_editor.validate_content()
        v2 = True
        if self.transition_scenarios_editor.has_content():
            v2, _ = self.transition_scenarios_editor.validate_content()
        v3 = True
        if self.deal_scenarios_editor.has_content():
            v3, _ = self.deal_scenarios_editor.validate_content()
        self.validation_status_label.setText("Валидность: OK" if (v1 and v2 and v3) else "Валидность: ошибки")

    def _refresh_context_status(self) -> None:
        markdown = self._preview_markdown()
        tf = self._extract_primary_tf(markdown)
        self.tf_status_label.setText(f"TF: {tf or '-'}")

    def _set_autosave_status(self, text: str) -> None:
        self.autosave_status_label.setText(text)

    def _set_saved_now(self) -> None:
        self.last_saved_label.setText(f"Сохранение: {datetime.now().strftime('%H:%M:%S')}")

    def _sync_structured_editors_base_dir(self) -> None:
        if self._editor_in_structured_mode():
            base_dir = self._current_preview_base_dir()
            self.current_situation_editor.set_base_directory(base_dir)
            self.transition_scenarios_editor.set_base_directory(base_dir)
            self.deal_scenarios_editor.set_base_directory(base_dir)

    def _sync_deal_transition_choices(self) -> None:
        if not self._editor_in_structured_mode():
            return
        self.deal_scenarios_editor.set_transition_choices(self.transition_scenarios_editor.scenario_choices())
        self._refresh_section_statuses()
        self._refresh_context_status()

    def _update_file_status_label(self) -> None:
        if self.current_file:
            self.file_status_label.setText(f"Р¤Р°Р№Р»: {self.current_file}")
            return
        if self.current_draft_path:
            self.file_status_label.setText(f"Черновик: {self.current_draft_path}")
            return
        self.file_status_label.setText("Файл: новый документ")

    def _update_editor_tab_caption(self) -> None:
        if self.editor_tabs.count() == 0:
            self.editor_tabs.addTab("Новый план")

        if self.current_file:
            name = self.current_file.name
            tooltip = str(self.current_file)
        elif self.current_draft_path:
            name = self.current_draft_path.name
            tooltip = str(self.current_draft_path)
        else:
            title_source = self.title_edit.text().strip() if hasattr(self, "title_edit") else ""
            name = title_source or "Новый план"
            tooltip = "Новый документ"

        if not self._editor_in_structured_mode():
            name = f"{name} [RAW]"

        if hasattr(self, "autosave") and self.autosave.dirty:
            name = f"{name} *"

        self.editor_tabs.setTabText(0, name)
        self.editor_tabs.setTabToolTip(0, tooltip)

    def _editor_in_structured_mode(self) -> bool:
        return self.editor_stack.currentWidget() is self.structured_page

    def _schedule_preview_refresh(self) -> None:
        return

    def _on_editor_changed(self) -> None:
        if self._updating:
            return
        self.autosave.mark_dirty()
        self._set_autosave_status("Автосохранение: ожидает...")
        self._update_editor_tab_caption()
        self._refresh_section_statuses()
        self._refresh_context_status()
        self._schedule_preview_refresh()

    def _choose_directory(self) -> None:
        if not self._ensure_saved_before_navigation():
            return

        start_dir = str(self.current_directory) if self.current_directory else str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Выберите папку с планами", start_dir)
        if not selected:
            return

        self.current_directory = self._normalize_root_directory(Path(selected))
        self.settings.last_directory = str(self.current_directory)
        self.settings.save()
        self._sync_structured_editors_base_dir()
        self._refresh_file_list()

    def _refresh_file_list(self, show_message: bool = True) -> None:
        self.file_list.clear()

        if not self.current_directory:
            self.folder_label.setText("Папка: не выбрана")
            self.file_cache = []
            return

        plans_dir = self.current_directory / "Plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        self.folder_label.setText(f"Папка: {plans_dir}")
        try:
            self.file_cache = list_markdown_files(plans_dir)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка чтения папки", f"Не удалось прочитать папку:\n{exc}")
            self.file_cache = []

        self._apply_filter()
        if show_message:
            self.statusBar().showMessage("Список файлов обновлён", 3000)

    def _apply_filter(self) -> None:
        self.file_list.clear()
        filter_text = self.search_edit.text().strip().casefold()
        current_path = str(self.current_file) if self.current_file else ""
        selected_index = -1

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
            if current_path and str(info.path) == current_path:
                selected_index = self.file_list.count() - 1

        if shown == 0:
            placeholder = QListWidgetItem("(файлы .md не найдены)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.file_list.addItem(placeholder)
        elif selected_index >= 0:
            self.file_list.setCurrentRow(selected_index)

    def _open_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
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
        root_dir = self._resolve_root_directory_from_plan_path(path)
        self.current_directory = root_dir
        self.settings.last_directory = str(root_dir)
        self.settings.last_open_file = str(path)
        self.settings.touch_recent_file(str(path))
        self.settings.save()
        self._refresh_file_list(show_message=False)

        self._sync_structured_editors_base_dir()
        self._load_plan_into_ui(plan)
        self.autosave.clear_dirty()
        self._set_autosave_status("Автосохранение: ON")
        self.last_saved_label.setText("Сохранение: открыт файл")
        self._update_file_status_label()
        self._update_editor_tab_caption()
        self._refresh_section_statuses()
        self._refresh_context_status()

        if not plan.structured:
            self.statusBar().showMessage("Шаблон не найден: включён режим сырого Markdown", 6000)
        else:
            self.statusBar().showMessage(f"Открыт файл: {path.name}", 3000)

    def _load_plan_into_ui(self, plan: TradingPlan) -> None:
        self._updating = True
        try:
            self.title_edit.setText(plan.title)

            if plan.structured:
                self.editor_stack.setCurrentWidget(self.structured_page)
                self.current_situation_editor.set_base_directory(self._current_preview_base_dir())
                self.transition_scenarios_editor.set_base_directory(self._current_preview_base_dir())
                self.deal_scenarios_editor.set_base_directory(self._current_preview_base_dir())
                self.current_situation_editor.load_from_markdown(plan.block1)
                self.transition_scenarios_editor.load_from_markdown(plan.block2)
                self._sync_deal_transition_choices()
                self.deal_scenarios_editor.load_from_markdown(plan.block3)
                self.raw_editor.setPlainText("")
            else:
                self.editor_stack.setCurrentWidget(self.raw_page)
                self.raw_editor.setPlainText(plan.raw_markdown)
                self.current_situation_editor.load_from_markdown("")
                self.transition_scenarios_editor.load_from_markdown("")
                self.deal_scenarios_editor.set_transition_choices([])
                self.deal_scenarios_editor.load_from_markdown("")
        finally:
            self._updating = False

        self._update_editor_tab_caption()
        self._refresh_section_statuses()
        self._refresh_context_status()
        self._apply_editor_mode(self._editor_mode, emit_change=False)
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
        self.settings.last_open_file = ""
        self.settings.save()

        self._sync_structured_editors_base_dir()
        self._load_plan_into_ui(plan)
        self.autosave.clear_dirty()
        self._set_autosave_status("Автосохранение: ON")
        self.last_saved_label.setText("Сохранение: -")
        self._update_file_status_label()
        self._update_editor_tab_caption()
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
                block1=self.current_situation_editor.to_markdown(),
                block2=self.transition_scenarios_editor.to_markdown(),
                block3=self.deal_scenarios_editor.to_markdown(),
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

    @staticmethod
    def _sanitize_plan_folder_name(name: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip(". ")
        return cleaned or "plan"

    @staticmethod
    def _resolve_root_directory_from_plan_path(path: Path) -> Path:
        current = path.parent
        while True:
            if current.name.casefold() == "plans" and current.parent != current:
                return current.parent
            if current.parent == current:
                break
            current = current.parent
        return path.parent

    def _derive_structured_plan_path(self) -> Path | None:
        if not self._editor_in_structured_mode():
            return None

        root_dir = self.current_directory
        if root_dir is None and self.current_file is not None:
            root_dir = self._resolve_root_directory_from_plan_path(self.current_file)
        if root_dir is None and self.settings.last_directory:
            candidate = Path(self.settings.last_directory)
            if candidate.exists() and candidate.is_dir():
                root_dir = candidate
        if root_dir is None:
            return None

        plan_name = self._sanitize_plan_folder_name(self.title_edit.text().strip() or "plan")
        return root_dir / "Plans" / plan_name / f"{plan_name}.md"

    def _all_image_widgets(self) -> list[object]:
        return [
            *self.current_situation_editor.image_widgets(),
            *self.transition_scenarios_editor.image_widgets(),
            *self.deal_scenarios_editor.image_widgets(),
        ]

    def _remap_image_paths_after_plan_move(self, old_folder: Path, new_folder: Path) -> None:
        old_resolved = old_folder.resolve()
        for widget in self._all_image_widgets():
            raw_path = getattr(widget, "image_path", "")
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                continue
            try:
                relative = candidate.resolve().relative_to(old_resolved)
            except (OSError, ValueError):
                continue
            widget.image_path = str(new_folder / relative)
            widget._update_image_preview()

    def _maybe_rename_plan_structure(self, target_path: Path) -> Path:
        if self.current_file is None or self.current_file == target_path:
            return target_path

        current_path = self.current_file
        if (
            current_path.parent.parent.name.casefold() != "plans"
            or target_path.parent.parent.name.casefold() != "plans"
            or current_path.parent.parent != target_path.parent.parent
        ):
            return target_path

        old_folder = current_path.parent
        new_folder = target_path.parent

        if old_folder != new_folder:
            if old_folder.exists() and not new_folder.exists():
                old_folder.rename(new_folder)
                self._remap_image_paths_after_plan_move(old_folder=old_folder, new_folder=new_folder)
            current_path = new_folder / current_path.name

        if current_path != target_path and current_path.exists() and not target_path.exists():
            current_path.rename(target_path)

        self.current_file = target_path
        return target_path

    @staticmethod
    def _copy_image_to_plan_folder(source: Path, target_dir: Path) -> Path:
        source_path = source.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        candidate = target_dir / source_path.name
        stem = source_path.stem or "image"
        suffix = source_path.suffix

        if candidate.exists():
            try:
                if candidate.resolve() == source_path:
                    return candidate
            except OSError:
                pass

            index = 2
            while True:
                candidate = target_dir / f"{stem}_{index}{suffix}"
                if not candidate.exists():
                    break
                try:
                    if candidate.resolve() == source_path:
                        return candidate
                except OSError:
                    pass
                index += 1

        try:
            if candidate.resolve() == source_path:
                return candidate
        except OSError:
            pass

        shutil.copy2(source_path, candidate)
        return candidate

    def _sync_plan_images_into_directory(self, target_path: Path) -> None:
        if not self._editor_in_structured_mode():
            return

        folder_name = self._sanitize_plan_folder_name(target_path.stem)
        if (
            target_path.parent.parent.name.casefold() == "plans"
            and target_path.parent.name.casefold() == folder_name.casefold()
        ):
            images_dir = target_path.parent
        else:
            images_dir = target_path.parent / "Plans" / folder_name
        images_dir.mkdir(parents=True, exist_ok=True)

        widgets = self._all_image_widgets()
        for widget in widgets:
            source = widget._resolve_image_path()
            if not source.exists() or source.is_dir():
                continue
            copied_path = self._copy_image_to_plan_folder(source, images_dir)
            widget.image_path = str(copied_path)
            widget._update_image_preview()

    def _save_internal(self, explicit: bool, save_as: bool = False, autosave: bool = False) -> bool:
        if not self._validate_image_text_rules(explicit=explicit):
            return False

        target_path: Path | None = None
        if save_as:
            target_path = self._ask_save_path()
            if not target_path:
                return False
        elif explicit and self._editor_in_structured_mode():
            derived_path = self._derive_structured_plan_path()
            if derived_path is not None:
                target_path = derived_path
            elif self.current_file:
                target_path = self.current_file
            else:
                target_path = self._ask_save_path()
                if not target_path:
                    return False
        elif self.current_file:
            target_path = self.current_file
        elif autosave:
            if self._editor_in_structured_mode():
                derived_path = self._derive_structured_plan_path()
                if derived_path is not None:
                    target_path = derived_path
            if target_path is None:
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

        if target_path is None:
            return False

        if (
            explicit
            and self._editor_in_structured_mode()
            and self.current_file is not None
            and target_path != self.current_file
            and target_path.exists()
        ):
            QMessageBox.warning(
                self,
                "Сохранение",
                "План с таким именем уже существует. Выберите другое название плана.",
            )
            return False

        if explicit and self._editor_in_structured_mode():
            try:
                target_path = self._maybe_rename_plan_structure(target_path)
            except OSError as exc:
                self._set_autosave_status("Автосохранение: ошибка переименования")
                self.statusBar().showMessage(f"Ошибка переименования плана: {exc}", 7000)
                QMessageBox.critical(
                    self,
                    "Ошибка переименования плана",
                    f"Не удалось переименовать папку/файл плана:\n{exc}",
                )
                return False

        if self._editor_in_structured_mode():
            try:
                self._sync_plan_images_into_directory(target_path)
            except OSError as exc:
                self._set_autosave_status("Автосохранение: ошибка копирования")
                self.statusBar().showMessage(f"Ошибка копирования изображений: {exc}", 7000)
                if explicit:
                    QMessageBox.critical(
                        self,
                        "Ошибка копирования изображений",
                        f"Не удалось скопировать изображения плана:\n{exc}",
                    )
                return False
            base_dir = target_path.parent if target_path else self._current_preview_base_dir()
            self.current_situation_editor.set_base_directory(base_dir)
            self.transition_scenarios_editor.set_base_directory(base_dir)
            self.deal_scenarios_editor.set_base_directory(base_dir)
        markdown, plan = self._compose_current_markdown()

        if not self._save_to_target(target=target_path, markdown=markdown, explicit=explicit):
            return False

        if plan is not None:
            self.current_plan = plan
        else:
            self.current_plan = TradingPlan.from_markdown(markdown, fallback_title=self.title_edit.text().strip())

        if save_as or explicit:
            self.current_file = target_path
            self.current_draft_path = None
            self.current_directory = self._resolve_root_directory_from_plan_path(target_path)
            self.settings.last_directory = str(self.current_directory)
            self.settings.last_open_file = str(target_path)
            self.settings.touch_recent_file(str(target_path))
            self.settings.save()
            self._sync_structured_editors_base_dir()
            self._refresh_file_list(show_message=False)
        elif autosave and self.current_file is None:
            if self._editor_in_structured_mode() and target_path.suffix.lower() == ".md" and not target_path.name.startswith("_draft_"):
                self.current_file = target_path
                self.current_draft_path = None
                self.current_directory = self._resolve_root_directory_from_plan_path(target_path)
                self.settings.last_directory = str(self.current_directory)
                self.settings.last_open_file = str(target_path)
                self.settings.touch_recent_file(str(target_path))
                self.settings.save()
                self._sync_structured_editors_base_dir()
                self._refresh_file_list(show_message=False)
            else:
                self.current_draft_path = target_path
        elif self.current_file is not None:
            self.settings.last_open_file = str(self.current_file)

        self.autosave.clear_dirty()
        self._set_autosave_status("Автосохранение: ON")
        self._set_saved_now()
        self._update_file_status_label()
        self._update_editor_tab_caption()
        self._refresh_section_statuses()
        self._refresh_context_status()

        if explicit and target_path is not None:
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
        self._refresh_section_statuses()
        self._refresh_context_status()

    @staticmethod
    def _normalize_preview_markdown(markdown: str, hide_comments: bool = True) -> str:
        text = markdown.replace("\r\n", "\n").replace("\r", "\n")
        if hide_comments:
            text = re.sub(r"(?s)<!--.*?-->", "", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def _move_tf_lines_above_images(text: str) -> str:
        previous = text
        for _ in range(3):
            updated = _IMAGE_THEN_TF_RE.sub(lambda match: f"{match.group(2)}\n{match.group(1)}", previous)
            if updated == previous:
                return updated
            previous = updated
        return previous

    @staticmethod
    def _strip_preview_notation_lines(text: str) -> str:
        cleaned = re.sub(r"(?mi)^\s*\*\*Сценарий перехода[^:\n]*:\*\*\s*.*$", "", text)
        cleaned = re.sub(r"(?mi)^\s*Сценарий перехода[^:\n]*:\s*.*$", "", cleaned)
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    @staticmethod
    def _format_bold_label_blocks(body_html: str) -> str:
        pattern = re.compile(r"(?is)<p>\s*<strong>([^<]+?)</strong>\s*(.*?)\s*</p>")

        def _replace(match: re.Match[str]) -> str:
            label = re.sub(r"\s*:+\s*$", "", match.group(1).strip())
            value = re.sub(r"^\s*:\s*", "", match.group(2).strip())
            if not value:
                return f'<div class="kv-block"><div class="kv-label"><strong>{label}</strong></div></div>'
            return (
                '<div class="kv-block">'
                f'<div class="kv-label"><strong>{label}</strong></div>'
                f'<div class="kv-value">{value}</div>'
                "</div>"
            )

        return pattern.sub(_replace, body_html)

    @staticmethod
    def _prepare_inline_code_markdown(text: str) -> str:
        return _INLINE_CODE_RE.sub(lambda match: f"`[{match.group(1)}]`", text)

    def _markdown_to_body_html(self, markdown: str) -> str:
        if not markdown.strip():
            return '<div class="placeholder-block"></div>'

        if markdown_renderer is None:
            return f"<pre>{html.escape(markdown)}</pre>"

        body = markdown_renderer.markdown(markdown, extensions=["fenced_code", "tables", "sane_lists"])
        body = re.sub(r"(?is)<p>\s*(<img[^>]*>)\s*</p>", r"\1", body)
        body = re.sub(
            r"(?is)<p>\s*(<img[^>]*>)\s*(<strong>\s*TF:\s*</strong>\s*[^<]*)\s*</p>",
            r'<div class="kv-block"><div class="kv-label">\2</div></div><p>\1</p>',
            body,
        )
        body = re.sub(
            r"(?is)<p>\s*(<strong>\s*TF:\s*</strong>\s*[^<]*)\s*(<img[^>]*>)\s*</p>",
            r'<div class="kv-block"><div class="kv-label">\1</div></div><p>\2</p>',
            body,
        )
        body = self._format_bold_label_blocks(body)
        body = re.sub(r"(?is)<code>(.*?)</code>", r'<code class="inline-code">\1</code>', body)
        body = re.sub(r'(?is)<pre><code class="inline-code">', "<pre><code>", body)
        return body

    def _extract_situation_blocks(self, block_markdown: str) -> list[SituationPreview]:
        text = block_markdown.strip()
        if not text:
            return []

        matches = list(_SITUATION_H4_RE.finditer(text))
        situations: list[SituationPreview] = []
        if not matches:
            return [SituationPreview(title="Ситуация 1", panels=self._parse_tf_panels(text))]

        for index, match in enumerate(matches, start=1):
            start = match.end()
            end = matches[index].start() if index < len(matches) else len(text)
            title = match.group(1).strip() or f"Ситуация {index}"
            chunk = text[start:end].strip()
            situations.append(SituationPreview(title=title, panels=self._parse_tf_panels(chunk)))
        return situations

    def _parse_tf_panels(self, chunk: str) -> list[TfPanelPreview]:
        text = chunk.strip()
        if not text:
            return [TfPanelPreview(timeframe="", image_path="", notation="", text="")]

        image_matches = list(_IMAGE_MD_RE.finditer(text))
        if not image_matches:
            tf_guess = self._extract_primary_tf(text) or ""
            return [TfPanelPreview(timeframe=tf_guess, image_path="", notation="", text=text)]

        panels: list[TfPanelPreview] = []
        for index, match in enumerate(image_matches):
            start = match.start()
            end = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(text)
            panel_chunk = text[start:end].strip()
            image_path = match.group(1).strip()

            tf_match = _TF_LINE_RE.search(panel_chunk)
            timeframe = tf_match.group(1).strip() if tf_match else ""

            notation_match = _NOTATION_COMMENT_RE.search(panel_chunk)
            notation = notation_match.group(1).strip() if notation_match else ""

            body_text = _IMAGE_MD_RE.sub("", panel_chunk, count=1)
            body_text = re.sub(r"(?mi)^(?:\*\*TF:\*\*|TF:)\s*.+$", "", body_text)
            body_text = _NOTATION_COMMENT_RE.sub("", body_text)
            body_text = re.sub(r"(?mi)^---+\s*$", "", body_text)
            body_text = body_text.strip()

            if not timeframe:
                timeframe = self._extract_primary_tf(f"{notation}\n{body_text}") or ""

            panels.append(
                TfPanelPreview(
                    timeframe=timeframe,
                    image_path=image_path,
                    notation=notation,
                    text=body_text,
                )
            )
        return panels

    def _build_tf_panel_html(self, panel: TfPanelPreview) -> str:
        tf_label = panel.timeframe.strip().upper() if panel.timeframe.strip() else "N/A"
        chunks: list[str] = [
            '<article class="tf-panel">',
            f'<div class="tf-panel-header"><span class="tf-icon">в—·</span><span>TF -> {html.escape(tf_label)}</span></div>',
            '<div class="tf-panel-body">',
        ]

        if panel.image_path:
            image_src = html.escape(panel.image_path, quote=True)
            image_alt = html.escape(Path(panel.image_path).stem or "chart")
            chunks.append(f'<div class="image-block"><img src="{image_src}" alt="{image_alt}"></div>')
        else:
            chunks.append('<div class="placeholder-block"></div>')

        notation_text = panel.notation.strip()
        fixed_text = ""
        if notation_text:
            converted_text, _ = current_situation_notation_to_text(notation_text)
            fixed_text = (converted_text or "").strip()

        user_text = panel.text.strip()
        if fixed_text and user_text and user_text.casefold().startswith(fixed_text.casefold()):
            user_text = user_text[len(fixed_text) :].lstrip(" \t\r\n-:;,.")

        if fixed_text:
            fixed_md = self._prepare_inline_code_markdown(fixed_text)
            fixed_html = self._markdown_to_body_html(fixed_md)
            chunks.append(f'<div class="panel-text panel-fixed">{fixed_html}</div>')

        if user_text:
            user_md = self._prepare_inline_code_markdown(user_text)
            user_html = self._markdown_to_body_html(user_md)
            chunks.append('<div class="panel-label panel-user-label">Текст пользователя</div>')
            chunks.append(f'<div class="panel-text panel-user">{user_html}</div>')

        chunks.append("</div></article>")
        return "".join(chunks)

    def _build_notion_layout_content(self, markdown: str) -> tuple[str, str]:
        plan = TradingPlan.from_markdown(markdown, fallback_title="Trading Plan")
        title = (plan.title.strip() or "Trading Plan").upper()
        sections: list[str] = []

        if plan.structured:
            situations = self._extract_situation_blocks(plan.block1)
            for situation in situations:
                panels_html = "".join(self._build_tf_panel_html(panel) for panel in situation.panels)
                sections.append(
                    '<section class="situation-block">'
                    f"<h2>{html.escape(situation.title)}</h2>"
                    f'<div class="columns-2">{panels_html}</div>'
                    "</section>"
                )

            if plan.block2.strip():
                block2_source = self._strip_preview_notation_lines(plan.block2.strip())
                block2_source = self._move_tf_lines_above_images(block2_source)
                block2_html = self._markdown_to_body_html(self._prepare_inline_code_markdown(block2_source))
                sections.append(
                    '<section class="markdown-card">'
                    "<h2>2. Описание сценариев перехода к сделкам</h2>"
                    f"{block2_html}"
                    "</section>"
                )

            if plan.block3.strip():
                block3_source = self._strip_preview_notation_lines(plan.block3.strip())
                block3_source = self._move_tf_lines_above_images(block3_source)
                block3_html = self._markdown_to_body_html(self._prepare_inline_code_markdown(block3_source))
                sections.append(
                    '<section class="markdown-card">'
                    "<h2>3. Описание сценариев сделок</h2>"
                    f"{block3_html}"
                    "</section>"
                )
            if not sections:
                sections.append('<section class="markdown-card"><div class="placeholder-block"></div></section>')
            return title, "".join(sections)

        fallback_markdown = self._normalize_preview_markdown(markdown, hide_comments=True)
        fallback_markdown = self._strip_preview_notation_lines(fallback_markdown)
        fallback_markdown = self._move_tf_lines_above_images(fallback_markdown)
        fallback_markdown = re.sub(r"(?m)^\s*#\s+.+?\s*$", "", fallback_markdown, count=1).strip()
        fallback_html = self._markdown_to_body_html(self._prepare_inline_code_markdown(fallback_markdown))
        sections.append(f'<section class="markdown-card">{fallback_html}</section>')
        return title, "".join(sections)

    def _render_markdown_to_html(self, markdown: str, mode: str = "markdown") -> str:
        if mode == "notion-layout":
            title, content_html = self._build_notion_layout_content(markdown)
            return (
                "<html><head><style>"
                + build_markdown_css(self._theme_tokens)
                + "</style></head><body>"
                + '<div class="preview-root"><div class="page-container">'
                + f'<div class="page-title-pill">{html.escape(title)}</div>'
                + content_html
                + "</div></div></body></html>"
            )

        normalized = self._normalize_preview_markdown(markdown, hide_comments=True)
        normalized = self._strip_preview_notation_lines(normalized)
        plan = TradingPlan.from_markdown(markdown, fallback_title="Trading Plan")
        title = (plan.title.strip() or "Trading Plan").upper()
        normalized = re.sub(r"(?m)^\s*#\s+.+?\s*$", "", normalized, count=1).strip()
        normalized = self._move_tf_lines_above_images(normalized)
        body = self._markdown_to_body_html(self._prepare_inline_code_markdown(normalized))
        return (
            "<html><head><style>"
            + build_markdown_css(self._theme_tokens)
            + "</style></head><body>"
            + '<div class="preview-root"><div class="page-container">'
            + f'<div class="page-title-pill">{html.escape(title)}</div>'
            + f'<section class="markdown-card">{body}</section>'
            + "</div></div></body></html>"
        )

    def _preview_markdown(self) -> str:
        markdown, _ = self._compose_current_markdown()
        # Hide metadata comments in preview so text appears immediately under media.
        markdown = re.sub(r"(?s)<!--.*?-->", "", markdown)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        return markdown

    def _current_preview_base_dir(self) -> Path | None:
        return self.current_file.parent if self.current_file else self.current_directory

    def _update_preview(self) -> None:
        return

    def _persist_ui_state(self) -> None:
        self.settings.sidebar_visible = self.toggle_sidebar_action.isChecked()
        self.settings.sidebar_width = int(self._sidebar_last_width)
        self.settings.preview_visible = False
        self.settings.last_directory = str(self.current_directory) if self.current_directory else ""
        self.settings.last_open_file = str(self.current_file) if self.current_file else ""
        self.settings.save()

    @staticmethod
    def _extract_primary_tf(markdown: str) -> str | None:
        match = re.search(r"\b(MN1|W1|D1|H4|H1|M30|M15|M5|M1)\b", markdown, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).upper()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._ensure_saved_before_navigation():
            self._persist_ui_state()
            event.accept()
            return
        event.ignore()
