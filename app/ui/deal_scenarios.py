from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLayout,
)

_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
_TRANSITION_REF_RE = re.compile(r"(?mi)^\*\*Сценарий перехода:\*\*\s*(.+?)\s*$")
_FIELD_DEFINITIONS: list[tuple[str, str]] = [
    ("idea", "Идея сделки"),
    ("entry", "Entry: почему именно так? Можно ли выгоднее? Обосновать"),
    ("sl", "SL: Почему именно так? Что он отменяет? Обосновать"),
    ("tp", "TP: Почему именно так? Это оптимальная цель? Обосновать"),
]


def _extract_fields_by_headers(chunk: str) -> dict[str, str]:
    matches: list[tuple[int, int, str]] = []
    for key, header in _FIELD_DEFINITIONS:
        pattern = re.compile(rf"(?mi)^\*\*{re.escape(header)}\*\*\s*$")
        match = pattern.search(chunk)
        if not match:
            continue
        matches.append((match.start(), match.end(), key))

    if not matches:
        return {key: "" for key, _ in _FIELD_DEFINITIONS}

    matches.sort(key=lambda item: item[0])
    values: dict[str, str] = {key: "" for key, _ in _FIELD_DEFINITIONS}
    for index, (_start, body_start, key) in enumerate(matches):
        body_end = matches[index + 1][0] if index + 1 < len(matches) else len(chunk)
        values[key] = chunk[body_start:body_end].strip()
    return values


class AutoHeightPlainTextEdit(QPlainTextEdit):
    def __init__(self, min_height: int = 110, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min_height = min_height
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self._update_height)
        document_layout = self.document().documentLayout()
        if document_layout is not None:
            document_layout.documentSizeChanged.connect(self._update_height)
        QTimer.singleShot(0, self._update_height)

    def _update_height(self, *_args) -> None:
        document_layout = self.document().documentLayout()
        if document_layout is None:
            return
        content_height = int(document_layout.documentSize().height())
        margins = self.contentsMargins()
        target_height = max(
            self._min_height,
            content_height + (self.frameWidth() * 2) + margins.top() + margins.bottom() + 12,
        )
        if self.height() != target_height:
            self.setFixedHeight(target_height)


@dataclass(slots=True)
class DealScenarioData:
    image_path: str
    transition_ref: str = ""
    idea: str = ""
    entry: str = ""
    sl: str = ""
    tp: str = ""


