from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import QTimer, QStringListModel, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCompleter,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLayout,
)

from .current_situation import ELEMENT_OPTIONS, TIMEFRAME_OPTIONS

_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
_CREATE_RE = re.compile(
    r"^(CREATE|NOT[\s_]+CREATE)\s+([+-])\s+([A-Za-z0-9]+)\s+(.+)$",
    re.IGNORECASE,
)
_GET_RE = re.compile(
    (
        r"^(GET|NOT[\s_]+GET)\s+([+-])\s+([A-Za-z0-9]+)\s+(.+?)\s+"
        r"(ACTUAL|PREV)\s+([+-])\s+([A-Za-z0-9]+)\s+DR\s+(PREMIUM|DISCOUNT|EQUILIBRIUM)$"
    ),
    re.IGNORECASE,
)
_GET_TAIL_RE = re.compile(
    r"\b(ACTUAL|PREV)\b\s+[+-]\s+[A-Za-z0-9]+\s+DR\s+(PREMIUM|DISCOUNT|EQUILIBRIUM)\s*$",
    re.IGNORECASE,
)
_ACTION_HELP = "CREATE/NOT CREATE [+/- TF Element] или GET/NOT GET [+/- TF Element ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium]"


def _normalize_action(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").strip()).upper()


def _normalize_zone(value: str) -> str:
    zone = value.strip().casefold()
    mapping = {
        "premium": "Premium",
        "discount": "Discount",
        "equilibrium": "Equilibrium",
    }
    return mapping.get(zone, value.strip())


def transition_notation_to_text(notation: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in notation.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, "Нотация должна содержать ровно 1 непустую строку."

    line = lines[0]

    create_match = _CREATE_RE.match(line)
    if create_match:
        action_raw, sign, timeframe, element = create_match.groups()
        if _GET_TAIL_RE.search(element):
            return None, "Для CREATE/NOT CREATE указывается только +/- TF Element без блока ACTUAL/PREV ... DR ..."
        action = _normalize_action(action_raw)
        action_text = "сформировать" if action == "CREATE" else "не сформировать"
        side_text = "бычий" if sign == "+" else "медвежий"
        text = (
            "Для перехода к сделке цена должна "
            f"{action_text} {side_text} {timeframe.upper()} {element.strip()}."
        )
        return text, None

    get_match = _GET_RE.match(line)
    if get_match:
        (
            action_raw,
            sign,
            timeframe,
            element,
            range_kind_raw,
            range_sign,
            range_tf,
            zone_raw,
        ) = get_match.groups()
        action = _normalize_action(action_raw)
        action_text = "получить" if action == "GET" else "не получить"
        side_text = "бычьего" if sign == "+" else "медвежьего"
        range_kind_text = "актуальном" if range_kind_raw.upper() == "ACTUAL" else "предыдущем"
        range_sign_text = "бычьем" if range_sign == "+" else "медвежьем"
        zone = _normalize_zone(zone_raw)
        text = (
            "Для перехода к сделке цена должна "
            f"{action_text} реакцию от {side_text} {timeframe.upper()} {element.strip()}, "
            f"расположенного в {range_kind_text} {range_sign_text} торговом диапазоне на "
            f"{range_tf.upper()} в отметке {zone}."
        )
        return text, None

    return None, f"Формат нотации: {_ACTION_HELP}"


class TransitionNotationEdit(QLineEdit):
    _ACTION_FIRST_OPTIONS = ["CREATE", "GET", "NOT"]
    _ACTION_AFTER_NOT_OPTIONS = ["CREATE", "GET"]
    _RANGE_KIND_OPTIONS = ["ACTUAL", "PREV"]
    _ZONE_OPTIONS = ["Premium", "Discount", "Equilibrium"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("CREATE/NOT CREATE ... или GET/NOT GET ...")
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setWidget(self)
        self._completer.activated.connect(self._insert_completion)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        popup = self._completer.popup()
        if popup.isVisible() and event.key() in (
            Qt.Key.Key_Enter,
            Qt.Key.Key_Return,
            Qt.Key.Key_Escape,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        ):
            event.ignore()
            return

        force_completion = (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Space
        )
        super().keyPressEvent(event)
        if force_completion or event.text() or event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Space):
            self._show_completions(force=force_completion)

    def _insert_completion(self, completion: str) -> None:
        text = self.text()
        cursor_pos = self.cursorPosition()

        start = cursor_pos
        while start > 0 and not text[start - 1].isspace():
            start -= 1

        end = cursor_pos
        while end < len(text) and not text[end].isspace():
            end += 1

        updated = f"{text[:start]}{completion}{text[end:]}"
        self.setText(updated)
        self.setCursorPosition(start + len(completion))

    def _show_completions(self, force: bool) -> None:
        suggestions, prefix = self._completion_context()
        if not suggestions:
            self._completer.popup().hide()
            return

        if prefix:
            suggestions = [item for item in suggestions if item.casefold().startswith(prefix.casefold())]
            if not suggestions:
                self._completer.popup().hide()
                return
        elif not force:
            cursor = self.cursorPosition()
            if cursor > 0 and not self.text()[cursor - 1].isspace():
                return

        self._model.setStringList(suggestions)
        self._completer.setCompletionPrefix(prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(320, popup.sizeHintForColumn(0) + 24))
        self._completer.complete(rect)

    def _completion_context(self) -> tuple[list[str], str]:
        before = self.text()[: self.cursorPosition()]
        tokens = re.split(r"\s+", before.strip()) if before.strip() else []

        if before and not before.endswith((" ", "\t")):
            prefix = tokens[-1] if tokens else ""
            token_index = len(tokens) - 1
        else:
            prefix = ""
            token_index = len(tokens)

        if token_index <= 0:
            return self._ACTION_FIRST_OPTIONS, prefix

        first = tokens[0].upper() if tokens else ""
        if first == "NOT":
            if token_index == 1:
                return self._ACTION_AFTER_NOT_OPTIONS, prefix
            action_kind = tokens[1].upper() if len(tokens) > 1 else ""
            if action_kind not in ("CREATE", "GET"):
                return self._ACTION_AFTER_NOT_OPTIONS, prefix
            action_offset = 2
            action = "GET" if action_kind == "GET" else "CREATE"
        elif first in ("CREATE", "GET"):
            action_offset = 1
            action = first
        else:
            return self._ACTION_FIRST_OPTIONS, prefix

        if token_index == action_offset:
            return ["+", "-"], prefix
        if token_index == action_offset + 1:
            return TIMEFRAME_OPTIONS, prefix

        if action == "CREATE":
            return ELEMENT_OPTIONS, prefix

        after_header = tokens[action_offset + 2 :] if len(tokens) > action_offset + 2 else []
        range_kind_index = next(
            (idx for idx, value in enumerate(after_header) if value.upper() in ("ACTUAL", "PREV")),
            None,
        )
        if range_kind_index is None:
            if not after_header:
                return ELEMENT_OPTIONS, prefix
            if prefix and any(option.startswith(prefix.upper()) for option in self._RANGE_KIND_OPTIONS):
                return self._RANGE_KIND_OPTIONS, prefix
            if before.endswith(" "):
                return self._RANGE_KIND_OPTIONS, prefix
            return ELEMENT_OPTIONS, prefix

        absolute_range_index = action_offset + 2 + range_kind_index
        relative_index = token_index - absolute_range_index
        if relative_index <= 0:
            return self._RANGE_KIND_OPTIONS, prefix
        if relative_index == 1:
            return ["+", "-"], prefix
        if relative_index == 2:
            return TIMEFRAME_OPTIONS, prefix
        if relative_index == 3:
            return ["DR"], prefix
        if relative_index == 4:
            return self._ZONE_OPTIONS, prefix

        return [], prefix

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        text = " ".join(self.text().replace("\n", " ").split())
        if text != self.text():
            self.setText(text)
        super().focusOutEvent(event)


@dataclass(slots=True)
class TransitionScenarioData:
    image_path: str
    notation: str = ""
    text: str = ""


class TransitionScenarioWidget(QFrame):
    changed = Signal()
    remove_requested = Signal(QWidget)

    def __init__(self, data: TransitionScenarioData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("transitionScenarioCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._base_dir: Path | None = None
        self._last_generated = ""
        self._updating_manual = False
        self._source_pixmap = QPixmap()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        header = QHBoxLayout()
        self.title_label = QLabel("Сценарий")
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

        root.addWidget(QLabel("Нотация *"))
        self.notation_edit = TransitionNotationEdit()
        root.addWidget(self.notation_edit)

        self.notation_status = QLabel("")
        root.addWidget(self.notation_status)

        root.addWidget(QLabel("Текст под картинкой (ручное редактирование) *"))
        self.manual_edit = QPlainTextEdit()
        self.manual_edit.setPlaceholderText("Описание сценария перехода")
        self.manual_edit.setMinimumHeight(110)
        self.manual_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.manual_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.manual_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.manual_edit)

        self.image_path = data.image_path
        self.path_label.setText(data.image_path)
        self.notation_edit.setText(data.notation)
        self.manual_edit.setPlainText(data.text)

        self._on_notation_changed()
        self._update_image_preview()

        self.notation_edit.textChanged.connect(self._on_notation_changed)
        self.manual_edit.textChanged.connect(self._on_manual_changed)
        manual_layout = self.manual_edit.document().documentLayout()
        if manual_layout is not None:
            manual_layout.documentSizeChanged.connect(self._update_manual_edit_height)
        QTimer.singleShot(0, self._update_manual_edit_height)

    def set_index(self, index: int) -> None:
        self.title_label.setText(f"Сценарий #{index}")

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self._update_image_preview()

    def to_data(self) -> TransitionScenarioData:
        return TransitionScenarioData(
            image_path=self.image_path,
            notation=self.notation_edit.text().strip(),
            text=self.manual_edit.toPlainText().strip(),
        )

    def validate(self) -> tuple[bool, str]:
        if not self.image_path.strip():
            return False, "Не выбрана картинка."

        notation_text = self.notation_edit.text().strip()
        generated, notation_error = transition_notation_to_text(notation_text)
        if notation_error:
            return False, notation_error

        if not generated:
            return False, "Нотация не заполнена."

        if not self.manual_edit.toPlainText().strip():
            return False, "Заполните текст под картинкой."

        return True, ""

    def to_markdown(self, index: int, base_dir: Path | None) -> str:
        data = self.to_data()
        image_markdown_path = self._to_markdown_path(Path(data.image_path), base_dir)
        alt_text = Path(image_markdown_path).stem or f"transition_{index}"

        parts = [
            f"#### Сценарий {index}",
            f"![{alt_text}]({image_markdown_path})",
            "",
            "<!-- TRANSITION_NOTATION",
            data.notation.strip(),
            "-->",
            "",
            data.text,
        ]
        return "\n".join(parts).strip()

    def _on_notation_changed(self) -> None:
        notation_text = self.notation_edit.text().strip()
        generated, error = transition_notation_to_text(notation_text)
        if error:
            self.notation_status.setText(f"Подсказка: {error}")
            self.notation_status.setStyleSheet("color: #9a6b00;")
            self.changed.emit()
            return

        self.notation_status.setText(f"Результат: {generated}")
        self.notation_status.setStyleSheet("color: #1f6f43;")

        manual = self.manual_edit.toPlainText().strip()
        if not manual or manual == self._last_generated:
            self._updating_manual = True
            self.manual_edit.setPlainText(generated or "")
            self._updating_manual = False

        self._last_generated = generated or ""
        self._update_manual_edit_height()
        self.changed.emit()

    def _on_manual_changed(self) -> None:
        if self._updating_manual:
            return
        self._update_manual_edit_height()
        self.changed.emit()

    def _update_manual_edit_height(self, *_args) -> None:
        document_layout = self.manual_edit.document().documentLayout()
        if document_layout is None:
            return
        content_height = int(document_layout.documentSize().height())
        margins = self.manual_edit.contentsMargins()
        target_height = max(
            110,
            content_height + (self.manual_edit.frameWidth() * 2) + margins.top() + margins.bottom() + 12,
        )
        if self.manual_edit.height() != target_height:
            self.manual_edit.setFixedHeight(target_height)

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


class TransitionScenariosEditor(QWidget):
    content_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._base_dir: Path | None = None
        self._entries: list[TransitionScenarioWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        top_row = QHBoxLayout()
        self.add_image_button = QPushButton("Добавить сценарий")
        self.add_image_button.clicked.connect(self._on_add_image_clicked)
        top_row.addWidget(self.add_image_button)
        top_row.addStretch(1)
        root.addLayout(top_row)

        self.empty_label = QLabel("Добавьте минимум один сценарий перехода к сделке.")
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

    def scenario_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        for index, entry in enumerate(self._entries, start=1):
            data = entry.to_data()
            reference = data.notation.strip() or f"Сценарий #{index}"
            preview_source = data.notation.strip() or data.text.strip()
            preview = re.sub(r"\s+", " ", preview_source).strip()
            if len(preview) > 90:
                preview = f"{preview[:87]}..."
            label = f"Сценарий #{index}: {preview}" if preview else f"Сценарий #{index}"
            choices.append((reference, label))
        return choices

    def validate_content(self) -> tuple[bool, str]:
        if not self._entries:
            return False, "В разделе сценариев перехода нужен минимум один сценарий."

        for index, entry in enumerate(self._entries, start=1):
            ok, error = entry.validate()
            if ok:
                continue
            return False, f"Сценарий #{index}: {error}"
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

        self._add_entry_widget(TransitionScenarioData(image_path=image_file))
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _add_entry_widget(self, data: TransitionScenarioData) -> None:
        entry = TransitionScenarioWidget(data, self)
        entry.set_base_dir(self._base_dir)
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
    def _parse_entries(markdown: str) -> list[TransitionScenarioData]:
        text = markdown.strip()
        if not text:
            return []

        image_matches = list(_IMAGE_RE.finditer(text))
        if not image_matches:
            return []

        entries: list[TransitionScenarioData] = []
        for index, match in enumerate(image_matches):
            start = match.start()
            end = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(text)
            chunk = text[start:end].strip()

            image_path = match.group(1).strip()

            notation_match = re.search(r"(?is)<!--\s*TRANSITION_NOTATION\s*(.*?)\s*-->", chunk)
            notation = notation_match.group(1).strip() if notation_match else ""
            if not notation:
                notation_match = re.search(r"(?is)Notation:\s*\n(.*?)(?:\n\s*Text:|\Z)", chunk)
                notation = notation_match.group(1).strip() if notation_match else ""

            manual_text = ""
            if notation_match:
                manual_text = chunk[notation_match.end() :].strip()
            if not manual_text:
                text_match = re.search(r"(?is)Text:\s*\n(.*)$", chunk)
                manual_text = text_match.group(1).strip() if text_match else ""

            if not manual_text:
                body_after_image = chunk[match.end() - start :].strip()
                body_after_image = re.sub(r"(?is)<!--\s*TRANSITION_NOTATION\s*.*?-->", "", body_after_image).strip()
                body_after_image = re.sub(r"(?is)Notation:\s*\n.*$", "", body_after_image).strip()
                manual_text = body_after_image.strip()

            entries.append(
                TransitionScenarioData(
                    image_path=image_path,
                    notation=notation,
                    text=manual_text,
                )
            )

        return entries
