from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import QTimer, QStringListModel, Qt, Signal
from PySide6.QtGui import QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QSizePolicy,
    QLayout,
    QVBoxLayout,
    QWidget,
)

from .image_clipboard import image_path_from_clipboard

TIMEFRAME_OPTIONS = ["m1", "m5", "m15", "h1", "h4", "D1", "W1", "M1"]
ELEMENT_OPTIONS = [
    "RB",
    "FVG",
    "SNR",
    "FL",
    "FH",
]
ZONE_OPTIONS = ["Premium", "Equilibrium", "Discount"]

_LINE_1_IN_RE = re.compile(r"^IN\s+([+-])\s+([A-Za-z0-9]+)\s+([A-Za-z][A-Za-z0-9_-]*)$", re.IGNORECASE)
_LINE_1_RANGE_ONE_RE = re.compile(
    r"^RANGE\s+([+-])\s+([A-Za-z0-9]+)\s+([A-Za-z][A-Za-z0-9_-]*)\s+(UP|DOWN)$",
    re.IGNORECASE,
)
_LINE_1_RANGE_TWO_RE = re.compile(
    r"^RANGE\s+([+-])\s+([A-Za-z0-9]+)\s+([A-Za-z][A-Za-z0-9_-]*)\s+([+-])\s+([A-Za-z0-9]+)\s+([A-Za-z][A-Za-z0-9_-]*)$",
    re.IGNORECASE,
)
_RANGE_CLAUSE_RE = re.compile(
    r"^(Actual|Prev)\s+([+-])\s+([A-Za-z0-9]+)\s+(?:DR\s+)?(Premium|Equilibrium|Discount)$",
    re.IGNORECASE,
)
_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
_NOTATION_COMMENT_RE = re.compile(r"(?is)<!--\s*NOTATION\s*(.*?)\s*-->")