class DealScenarioWidget(QFrame):
    changed = Signal()
    remove_requested = Signal(QWidget)

    def __init__(self, data: DealScenarioData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("dealScenarioCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._base_dir: Path | None = None
        self._source_pixmap = QPixmap()
        self._transition_ref = data.transition_ref.strip()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        header = QHBoxLayout()
        self.title_label = QLabel("Сделка")
        header.addWidget(self.title_label)
        header.addStretch(1)
        remove_button = QPushButton("Удалить")
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(remove_button)
        root.addLayout(header)

        self.image_frame = QFrame()
        self.image_frame.setFixedHeight(220)
        self.image_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.image_frame.setStyleSheet("QFrame { border: 1px solid #d8dde6; border-radius: 6px; background: #fafbfd; }")
        image_layout = QVBoxLayout(self.image_frame)
        image_layout.setContentsMargins(2, 2, 2, 2)
        image_layout.setSpacing(0)

        self.image_label = QLabel("Изображение не найдено")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        image_layout.addWidget(self.image_label)
        root.addWidget(self.image_frame)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.path_label)

        transition_row = QHBoxLayout()
        transition_row.addWidget(QLabel("Сценарий перехода *"))
        self.transition_combo = QComboBox()
        self.transition_combo.addItem("Выберите сценарий перехода", "")
        transition_row.addWidget(self.transition_combo, 1)
        root.addLayout(transition_row)

        helper = QLabel("Мой текст с пояснениями:")
        helper.setStyleSheet("color: #596579;")
        root.addWidget(helper)

        self.idea_edit = AutoHeightPlainTextEdit(parent=self)
        self.entry_edit = AutoHeightPlainTextEdit(parent=self)
        self.sl_edit = AutoHeightPlainTextEdit(parent=self)
        self.tp_edit = AutoHeightPlainTextEdit(parent=self)

        self._add_text_field(root, "Идея сделки", self.idea_edit)
        self._add_text_field(root, "Entry: почему именно так? Можно ли выгоднее? Обосновать", self.entry_edit)
        self._add_text_field(root, "SL: Почему именно так? Что он отменяет? Обосновать", self.sl_edit)
        self._add_text_field(root, "TP: Почему именно так? Это оптимальная цель? Обосновать", self.tp_edit)

        self.image_path = data.image_path
        self.path_label.setText(data.image_path)
        self.idea_edit.setPlainText(data.idea)
        self.entry_edit.setPlainText(data.entry)
        self.sl_edit.setPlainText(data.sl)
        self.tp_edit.setPlainText(data.tp)
        self.set_transition_choices([])

        self._update_image_preview()

        self.transition_combo.currentIndexChanged.connect(self._on_transition_changed)
        self.idea_edit.textChanged.connect(self.changed)
        self.entry_edit.textChanged.connect(self.changed)
        self.sl_edit.textChanged.connect(self.changed)
        self.tp_edit.textChanged.connect(self.changed)

    @staticmethod
    def _add_text_field(layout: QVBoxLayout, label_text: str, editor: QPlainTextEdit) -> None:
        layout.addWidget(QLabel(label_text))
        layout.addWidget(editor)

    def set_index(self, index: int) -> None:
        self.title_label.setText(f"Сделка #{index}")

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self._update_image_preview()

    def set_transition_choices(self, choices: list[tuple[str, str]]) -> None:
        previous_ref = self._transition_ref or (self.transition_combo.currentData() or "")
        self.transition_combo.blockSignals(True)
        self.transition_combo.clear()
        self.transition_combo.addItem("Выберите сценарий перехода", "")
        for reference, label in choices:
            self.transition_combo.addItem(label, reference)

        if previous_ref:
            index = self.transition_combo.findData(previous_ref)
            if index < 0:
                self.transition_combo.addItem(f"(Не найдено) {previous_ref}", previous_ref)
                index = self.transition_combo.count() - 1
            self.transition_combo.setCurrentIndex(index)
        else:
            self.transition_combo.setCurrentIndex(0)
        self.transition_combo.blockSignals(False)

    def to_data(self) -> DealScenarioData:
        transition_ref = self.transition_combo.currentData() or self._transition_ref
        return DealScenarioData(
            image_path=self.image_path,
            transition_ref=(transition_ref or "").strip(),
            idea=self.idea_edit.toPlainText().strip(),
            entry=self.entry_edit.toPlainText().strip(),
            sl=self.sl_edit.toPlainText().strip(),
            tp=self.tp_edit.toPlainText().strip(),
        )

    def validate(self) -> tuple[bool, str]:
        data = self.to_data()
        if not data.image_path.strip():
            return False, "Не выбрана картинка."
        if not data.transition_ref.strip():
            return False, "Выберите сценарий перехода."
        if not data.idea.strip():
            return False, "Заполните поле 'Идея сделки'."
        if not data.entry.strip():
            return False, "Заполните поле 'Entry'."
        if not data.sl.strip():
            return False, "Заполните поле 'SL'."
        if not data.tp.strip():
            return False, "Заполните поле 'TP'."
        return True, ""

    def to_markdown(self, index: int, base_dir: Path | None) -> str:
        data = self.to_data()
        image_markdown_path = self._to_markdown_path(Path(data.image_path), base_dir)
        alt_text = Path(image_markdown_path).stem or f"deal_{index}"

        parts = [
            f"#### Сделка {index}",
            f"![{alt_text}]({image_markdown_path})",
            f"**Сценарий перехода:** {data.transition_ref}",
            "",
            f"**{_FIELD_DEFINITIONS[0][1]}**",
            data.idea,
            "",
            f"**{_FIELD_DEFINITIONS[1][1]}**",
            data.entry,
            "",
            f"**{_FIELD_DEFINITIONS[2][1]}**",
            data.sl,
            "",
            f"**{_FIELD_DEFINITIONS[3][1]}**",
            data.tp,
        ]
        return "\n".join(parts).strip()

    def _on_transition_changed(self, _index: int) -> None:
        self._transition_ref = (self.transition_combo.currentData() or "").strip()
        self.changed.emit()

    def _resolve_image_path(self) -> Path:
        candidate = Path(self.image_path)
        if candidate.is_absolute():
            return candidate
        if self._base_dir:
            return self._base_dir / candidate
        return candidate

    def _update_image_preview(self) -> None:
        resolved = self._resolve_image_path()
        if not resolved.exists():
            self._source_pixmap = QPixmap()
            self.image_label.setText("Изображение не найдено")
            self.image_label.setPixmap(QPixmap())
            return

        source = QPixmap(str(resolved))
        if source.isNull():
            self._source_pixmap = QPixmap()
            self.image_label.setText("Не удалось загрузить изображение")
            self.image_label.setPixmap(QPixmap())
            return

        self._source_pixmap = source
        self._render_image_preview()

    def _render_image_preview(self) -> None:
        if self._source_pixmap.isNull():
            return

        target_width = self.image_label.width() if self.image_label.width() > 16 else 640
        target_height = self.image_label.height() if self.image_label.height() > 16 else 216
        scaled = self._source_pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setText("")
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._render_image_preview()

    @staticmethod
    def _to_markdown_path(path: Path, base_dir: Path | None) -> str:
        if path.is_absolute() and base_dir:
            try:
                return path.relative_to(base_dir).as_posix()
            except ValueError:
                return path.as_posix()
        return path.as_posix()


class DealScenariosEditor(QWidget):
    content_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._base_dir: Path | None = None
        self._transition_choices: list[tuple[str, str]] = []
        self._entries: list[DealScenarioWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        top_row = QHBoxLayout()
        self.add_image_button = QPushButton("Добавить сделку")
        self.add_image_button.clicked.connect(self._on_add_image_clicked)
        top_row.addWidget(self.add_image_button)
        top_row.addStretch(1)
        root.addLayout(top_row)

        self.empty_label = QLabel("Добавьте минимум одну сделку и заполните идею, Entry, SL, TP.")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.entries_container = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_container)
        self.entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entries_layout.setSpacing(10)
        self.entries_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.entries_layout.addStretch(1)
        self.entries_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root.addWidget(self.entries_container)

        self._update_empty_state()

    def set_base_directory(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        for entry in self._entries:
            entry.set_base_dir(base_dir)

    def set_transition_choices(self, choices: list[tuple[str, str]]) -> None:
        self._transition_choices = choices
        for entry in self._entries:
            entry.set_transition_choices(choices)

    def load_from_markdown(self, markdown: str) -> None:
        self._clear_entries()
        for data in self._parse_entries(markdown):
            self._add_entry_widget(data)
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def to_markdown(self) -> str:
        chunks = [entry.to_markdown(index + 1, self._base_dir) for index, entry in enumerate(self._entries)]
        return "\n\n---\n\n".join(chunks).strip()

    def validate_content(self) -> tuple[bool, str]:
        if not self._entries:
            return False, "В разделе сценариев сделок нужна минимум одна сделка."

        for index, entry in enumerate(self._entries, start=1):
            ok, error = entry.validate()
            if ok:
                continue
            return False, f"Сделка #{index}: {error}"
        return True, ""

    def _on_add_image_clicked(self) -> None:
        start_dir = str(self._base_dir) if self._base_dir else str(Path.home())
        image_file, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите картинку",
            start_dir,
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.svg)",
        )
        if not image_file:
            return

        self._add_entry_widget(DealScenarioData(image_path=image_file))
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _add_entry_widget(self, data: DealScenarioData) -> None:
        entry = DealScenarioWidget(data, self)
        entry.set_base_dir(self._base_dir)
        entry.set_transition_choices(self._transition_choices)
        entry.changed.connect(self.content_changed)
        entry.remove_requested.connect(self._remove_entry_widget)

        self.entries_layout.insertWidget(max(0, self.entries_layout.count() - 1), entry)
        self._entries.append(entry)

    def _remove_entry_widget(self, widget: QWidget) -> None:
        if widget in self._entries:
            self._entries.remove(widget)
        widget.setParent(None)
        widget.deleteLater()
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _clear_entries(self) -> None:
        while self._entries:
            widget = self._entries.pop()
            widget.setParent(None)
            widget.deleteLater()

    def _update_entry_titles(self) -> None:
        for index, entry in enumerate(self._entries, start=1):
            entry.set_index(index)

    def _update_empty_state(self) -> None:
        is_empty = len(self._entries) == 0
        self.empty_label.setVisible(is_empty)
        self.entries_container.setVisible(not is_empty)

    @staticmethod
    def _parse_entries(markdown: str) -> list[DealScenarioData]:
        text = markdown.strip()
        if not text:
            return []

        image_matches = list(_IMAGE_RE.finditer(text))
        if not image_matches:
            return [
                DealScenarioData(
                    image_path="",
                    transition_ref="",
                    idea=text,
                    entry="",
                    sl="",
                    tp="",
                )
            ]

        entries: list[DealScenarioData] = []
        for index, match in enumerate(image_matches):
            start = match.start()
            end = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(text)
            chunk = text[start:end].strip()

            image_path = match.group(1).strip()
            transition_match = _TRANSITION_REF_RE.search(chunk)
            transition_ref = transition_match.group(1).strip() if transition_match else ""
            fields = _extract_fields_by_headers(chunk)
            if all(not value for value in fields.values()):
                body_after_image = chunk[match.end() - start :].strip()
                body_after_image = re.sub(
                    r"(?mi)^\*\*Сценарий перехода:\*\*.*$",
                    "",
                    body_after_image,
                ).strip()
                fields["idea"] = body_after_image

            entries.append(
                DealScenarioData(
                    image_path=image_path,
                    transition_ref=transition_ref,
                    idea=fields["idea"],
                    entry=fields["entry"],
                    sl=fields["sl"],
                    tp=fields["tp"],
                )
            )

        return entries