def notation_to_text(notation: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in notation.splitlines() if line.strip()]
    if len(lines) != 2:
        return None, "Нотация должна содержать ровно 2 непустые строки."

    def actual_prev_text(value: str) -> str:
        return "актуального" if value.upper() == "ACTUAL" else "предыдущего"

    def element_text(sign: str, timeframe: str, element: str) -> str:
        return f"[{sign}{timeframe.upper()} {element}]"

    def dr_text(sign: str, timeframe: str) -> str:
        return f"[{sign}{timeframe.upper()} DR]"

    def normalize_zone(value: str) -> str:
        lookup = {"premium": "Premium", "equilibrium": "Equilibrium", "discount": "Discount"}
        return lookup.get(value.casefold(), value)

    def parse_range_clause(clause_text: str) -> tuple[tuple[str, str, str, str] | None, str | None]:
        match = _RANGE_CLAUSE_RE.match(clause_text.strip())
        if not match:
            return None, "Формат диапазона: Actual/Prev +/- TF DR Premium/Equilibrium/Discount"
        actual_prev, direction_sign, timeframe, zone = match.groups()
        return (
            actual_prev.upper(),
            direction_sign,
            timeframe.upper(),
            normalize_zone(zone),
        ), None

    line_1 = lines[0]
    line_2 = lines[1]

    in_match = _LINE_1_IN_RE.match(line_1)
    if in_match:
        sign_1, tf_1, element = in_match.groups()
        clause_data, clause_error = parse_range_clause(line_2)
        if clause_error:
            return None, "2 строка: Actual/Prev +/- TF DR Premium/Equilibrium/Discount"
        assert clause_data is not None
        actual_prev, sign_2, tf_2, zone = clause_data
        range_desc = dr_text(sign_2, tf_2)
        text = (
            f"Цена находится внутри {element_text(sign_1, tf_1, element)}. "
            f"Данный {element} находится в отметках {zone} {actual_prev_text(actual_prev)} "
            f"{range_desc}."
        )
        return text, None

    range_two_match = _LINE_1_RANGE_TWO_RE.match(line_1)
    if range_two_match:
        sign_1, tf_1, element_1, sign_2, tf_2, element_2 = range_two_match.groups()
        first_element_desc = element_text(sign_1, tf_1, element_1)
        parts = [part.strip() for part in re.split(r"\s*[|;]\s*", line_2) if part.strip()]
        if len(parts) != 2:
            return None, "2 строка для RANGE с 2 элементами: <диапазон 1> | <диапазон 2>"

        clause_1, error_1 = parse_range_clause(parts[0])
        clause_2, error_2 = parse_range_clause(parts[1])
        if error_1 or error_2:
            return None, "2 строка для RANGE: Actual/Prev +/- TF DR Premium/Equilibrium/Discount | Actual/Prev +/- TF DR Premium/Equilibrium/Discount"
        assert clause_1 is not None and clause_2 is not None

        range_1_text = f"{clause_1[3]} {actual_prev_text(clause_1[0])} {dr_text(clause_1[1], clause_1[2])}"
        range_2_text = f"{clause_2[3]} {actual_prev_text(clause_2[0])} {dr_text(clause_2[1], clause_2[2])}"
        second_element_desc = element_text(sign_2, tf_2, element_2)
        text = (
            f"Цена находится в диапазоне между {first_element_desc}, расположенного в отметках {range_1_text}, "
            f"и {second_element_desc}, расположенного в отметках {range_2_text}."
        )
        return text, None

    range_one_match = _LINE_1_RANGE_ONE_RE.match(line_1)
    if not range_one_match:
        return None, "1 строка: IN +/- TF Element или RANGE +/- TF Element (UP/DOWN или +/- TF Element)"

    sign_1, tf_1, element_1, direction = range_one_match.groups()
    clause_data, clause_error = parse_range_clause(line_2)
    if clause_error:
        return None, "2 строка для RANGE с 1 элементом: Actual/Prev +/- TF DR Premium/Equilibrium/Discount"
    assert clause_data is not None

    ath_or_atl = "ATH" if direction.upper() == "UP" else "ATL"
    range_text = f"{clause_data[3]} {actual_prev_text(clause_data[0])} {dr_text(clause_data[1], clause_data[2])}"
    text = (
        f"Цена устанавливает {ath_or_atl}. "
        f"Ближайшая опорная область - {element_text(sign_1, tf_1, element_1)}, расположенный в отметках {range_text}."
    )
    return text, None


class NotationTextEdit(QPlainTextEdit):
    _ELEMENT_OPTIONS_NORMALIZED = {re.sub(r"\s+", " ", item).casefold() for item in ELEMENT_OPTIONS}
    _TIMEFRAME_OPTIONS_NORMALIZED = {item.upper() for item in TIMEFRAME_OPTIONS}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setWidget(self)
        self._completer.activated.connect(self._insert_completion)
        self.setPlaceholderText(
            "1 строка: IN +/- TF Element или RANGE +/- TF Element (UP/DOWN или +/- TF Element)\n"
            "2 строка: Actual/Prev +/- TF DR Premium/Equilibrium/Discount"
        )
        self.setMaximumHeight(84)

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

        force_completion = event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Space
        super().keyPressEvent(event)
        self._maybe_move_to_second_line()
        self._maybe_autofill_dr_token()
        if force_completion or event.text() or event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Space):
            self._show_completions(force=force_completion)

    def focusInEvent(self, event) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        QTimer.singleShot(0, lambda: self._show_completions(force=True))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        super().mousePressEvent(event)
        QTimer.singleShot(0, lambda: self._show_completions(force=True))

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        line_text = cursor.block().text()
        position_in_block = cursor.positionInBlock()

        start = position_in_block
        while start > 0 and not line_text[start - 1].isspace():
            start -= 1

        end = position_in_block
        while end < len(line_text) and not line_text[end].isspace():
            end += 1

        cursor.setPosition(cursor.position() - (position_in_block - start), QTextCursor.MoveMode.MoveAnchor)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
            end - start,
        )
        insert_text = completion
        if end >= len(line_text) or not line_text[end].isspace():
            insert_text += " "
        cursor.insertText(insert_text)
        self.setTextCursor(cursor)
        self._maybe_move_to_second_line()
        self._maybe_autofill_dr_token()

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
            cursor = self.textCursor()
            if cursor.positionInBlock() > 0 and not cursor.block().text()[cursor.positionInBlock() - 1].isspace():
                return

        self._model.setStringList(suggestions)
        self._completer.setCompletionPrefix(prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(260, popup.sizeHintForColumn(0) + 24))
        self._completer.complete(rect)

    def _completion_context(self) -> tuple[list[str], str]:
        cursor = self.textCursor()
        line_number = cursor.blockNumber()
        before = cursor.block().text()[: cursor.positionInBlock()]
        token_source = re.sub(r"([|;])", r" \1 ", before)

        if token_source and not token_source.endswith((" ", "\t")):
            prefix = re.split(r"\s+", token_source)[-1]
            token_index = len(re.split(r"\s+", token_source.strip())) - 1
        else:
            prefix = ""
            token_index = len(re.split(r"\s+", token_source.strip())) if token_source.strip() else 0

        if line_number == 0:
            first_line_tokens = re.split(r"\s+", before.strip()) if before.strip() else []
            if token_index <= 0:
                return ["IN", "RANGE"], prefix

            head = first_line_tokens[0].upper() if first_line_tokens else ""
            if head == "IN":
                if token_index == 1:
                    return ["+", "-"], prefix
                if token_index == 2:
                    return TIMEFRAME_OPTIONS, prefix
                if token_index == 3:
                    return ELEMENT_OPTIONS, prefix
                return [], prefix

            if head == "RANGE":
                if token_index == 1:
                    return ["+", "-"], prefix
                if token_index == 2:
                    return TIMEFRAME_OPTIONS, prefix
                if token_index == 3:
                    return ELEMENT_OPTIONS, prefix
                if token_index == 4:
                    return ["UP", "DOWN", "+", "-"], prefix
                if token_index == 5:
                    return TIMEFRAME_OPTIONS, prefix
                if token_index == 6:
                    return ELEMENT_OPTIONS, prefix
                return [], prefix

            return ["IN", "RANGE"], prefix

        if line_number == 1:
            mode, range_elements = self._current_mode_and_element_count()
            if token_index <= 0:
                return ["Actual", "Prev"], prefix
            if token_index == 1:
                return ["+", "-"], prefix
            if token_index == 2:
                return TIMEFRAME_OPTIONS, prefix
            if token_index == 3:
                return ["DR"], prefix
            if token_index == 4:
                return ZONE_OPTIONS, prefix
            if mode == "RANGE" and range_elements == 2:
                if token_index == 5:
                    return ["|"], prefix
                if token_index == 6:
                    return ["Actual", "Prev"], prefix
                if token_index == 7:
                    return ["+", "-"], prefix
                if token_index == 8:
                    return TIMEFRAME_OPTIONS, prefix
                if token_index == 9:
                    return ["DR"], prefix
                if token_index == 10:
                    return ZONE_OPTIONS, prefix

        return [], prefix

    def _maybe_move_to_second_line(self) -> None:
        cursor = self.textCursor()
        if cursor.blockNumber() != 0:
            return

        first_line = self.document().findBlockByNumber(0).text()
        if not self._is_first_line_complete(first_line):
            return

        second_block = self.document().findBlockByNumber(1)
        if not second_block.isValid():
            insert_cursor = QTextCursor(self.document())
            insert_cursor.setPosition(self.document().findBlockByNumber(0).position() + len(first_line))
            insert_cursor.insertText("\n")
            second_block = self.document().findBlockByNumber(1)

        if second_block.isValid() and second_block.text().strip():
            return

        if second_block.isValid():
            cursor.setPosition(second_block.position())
            self.setTextCursor(cursor)
            QTimer.singleShot(0, lambda: self._show_completions(force=True))

    @classmethod
    def _is_first_line_complete(cls, line_text: str) -> bool:
        first_line = line_text.strip()
        in_match = _LINE_1_IN_RE.match(first_line)
        if in_match:
            _sign, timeframe, element = in_match.groups()
            return (
                timeframe.upper() in cls._TIMEFRAME_OPTIONS_NORMALIZED
                and element.casefold() in cls._ELEMENT_OPTIONS_NORMALIZED
            )

        range_one_match = _LINE_1_RANGE_ONE_RE.match(first_line)
        if range_one_match:
            sign_1, tf_1, element_1, _direction = range_one_match.groups()
            first_ok = (
                sign_1 in ("+", "-")
                and tf_1.upper() in cls._TIMEFRAME_OPTIONS_NORMALIZED
                and element_1.casefold() in cls._ELEMENT_OPTIONS_NORMALIZED
            )
            return first_ok

        range_two_match = _LINE_1_RANGE_TWO_RE.match(first_line)
        if range_two_match:
            sign_1, tf_1, element_1, sign_2, tf_2, element_2 = range_two_match.groups()
            first_ok = (
                sign_1 in ("+", "-")
                and tf_1.upper() in cls._TIMEFRAME_OPTIONS_NORMALIZED
                and element_1.casefold() in cls._ELEMENT_OPTIONS_NORMALIZED
            )
            return (
                first_ok
                and sign_2 in ("+", "-")
                and tf_2.upper() in cls._TIMEFRAME_OPTIONS_NORMALIZED
                and element_2.casefold() in cls._ELEMENT_OPTIONS_NORMALIZED
            )
        return False

    def _current_mode_and_element_count(self) -> tuple[str | None, int]:
        first_line = self.document().findBlockByNumber(0).text().strip()
        if _LINE_1_IN_RE.match(first_line):
            return "IN", 1

        if _LINE_1_RANGE_ONE_RE.match(first_line):
            return "RANGE", 1
        if _LINE_1_RANGE_TWO_RE.match(first_line):
            return "RANGE", 2

        tokens = first_line.split()
        if not tokens:
            return None, 0
        if tokens[0].upper() == "IN":
            return "IN", 1
        if tokens[0].upper() == "RANGE":
            if len(tokens) >= 7:
                return "RANGE", 2
            return "RANGE", 1
        return None, 0

    def _maybe_autofill_dr_token(self) -> None:
        cursor = self.textCursor()
        if cursor.blockNumber() != 1:
            return

        mode, range_elements = self._current_mode_and_element_count()
        if mode is None:
            return

        before = cursor.block().text()[: cursor.positionInBlock()]
        token_source = re.sub(r"([|;])", r" \1 ", before)
        if not token_source.endswith((" ", "\t")):
            return
        tokens = re.split(r"\s+", token_source.strip()) if token_source.strip() else []
        if not tokens:
            return

        def is_range_prefix(start: int) -> bool:
            if len(tokens) < start + 3:
                return False
            if tokens[start].upper() not in ("ACTUAL", "PREV"):
                return False
            if tokens[start + 1] not in ("+", "-"):
                return False
            if tokens[start + 2].upper() not in self._TIMEFRAME_OPTIONS_NORMALIZED:
                return False
            return True

        should_insert = len(tokens) == 3 and is_range_prefix(0)
        if mode == "RANGE" and range_elements == 2:
            should_insert = should_insert or (
                len(tokens) == 9 and len(tokens) > 5 and tokens[5] in ("|", ";") and is_range_prefix(6)
            )

        if should_insert:
            cursor.insertText("DR ")
            self.setTextCursor(cursor)
            QTimer.singleShot(0, lambda: self._show_completions(force=True))


@dataclass(slots=True)
class SituationEntryData:
    image_path: str
    timeframe: str = ""
    notation: str = ""
    text: str = ""


class SituationEntryWidget(QFrame):
    changed = Signal()
    remove_requested = Signal(QWidget)

    def __init__(self, data: SituationEntryData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("situationCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._base_dir: Path | None = None
        self._source_pixmap = QPixmap()

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        header = QHBoxLayout()
        self.title_label = QLabel("Картинка")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.remove_button = QPushButton("Удалить")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(self.remove_button)
        root.addLayout(header)

        self.image_frame = QFrame()
        self.image_frame.setFixedHeight(220)
        self.image_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.image_frame.setStyleSheet("QFrame { border: 1px solid #d8dde6; border-radius: 6px; background: transparent; }")
        image_layout = QVBoxLayout(self.image_frame)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        self.image_label = QLabel("Изображение не найдено")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        image_layout.addWidget(self.image_label)
        root.addWidget(self.image_frame)

        tf_row = QHBoxLayout()
        self.tf_label = QLabel("TF *")
        tf_row.addWidget(self.tf_label)
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItem("Выберите TF", "")
        for timeframe in TIMEFRAME_OPTIONS:
            self.timeframe_combo.addItem(timeframe, timeframe)
        tf_row.addWidget(self.timeframe_combo, 1)
        root.addLayout(tf_row)

        self.image_path = data.image_path
        if data.timeframe:
            index = self.timeframe_combo.findData(data.timeframe)
            if index >= 0:
                self.timeframe_combo.setCurrentIndex(index)

        self._update_image_preview()
        self.timeframe_combo.currentIndexChanged.connect(lambda _: self.changed.emit())

    def set_index(self, index: int) -> None:
        self.title_label.setText(f"Картинка #{index}")

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self._update_image_preview()

    def set_read_mode(self, read_mode: bool) -> None:
        self.remove_button.setVisible(not read_mode)
        self.timeframe_combo.setEnabled(not read_mode)

    def to_data(self) -> SituationEntryData:
        return SituationEntryData(
            image_path=self.image_path,
            timeframe=self.timeframe_combo.currentData() or "",
        )

    def validate(self) -> tuple[bool, str]:
        if not self.image_path.strip():
            return False, "Не выбрана картинка."

        if not self.timeframe_combo.currentData():
            return False, "Укажите TF."

        return True, ""

    def to_markdown(self, index: int, base_dir: Path | None) -> str:
        data = self.to_data()
        image_markdown_path = self._to_markdown_path(Path(data.image_path), base_dir)
        alt_text = Path(image_markdown_path).stem or f"situation_{index}"
        return "\n".join(
            [
                f"![{alt_text}]({image_markdown_path})",
                f"**TF:** {data.timeframe}",
            ]
        ).strip()

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
            self.image_label.setMinimumSize(0, 0)
            self.image_label.setMaximumSize(16777215, 16777215)
            self.image_frame.setFixedHeight(120)
            return

        source = QPixmap(str(resolved))
        if source.isNull():
            self._source_pixmap = QPixmap()
            self.image_label.setText("Не удалось загрузить изображение")
            self.image_label.setPixmap(QPixmap())
            self.image_label.setMinimumSize(0, 0)
            self.image_label.setMaximumSize(16777215, 16777215)
            self.image_frame.setFixedHeight(120)
            return

        self._source_pixmap = source
        self._render_image_preview()

    def _render_image_preview(self) -> None:
        if self._source_pixmap.isNull():
            return

        frame_width = self.image_frame.width() if self.image_frame.width() > 16 else self.width()
        target_width = max(320, int((frame_width - 2) * 1.24))
        target_width = min(target_width, max(120, frame_width - 2))
        scaled = self._source_pixmap.scaledToWidth(target_width, Qt.TransformationMode.SmoothTransformation)
        if scaled.height() > 544:
            scaled = scaled.scaledToHeight(544, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setText("")
        self.image_label.setMinimumSize(scaled.size())
        self.image_label.setMaximumSize(scaled.size())
        self.image_label.setPixmap(scaled)
        target_height = max(381, scaled.height() + 2)
        if self.image_frame.height() != target_height:
            self.image_frame.setFixedHeight(target_height)

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

class CurrentSituationEditor(QWidget):
    content_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._base_dir: Path | None = None
        self._read_mode = False
        self._auto_generated_text = ""
        self._entries: list[SituationEntryWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        top_row = QHBoxLayout()
        self.add_image_button = QPushButton("Добавить картинку")
        self.add_image_button.clicked.connect(self._on_add_image_clicked)
        top_row.addWidget(self.add_image_button)
        self.paste_image_button = QPushButton("Вставить из буфера")
        self.paste_image_button.clicked.connect(self._on_paste_image_clicked)
        top_row.addWidget(self.paste_image_button)
        top_row.addStretch(1)
        root.addLayout(top_row)

        self.empty_label = QLabel("Добавьте минимум одну картинку, чтобы начать описание текущей ситуации.")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.entries_container = QWidget()
        self.entries_layout = QGridLayout(self.entries_container)
        self.entries_layout.setContentsMargins(0, 0, 0, 0)
        self.entries_layout.setSpacing(10)
        self.entries_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.entries_layout.setColumnStretch(0, 1)
        self.entries_layout.setColumnStretch(1, 1)
        self.entries_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root.addWidget(self.entries_container)

        self.notation_container = QWidget(self)
        notation_layout = QVBoxLayout(self.notation_container)
        notation_layout.setContentsMargins(0, 0, 0, 0)
        notation_layout.setSpacing(6)

        self.notation_label = QLabel("Нотация *")
        notation_layout.addWidget(self.notation_label)
        self.notation_edit = NotationTextEdit(self)
        notation_layout.addWidget(self.notation_edit)

        self.notation_status = QLabel(
            "Подсказка: нотация должна содержать ровно 2 непустые строки."
        )
        self.notation_status.setWordWrap(True)
        self.notation_status.setStyleSheet("color: #95a1b5;")
        notation_layout.addWidget(self.notation_status)

        self.manual_label = QLabel("Текст под картинками")
        notation_layout.addWidget(self.manual_label)
        self.manual_edit = QPlainTextEdit(self)
        self.manual_edit.setPlaceholderText("Введите дополнительный текст для блока текущей ситуации.")
        self.manual_edit.setMinimumHeight(120)
        notation_layout.addWidget(self.manual_edit)

        root.addWidget(self.notation_container)

        self.notation_edit.textChanged.connect(self._on_notation_changed)
        self.manual_edit.textChanged.connect(self.content_changed)

        self._update_empty_state()
        self._update_notation_feedback()

    def set_read_mode(self, read_mode: bool) -> None:
        self._read_mode = read_mode
        self.add_image_button.setVisible(not read_mode)
        self.paste_image_button.setVisible(not read_mode)
        self.notation_label.setVisible(not read_mode)
        self.notation_edit.setVisible(not read_mode)
        self.notation_status.setVisible(not read_mode)
        self.manual_label.setVisible(not read_mode)
        self.manual_label.setText("Текст под картинками")
        self.manual_edit.setReadOnly(read_mode)
        for entry in self._entries:
            entry.set_read_mode(read_mode)
        self._update_empty_state()

    def set_base_directory(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        for entry in self._entries:
            entry.set_base_dir(base_dir)

    def load_from_markdown(self, markdown: str) -> None:
        parsed_entries, notation_text, manual_text = self._parse_block(markdown)
        generated_from_notation = self._generated_text_from_notation(notation_text)
        manual_suffix = self._extract_manual_suffix(manual_text, generated_from_notation)
        composed_manual_text = self._compose_manual_text(generated_from_notation, manual_suffix)

        self._clear_entries()
        for data in parsed_entries:
            self._add_entry_widget(data)
        self.notation_edit.blockSignals(True)
        self.notation_edit.setPlainText(notation_text)
        self.notation_edit.blockSignals(False)
        self.manual_edit.blockSignals(True)
        self.manual_edit.setPlainText(composed_manual_text)
        self.manual_edit.blockSignals(False)
        self._auto_generated_text = generated_from_notation
        self._update_entry_titles()
        self._update_empty_state()
        self._update_notation_feedback()
        self.content_changed.emit()

    def to_markdown(self) -> str:
        chunks = [entry.to_markdown(index + 1, self._base_dir) for index, entry in enumerate(self._entries)]
        notation = self.notation_edit.toPlainText().strip()
        manual_text = self.manual_edit.toPlainText().strip()
        generated_from_notation = self._generated_text_from_notation(notation)
        manual_suffix = self._extract_manual_suffix(manual_text, generated_from_notation)
        manual_text = self._compose_manual_text(generated_from_notation, manual_suffix)

        parts: list[str] = []
        if chunks:
            parts.append("\n\n".join(chunks).strip())
        if notation:
            parts.append(f"<!-- NOTATION\n{notation}\n-->")
        if manual_text:
            parts.append(manual_text)
        return "\n\n".join(part for part in parts if part.strip()).strip()

    def validate_content(self) -> tuple[bool, str]:
        if not self._entries:
            return False, "В разделе текущей ситуации нужна минимум одна картинка."

        for index, entry in enumerate(self._entries, start=1):
            ok, error = entry.validate()
            if ok:
                continue
            return False, f"Картинка #{index}: {error}"

        notation = self.notation_edit.toPlainText().strip()
        if not notation:
            return False, "Заполните нотацию для блока текущей ситуации."

        _text, notation_error = notation_to_text(notation)
        if notation_error:
            return False, f"Ошибка нотации: {notation_error}"

        return True, ""

    def has_content(self) -> bool:
        return bool(self._entries)

    def image_widgets(self) -> list[SituationEntryWidget]:
        return list(self._entries)

    def _on_notation_changed(self) -> None:
        self._sync_manual_text_with_notation()
        self._update_notation_feedback()
        self.content_changed.emit()

    def _update_notation_feedback(self) -> None:
        notation = self.notation_edit.toPlainText().strip()
        if not notation:
            self.notation_status.setStyleSheet("color: #95a1b5;")
            self.notation_status.setText("Подсказка: нотация должна содержать ровно 2 непустые строки.")
            return

        converted, error = notation_to_text(notation)
        if error:
            self.notation_status.setStyleSheet("color: #ff7b72;")
            self.notation_status.setText(f"Ошибка нотации: {error}")
            return

        self.notation_status.setStyleSheet("color: #00e676;")
        self.notation_status.setText(f"Результат: {converted}")

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

        self._add_entry_widget(SituationEntryData(image_path=image_file))
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _on_paste_image_clicked(self) -> None:
        image_path = image_path_from_clipboard()
        if image_path is None:
            QMessageBox.warning(self, "Буфер обмена", "В буфере обмена нет изображения.")
            return

        self._add_entry_widget(SituationEntryData(image_path=str(image_path)))
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _add_entry_widget(self, data: SituationEntryData) -> None:
        entry = SituationEntryWidget(data, self)
        entry.set_base_dir(self._base_dir)
        entry.set_read_mode(self._read_mode)
        entry.changed.connect(self.content_changed)
        entry.remove_requested.connect(self._remove_entry_widget)
        self._entries.append(entry)
        self._refresh_entries_layout()

    def _remove_entry_widget(self, widget: QWidget) -> None:
        if widget in self._entries:
            self._entries.remove(widget)
        widget.setParent(None)
        widget.deleteLater()
        self._refresh_entries_layout()
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _clear_entries(self) -> None:
        while self._entries:
            widget = self._entries.pop()
            widget.setParent(None)
            widget.deleteLater()
        self._refresh_entries_layout()

    def _update_entry_titles(self) -> None:
        for index, entry in enumerate(self._entries, start=1):
            entry.set_index(index)

    def _refresh_entries_layout(self) -> None:
        while self.entries_layout.count():
            self.entries_layout.takeAt(0)

        for index, entry in enumerate(self._entries):
            row = index // 2
            col = index % 2
            self.entries_layout.addWidget(entry, row, col)

    def _update_empty_state(self) -> None:
        is_empty = len(self._entries) == 0
        self.empty_label.setVisible(is_empty)
        self.entries_container.setVisible(not is_empty)
        self.notation_container.setVisible(not is_empty)
        self.notation_label.setVisible((not is_empty) and (not self._read_mode))
        self.notation_edit.setVisible((not is_empty) and (not self._read_mode))
        self.notation_status.setVisible((not is_empty) and (not self._read_mode))

    @staticmethod
    def _extract_manual_suffix(manual_text: str, generated_text: str) -> str:
        text = manual_text.strip()
        generated = generated_text.strip()
        if not generated:
            return text
        if text.casefold().startswith(generated.casefold()):
            return text[len(generated) :].lstrip(" \t\r\n-:;,.")
        return text

    @staticmethod
    def _compose_manual_text(generated_text: str, manual_suffix: str) -> str:
        generated = generated_text.strip()
        suffix = manual_suffix.strip()
        if generated and suffix:
            return f"{generated}\n{suffix}"
        if generated:
            return generated
        return suffix

    @staticmethod
    def _generated_text_from_notation(notation: str) -> str:
        cleaned = notation.strip()
        if not cleaned:
            return ""
        generated, error = notation_to_text(cleaned)
        if error or not generated:
            return ""
        return generated.strip()

    def _sync_manual_text_with_notation(self) -> None:
        current_manual = self.manual_edit.toPlainText().strip()
        notation_text = self.notation_edit.toPlainText().strip()
        generated = self._generated_text_from_notation(notation_text)
        if notation_text and not generated:
            return

        suffix = self._extract_manual_suffix(current_manual, self._auto_generated_text)
        if not suffix:
            suffix = self._extract_manual_suffix(current_manual, generated)
        composed = self._compose_manual_text(generated, suffix)
        self._auto_generated_text = generated

        if composed == current_manual:
            return

        self.manual_edit.blockSignals(True)
        self.manual_edit.setPlainText(composed)
        cursor = self.manual_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.manual_edit.setTextCursor(cursor)
        self.manual_edit.blockSignals(False)

    @staticmethod
    def _parse_entries(markdown: str) -> list[SituationEntryData]:
        text = markdown.strip()
        if not text:
            return []

        image_matches = list(_IMAGE_RE.finditer(text))
        if not image_matches:
            return []

        entries: list[SituationEntryData] = []
        for index, match in enumerate(image_matches):
            start = match.start()
            end = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(text)
            chunk = text[start:end].strip()

            image_path = match.group(1).strip()
            timeframe_match = re.search(r"(?mi)^\*\*TF:\*\*\s*(.+?)\s*$", chunk)
            if not timeframe_match:
                timeframe_match = re.search(r"(?mi)^TF:\s*(.+?)\s*$", chunk)
            timeframe = timeframe_match.group(1).strip() if timeframe_match else ""

            entries.append(
                SituationEntryData(
                    image_path=image_path,
                    timeframe=timeframe,
                )
            )

        return entries

    @classmethod
    def _parse_block(cls, markdown: str) -> tuple[list[SituationEntryData], str, str]:
        text = markdown.strip()
        if not text:
            return [], "", ""

        entries = cls._parse_entries(text)

        notation = ""
        notation_match = _NOTATION_COMMENT_RE.search(text)
        if notation_match:
            notation = notation_match.group(1).strip()

        manual_text = _NOTATION_COMMENT_RE.sub("", text)
        manual_text = _IMAGE_RE.sub("", manual_text)
        manual_text = re.sub(r"(?mi)^(?:\*\*TF:\*\*|TF:)\s*.+$", "", manual_text)
        manual_text = re.sub(r"(?mi)^---+\s*$", "", manual_text)
        manual_text = manual_text.strip()

        return entries, notation, manual_text


