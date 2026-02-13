from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from PySide6.QtCore import QTimer, QStringListModel, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .current_situation import ELEMENT_OPTIONS, TIMEFRAME_OPTIONS
from .image_clipboard import image_path_from_clipboard

_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")
_MEANING_RE = re.compile(
    r"^(ADV|NOT[\s_]+ADV)\s+(BUY|SELL)\s+(UP|LOW)\s+(.+)$",
    re.IGNORECASE,
)
_MEANING_RANGE_RE = re.compile(
    r"^(ACTUAL|PREV)\s+([+-])\s+([A-Za-z0-9]+)\s+DR\s+(PREMIUM|DISCOUNT|EQUILIBRIUM)$",
    re.IGNORECASE,
)
_MEANING_ELEMENT_RE = re.compile(
    r"^([+-])\s+([A-Za-z0-9]+)\s+(.+)$",
    re.IGNORECASE,
)
_ACTION_HELP = (
    "CREATE +/- TF Element [ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium] "
    "[WITH +/- TF Element ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium BREAK/NOT BREAK] "
    "или NOT CREATE +/- TF Element "
    "[WITH +/- TF Element ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium] "
    "или GET/NOT GET +/- TF Element ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium"
)
_MEANING_HELP = (
    "ADV/NOT ADV BUY/SELL UP/LOW (+/- TF Element | ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium)"
)
_ZONE_OPTIONS = ["Premium", "Discount", "Equilibrium"]


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


def _is_tf_token(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9]+", value) is not None


def _is_zone_token(value: str) -> bool:
    return value.casefold() in ("premium", "discount", "equilibrium")


def _range_kind_text(value: str) -> str:
    return "актуального" if value == "ACTUAL" else "предыдущего"


def _element_desc(sign: str, timeframe: str, element: str) -> str:
    return f"[{sign}{timeframe.upper()} {element}]"


def _dr_desc(sign: str, timeframe: str) -> str:
    return f"[{sign}{timeframe.upper()} DR]"


def transition_action_from_notation(notation: str) -> str | None:
    lines = [line.strip() for line in notation.splitlines() if line.strip()]
    if len(lines) != 1:
        return None

    normalized = _normalize_action(lines[0])
    if normalized.startswith("NOT CREATE"):
        return "NOT CREATE"
    if normalized.startswith("CREATE"):
        return "CREATE"
    if normalized.startswith("NOT GET"):
        return "NOT GET"
    if normalized.startswith("GET"):
        return "GET"
    return None


def transition_meaning_notation_to_text(notation: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in notation.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, "Notation must contain exactly one non-empty line."

    line = lines[0]
    meaning_match = _MEANING_RE.match(line)
    if not meaning_match:
        return None, f"Notation format: {_MEANING_HELP}"

    advantage_raw, side_raw, level_raw, tail = meaning_match.groups()
    advantage = _normalize_action(advantage_raw)
    side = side_raw.upper()
    level = level_raw.upper()

    advantage_text = "преимущество" if advantage == "ADV" else "отсутствие преимущества"
    side_text = "покупателей над продавцами" if side == "BUY" else "продавцов над покупателями"
    level_text = "выше" if level == "UP" else "ниже"

    range_match = _MEANING_RANGE_RE.match(tail)
    if range_match:
        range_kind_raw, range_sign, range_tf, zone_raw = range_match.groups()
        range_kind_text = "актуального" if range_kind_raw.upper() == "ACTUAL" else "предыдущего"
        range_desc = f"[{range_sign}{range_tf.upper()} DR]"
        zone = _normalize_zone(zone_raw)
        return (
            (
                "Такое ценообразование будет означать "
                f"{advantage_text} {side_text} {level_text} "
                f"отметок {zone} {range_kind_text} {range_desc}."
            ),
            None,
        )

    element_match = _MEANING_ELEMENT_RE.match(tail)
    if element_match:
        element_sign, element_tf, element_name = element_match.groups()
        element_desc = f"[{element_sign}{element_tf.upper()} {element_name.strip()}]"
        return (
            (
                "Данное ценообразование будет означать "
                f"{advantage_text} {side_text} {level_text} "
                f"{element_desc}."
            ),
            None,
        )

    return None, (
        "After ADV/NOT ADV BUY/SELL UP/LOW specify either +/- TF Element "
        "or ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium."
    )


def transition_notation_to_text(notation: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in notation.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, "Нотация должна содержать ровно 1 непустую строку."

    line = re.sub(r"^(NOT)_(CREATE|GET)\b", r"\1 \2", lines[0], flags=re.IGNORECASE)
    tokens = re.split(r"\s+", line.strip()) if line.strip() else []
    if not tokens:
        return None, f"Формат нотации: {_ACTION_HELP}"

    def parse_element(start: int) -> tuple[tuple[str, str, str] | None, int, str | None]:
        if len(tokens) < start + 3:
            return None, start, "Ожидается элемент в формате +/- TF Element."
        sign = tokens[start]
        timeframe = tokens[start + 1]
        element = tokens[start + 2]
        if sign not in ("+", "-"):
            return None, start, "Ожидается знак +/- для элемента."
        if not _is_tf_token(timeframe):
            return None, start, "Ожидается корректный TF для элемента."
        return (sign, timeframe.upper(), element), start + 3, None

    def parse_range(start: int) -> tuple[tuple[str, str, str, str] | None, int, str | None]:
        if len(tokens) < start + 5:
            return (
                None,
                start,
                "Ожидается диапазон в формате ACTUAL/PREV +/- TF DR Premium/Discount/Equilibrium.",
            )
        range_kind = tokens[start].upper()
        sign = tokens[start + 1]
        timeframe = tokens[start + 2]
        dr = tokens[start + 3].upper()
        zone_raw = tokens[start + 4]
        if range_kind not in ("ACTUAL", "PREV"):
            return None, start, "Ожидается ACTUAL/PREV для диапазона."
        if sign not in ("+", "-"):
            return None, start, "Ожидается знак +/- для диапазона."
        if not _is_tf_token(timeframe):
            return None, start, "Ожидается корректный TF для диапазона."
        if dr != "DR":
            return None, start, "После TF диапазона должно быть DR."
        if not _is_zone_token(zone_raw):
            return None, start, "Ожидается Premium/Discount/Equilibrium."
        return (range_kind, sign, timeframe.upper(), _normalize_zone(zone_raw)), start + 5, None

    action = None
    index = 0
    first = tokens[0].upper()
    if first == "NOT":
        if len(tokens) < 2:
            return None, f"Формат нотации: {_ACTION_HELP}"
        second = tokens[1].upper()
        if second == "CREATE":
            action = "NOT CREATE"
        elif second == "GET":
            action = "NOT GET"
        else:
            return None, f"Формат нотации: {_ACTION_HELP}"
        index = 2
    elif first == "CREATE":
        action = "CREATE"
        index = 1
    elif first == "GET":
        action = "GET"
        index = 1
    else:
        return None, f"Формат нотации: {_ACTION_HELP}"

    primary_element, index, error = parse_element(index)
    if error or primary_element is None:
        return None, error or "Неверный формат элемента."

    if action in ("GET", "NOT GET"):
        range_data, index, error = parse_range(index)
        if error or range_data is None:
            return None, error or "Неверный формат диапазона."
        if index != len(tokens):
            return None, f"Формат нотации: {_ACTION_HELP}"

        action_text = "получить" if action == "GET" else "не получить"
        range_kind, range_sign, range_tf, zone = range_data
        text = (
            "Для перехода к сделке цена должна "
            f"{action_text} реакцию от {_element_desc(*primary_element)}, "
            f"расположенного в отметках {zone} {_range_kind_text(range_kind)} "
            f"{_dr_desc(range_sign, range_tf)}."
        )
        return text, None

    primary_range: tuple[str, str, str, str] | None = None
    with_element: tuple[str, str, str] | None = None
    with_range: tuple[str, str, str, str] | None = None
    with_mode: str | None = None

    if action == "CREATE" and index < len(tokens) and tokens[index].upper() in ("ACTUAL", "PREV"):
        primary_range, index, error = parse_range(index)
        if error:
            return None, error

    if index < len(tokens):
        if tokens[index].upper() != "WITH":
            if action == "NOT CREATE":
                return None, "Для NOT CREATE после элемента допускается только опциональный блок WITH."
            return None, f"Формат нотации: {_ACTION_HELP}"

        index += 1
        with_element, index, error = parse_element(index)
        if error or with_element is None:
            return None, error or "После WITH ожидается элемент."
        with_range, index, error = parse_range(index)
        if error:
            return None, error
        if action == "CREATE":
            if index >= len(tokens):
                return None, "После WITH блока для CREATE укажите BREAK или NOT BREAK."
            marker = tokens[index].upper()
            if marker == "BREAK":
                with_mode = "BREAK"
                index += 1
            elif marker == "NOT_BREAK":
                with_mode = "NOT BREAK"
                index += 1
            elif marker == "NOT" and index + 1 < len(tokens) and tokens[index + 1].upper() == "BREAK":
                with_mode = "NOT BREAK"
                index += 2
            else:
                return None, "После WITH блока для CREATE допускаются только BREAK или NOT BREAK."

    if index != len(tokens):
        return None, f"Формат нотации: {_ACTION_HELP}"

    action_text = "сформировать" if action == "CREATE" else "не сформировать"
    text = f"Для перехода к сделке цена должна {action_text} {_element_desc(*primary_element)}"

    details: list[str] = []
    if primary_range:
        details.append(
            f"расположенный в отметках {primary_range[3]} {_range_kind_text(primary_range[0])} "
            f"{_dr_desc(primary_range[1], primary_range[2])}"
        )
    if with_element and with_range:
        with_description = (
            f"{_element_desc(*with_element)}, расположенного в отметках {with_range[3]} "
            f"{_range_kind_text(with_range[0])} {_dr_desc(with_range[1], with_range[2])}"
        )
        if action == "CREATE" and with_mode == "BREAK":
            details.append(f"с пробитием {with_description}")
        elif action == "CREATE" and with_mode == "NOT BREAK":
            details.append(f"после реакции на {with_description}")
        else:
            details.append(f"в ходе взаимодействия с {with_description}")

    if details:
        return f"{text}, {' '.join(details)}.", None
    return f"{text}.", None


class TransitionNotationEdit(QLineEdit):
    _ACTION_FIRST_OPTIONS = ["CREATE", "GET", "NOT"]
    _ACTION_AFTER_NOT_OPTIONS = ["CREATE", "GET"]
    _RANGE_KIND_OPTIONS = ["ACTUAL", "PREV"]
    _ZONE_OPTIONS = _ZONE_OPTIONS

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
        text = self.text()
        cursor_pos = self.cursorPosition()

        start = cursor_pos
        while start > 0 and not text[start - 1].isspace():
            start -= 1

        end = cursor_pos
        while end < len(text) and not text[end].isspace():
            end += 1

        updated = f"{text[:start]}{completion}{text[end:]}"
        new_cursor = start + len(completion)
        if new_cursor >= len(updated) or not updated[new_cursor].isspace():
            updated = f"{updated[:new_cursor]} {updated[new_cursor:]}"
            new_cursor += 1
        self.setText(updated)
        self.setCursorPosition(new_cursor)
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
            cursor = self.cursorPosition()
            if cursor > 0 and not self.text()[cursor - 1].isspace():
                return

        self._model.setStringList(suggestions)
        self._completer.setCompletionPrefix(prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(360, popup.sizeHintForColumn(0) + 24))
        self._completer.complete(rect)

    def _completion_context(self) -> tuple[list[str], str]:
        before = self.text()[: self.cursorPosition()]
        tokens = re.split(r"\s+", before.strip()) if before.strip() else []

        if before and not before.endswith((" ", "\t")):
            prefix = tokens[-1] if tokens else ""
            completed_tokens = tokens[:-1]
        else:
            prefix = ""
            completed_tokens = tokens

        suggestions = self._next_suggestions(completed_tokens)
        return suggestions, prefix

    def _next_suggestions(self, tokens: list[str]) -> list[str]:
        if not tokens:
            return self._ACTION_FIRST_OPTIONS

        first = tokens[0].upper()
        if first == "NOT":
            if len(tokens) == 1:
                return self._ACTION_AFTER_NOT_OPTIONS
            second = tokens[1].upper()
            if second not in ("CREATE", "GET"):
                return self._ACTION_AFTER_NOT_OPTIONS
            action = f"NOT {second}"
            index = 2
        elif first in ("CREATE", "GET"):
            action = first
            index = 1
        else:
            return self._ACTION_FIRST_OPTIONS

        if len(tokens) == index:
            return ["+", "-"]
        if len(tokens) == index + 1:
            return TIMEFRAME_OPTIONS
        if len(tokens) == index + 2:
            return ELEMENT_OPTIONS
        index += 3

        if action in ("GET", "NOT GET"):
            return self._range_suggestions(tokens, index)

        if action == "NOT CREATE":
            if len(tokens) == index:
                return ["WITH"]
            if tokens[index].upper() != "WITH":
                return ["WITH"]
            return self._with_suggestions(tokens, index, require_break=False)

        if len(tokens) == index:
            return ["ACTUAL", "PREV", "WITH"]

        head = tokens[index].upper()
        if head in ("ACTUAL", "PREV"):
            range_suggestions = self._range_suggestions(tokens, index)
            if range_suggestions:
                return range_suggestions
            index += 5
            if len(tokens) == index:
                return ["WITH"]
            if tokens[index].upper() != "WITH":
                return ["WITH"]
            return self._with_suggestions(tokens, index, require_break=True)

        if head == "WITH":
            return self._with_suggestions(tokens, index, require_break=True)

        return ["ACTUAL", "PREV", "WITH"]

    def _range_suggestions(self, tokens: list[str], start: int) -> list[str]:
        if len(tokens) == start:
            return self._RANGE_KIND_OPTIONS
        if len(tokens) == start + 1:
            return ["+", "-"]
        if len(tokens) == start + 2:
            return TIMEFRAME_OPTIONS
        if len(tokens) == start + 3:
            return ["DR"]
        if len(tokens) == start + 4:
            return self._ZONE_OPTIONS
        return []

    def _with_suggestions(self, tokens: list[str], with_index: int, require_break: bool) -> list[str]:
        if len(tokens) == with_index:
            return ["WITH"]
        if tokens[with_index].upper() != "WITH":
            return ["WITH"]

        start = with_index + 1
        if len(tokens) == start:
            return ["+", "-"]
        if len(tokens) == start + 1:
            return TIMEFRAME_OPTIONS
        if len(tokens) == start + 2:
            return ELEMENT_OPTIONS
        if len(tokens) == start + 3:
            return self._RANGE_KIND_OPTIONS
        if len(tokens) == start + 4:
            return ["+", "-"]
        if len(tokens) == start + 5:
            return TIMEFRAME_OPTIONS
        if len(tokens) == start + 6:
            return ["DR"]
        if len(tokens) == start + 7:
            return self._ZONE_OPTIONS
        if require_break and len(tokens) == start + 8:
            return ["BREAK", "NOT BREAK"]
        if require_break and len(tokens) == start + 9 and tokens[start + 8].upper() == "NOT":
            return ["BREAK"]
        return []

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        text = " ".join(self.text().replace("\n", " ").split())
        if text != self.text():
            self.setText(text)
        super().focusOutEvent(event)

    def _maybe_autofill_dr_token(self) -> None:
        text = self.text()
        cursor_pos = self.cursorPosition()
        if cursor_pos != len(text):
            return
        if not text[:cursor_pos].endswith((" ", "\t")):
            return

        tokens = re.split(r"\s+", text.strip()) if text.strip() else []
        if not tokens or tokens[-1].upper() == "DR":
            return

        suggestions = self._next_suggestions(tokens)
        if suggestions != ["DR"]:
            return

        self.setText(f"{text}DR ")
        self.setCursorPosition(len(self.text()))
        QTimer.singleShot(0, lambda: self._show_completions(force=True))


class TransitionMeaningNotationEdit(QLineEdit):
    _ACTION_FIRST_OPTIONS = ["ADV", "NOT"]
    _ACTION_AFTER_NOT_OPTIONS = ["ADV"]
    _SIDE_OPTIONS = ["BUY", "SELL"]
    _LEVEL_OPTIONS = ["UP", "LOW"]
    _RANGE_KIND_OPTIONS = ["ACTUAL", "PREV"]
    _ZONE_OPTIONS = _ZONE_OPTIONS
    _TIMEFRAME_OPTIONS_NORMALIZED = {item.upper() for item in TIMEFRAME_OPTIONS}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("ADV/NOT ADV BUY/SELL UP/LOW ...")
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
        text = self.text()
        cursor_pos = self.cursorPosition()

        start = cursor_pos
        while start > 0 and not text[start - 1].isspace():
            start -= 1

        end = cursor_pos
        while end < len(text) and not text[end].isspace():
            end += 1

        updated = f"{text[:start]}{completion}{text[end:]}"
        new_cursor = start + len(completion)
        if new_cursor >= len(updated) or not updated[new_cursor].isspace():
            updated = f"{updated[:new_cursor]} {updated[new_cursor:]}"
            new_cursor += 1
        self.setText(updated)
        self.setCursorPosition(new_cursor)
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
            cursor = self.cursorPosition()
            if cursor > 0 and not self.text()[cursor - 1].isspace():
                return

        self._model.setStringList(suggestions)
        self._completer.setCompletionPrefix(prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(360, popup.sizeHintForColumn(0) + 24))
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
            if action_kind != "ADV":
                return self._ACTION_AFTER_NOT_OPTIONS, prefix
            action_offset = 2
        elif first == "ADV":
            action_offset = 1
        else:
            return self._ACTION_FIRST_OPTIONS, prefix

        if token_index == action_offset:
            return self._SIDE_OPTIONS, prefix
        if token_index == action_offset + 1:
            return self._LEVEL_OPTIONS, prefix
        if token_index == action_offset + 2:
            return self._RANGE_KIND_OPTIONS, prefix

        tail_start = action_offset + 2
        tail_tokens = tokens[tail_start:] if len(tokens) > tail_start else []
        if not tail_tokens:
            return self._RANGE_KIND_OPTIONS, prefix

        first_tail = tail_tokens[0].upper()
        if first_tail in ("ACTUAL", "PREV"):
            relative_index = token_index - tail_start
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

        if first_tail in ("+", "-"):
            relative_index = token_index - tail_start
            if relative_index == 1:
                return TIMEFRAME_OPTIONS, prefix
            return ELEMENT_OPTIONS, prefix

        if prefix and any(option.startswith(prefix.upper()) for option in self._RANGE_KIND_OPTIONS):
            return self._RANGE_KIND_OPTIONS, prefix
        return self._RANGE_KIND_OPTIONS, prefix

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        text = " ".join(self.text().replace("\n", " ").split())
        if text != self.text():
            self.setText(text)
        super().focusOutEvent(event)

    def _maybe_autofill_dr_token(self) -> None:
        text = self.text()
        cursor_pos = self.cursorPosition()
        if cursor_pos != len(text):
            return
        before = text[:cursor_pos]
        if not before.endswith((" ", "\t")):
            return

        tokens = re.split(r"\s+", before.strip()) if before.strip() else []
        if not tokens:
            return

        first = tokens[0].upper()
        if first == "NOT":
            if len(tokens) < 2 or tokens[1].upper() != "ADV":
                return
            action_offset = 2
        elif first == "ADV":
            action_offset = 1
        else:
            return

        tail_start = action_offset + 2
        if len(tokens) < tail_start + 3:
            return
        first_tail = tokens[tail_start].upper()
        if first_tail not in ("ACTUAL", "PREV"):
            return

        if len(tokens) != tail_start + 3:
            return
        if tokens[tail_start + 1] not in ("+", "-"):
            return
        if tokens[tail_start + 2].upper() not in self._TIMEFRAME_OPTIONS_NORMALIZED:
            return

        self.setText(f"{text}DR ")
        self.setCursorPosition(len(self.text()))
        QTimer.singleShot(0, lambda: self._show_completions(force=True))


@dataclass(slots=True)
class TransitionScenarioImageData:
    image_path: str
    timeframe: str = ""


@dataclass(slots=True)
class TransitionScenarioData:
    images: list[TransitionScenarioImageData] = field(default_factory=list)
    notation: str = ""
    meaning_notation: str = ""
    why_text: str = ""


class TransitionScenarioImageWidget(QFrame):
    changed = Signal()
    remove_requested = Signal(QWidget)

    def __init__(self, data: TransitionScenarioImageData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._base_dir: Path | None = None
        self._source_pixmap = QPixmap()
        self.image_path = data.image_path

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
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
        self.tf_label = QLabel("Таймфрейм *")
        tf_row.addWidget(self.tf_label)
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItem("Выберите TF", "")
        for timeframe in TIMEFRAME_OPTIONS:
            self.timeframe_combo.addItem(timeframe, timeframe)
        if data.timeframe:
            index = self.timeframe_combo.findData(data.timeframe)
            if index >= 0:
                self.timeframe_combo.setCurrentIndex(index)
        tf_row.addWidget(self.timeframe_combo, 1)
        root.addLayout(tf_row)

        self.timeframe_combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        self._update_image_preview()

    def set_index(self, index: int) -> None:
        self.title_label.setText(f"Картинка #{index}")

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self._update_image_preview()

    def set_read_mode(self, read_mode: bool) -> None:
        self.remove_button.setVisible(not read_mode)
        self.timeframe_combo.setEnabled(not read_mode)

    def to_data(self) -> TransitionScenarioImageData:
        return TransitionScenarioImageData(
            image_path=self.image_path,
            timeframe=self.timeframe_combo.currentData() or "",
        )

    def validate(self) -> tuple[bool, str]:
        if not self.image_path.strip():
            return False, "Картинка не выбрана."
        if not self.timeframe_combo.currentData():
            return False, "Выберите таймфрейм."
        return True, ""

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
        self.image_label.setMinimumSize(0, 0)
        self.image_label.setMaximumSize(16777215, 16777215)
        self.image_label.setPixmap(scaled)
        target_height = max(381, scaled.height() + 2)
        if self.image_frame.height() != target_height:
            self.image_frame.setFixedHeight(target_height)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._render_image_preview()


class TransitionScenarioWidget(QFrame):
    changed = Signal()
    remove_requested = Signal(QWidget)

    def __init__(self, data: TransitionScenarioData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("transitionScenarioCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self._base_dir: Path | None = None
        self._follow_up_visible = False
        self._read_mode = False
        self._images: list[TransitionScenarioImageWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        header = QHBoxLayout()
        self.title_label = QLabel("Сценарий")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.add_image_button = QPushButton("Добавить картинку")
        self.add_image_button.clicked.connect(self._on_add_image_clicked)
        header.addWidget(self.add_image_button)
        self.paste_image_button = QPushButton("Вставить из буфера")
        self.paste_image_button.clicked.connect(self._on_paste_image_clicked)
        header.addWidget(self.paste_image_button)
        self.remove_button = QPushButton("Удалить")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(self.remove_button)
        root.addLayout(header)

        self.images_container = QWidget()
        self.images_layout = QGridLayout(self.images_container)
        self.images_layout.setContentsMargins(0, 0, 0, 0)
        self.images_layout.setSpacing(8)
        self.images_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.images_layout.setColumnStretch(0, 1)
        self.images_layout.setColumnStretch(1, 1)
        root.addWidget(self.images_container)

        self.notation_label = QLabel("Нотация *")
        root.addWidget(self.notation_label)
        self.notation_edit = TransitionNotationEdit()
        root.addWidget(self.notation_edit)

        self.notation_status = QLabel("")
        root.addWidget(self.notation_status)

        self.meaning_label = QLabel("Что это будет означать?")
        root.addWidget(self.meaning_label)

        self.meaning_notation_edit = TransitionMeaningNotationEdit()
        root.addWidget(self.meaning_notation_edit)

        self.meaning_status = QLabel("")
        root.addWidget(self.meaning_status)

        self.why_label = QLabel("Почему?")
        root.addWidget(self.why_label)

        self.manual_edit = QPlainTextEdit()
        self.manual_edit.setPlaceholderText("Объясните, почему это верная интерпретация")
        self.manual_edit.setMinimumHeight(120)
        self.manual_edit.setFixedHeight(120)
        self.manual_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.manual_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.manual_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root.addWidget(self.manual_edit)

        initial_images = data.images if data.images else [TransitionScenarioImageData(image_path="")]
        for image_data in initial_images:
            if image_data.image_path.strip():
                self._add_image_widget(image_data)
        self._update_image_titles()

        self.notation_edit.setText(data.notation)
        self.meaning_notation_edit.setText(data.meaning_notation)
        self.manual_edit.setPlainText(data.why_text)

        self._on_notation_changed()
        self._on_meaning_notation_changed()

        self.notation_edit.textChanged.connect(self._on_notation_changed)
        self.meaning_notation_edit.textChanged.connect(self._on_meaning_notation_changed)
        self.manual_edit.textChanged.connect(self.changed)

    def set_index(self, index: int) -> None:
        self.title_label.setText(f"Сценарий #{index}")

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        for image in self._images:
            image.set_base_dir(base_dir)

    def set_read_mode(self, read_mode: bool) -> None:
        self._read_mode = read_mode
        self.add_image_button.setVisible(not read_mode)
        self.paste_image_button.setVisible(not read_mode)
        self.remove_button.setVisible(not read_mode)
        self.notation_label.setVisible(not read_mode)
        self.notation_edit.setVisible(not read_mode)
        self.manual_edit.setReadOnly(read_mode)
        for image in self._images:
            image.set_read_mode(read_mode)
        self._set_follow_up_visible(self._follow_up_visible)

    def to_data(self) -> TransitionScenarioData:
        return TransitionScenarioData(
            images=[entry.to_data() for entry in self._images],
            notation=self.notation_edit.text().strip(),
            meaning_notation=self.meaning_notation_edit.text().strip(),
            why_text=self.manual_edit.toPlainText().strip(),
        )

    def image_widgets(self) -> list[TransitionScenarioImageWidget]:
        return list(self._images)

    def validate(self) -> tuple[bool, str]:
        if not self._images:
            return False, "Добавьте минимум одну картинку."

        for index, image in enumerate(self._images, start=1):
            ok, error = image.validate()
            if not ok:
                return False, f"Картинка #{index}: {error}"

        notation_text = self.notation_edit.text().strip()
        generated, notation_error = transition_notation_to_text(notation_text)
        if notation_error:
            return False, notation_error

        if not generated:
            return False, "Нотация пуста."

        action = transition_action_from_notation(notation_text)
        if action is None:
            return False, "Укажите CREATE/NOT CREATE/GET/NOT GET."

        meaning_notation = self.meaning_notation_edit.text().strip()
        if not meaning_notation:
            return False, "Заполните поле 'Что это будет означать?'."

        meaning_generated, meaning_error = transition_meaning_notation_to_text(meaning_notation)
        if meaning_error:
            return False, meaning_error

        if not meaning_generated:
            return False, "Нотация 'Что это будет означать?' пуста."

        if not self.manual_edit.toPlainText().strip():
            return False, "Заполните поле 'Почему?'."

        return True, ""

    def to_markdown(self, index: int, base_dir: Path | None) -> str:
        data = self.to_data()
        notation_generated, _ = transition_notation_to_text(data.notation)
        meaning_generated, _ = transition_meaning_notation_to_text(data.meaning_notation)

        parts = [f"#### Сценарий {index}"]
        for image_index, image in enumerate(data.images, start=1):
            image_markdown_path = self._to_markdown_path(Path(image.image_path), base_dir)
            alt_text = Path(image_markdown_path).stem or f"transition_{index}_{image_index}"
            parts.extend(
                [
                    f"![{alt_text}]({image_markdown_path})",
                    f"**TF:** {image.timeframe}",
                    "",
                ]
            )

        parts.extend(
            [
                "<!-- TRANSITION_NOTATION",
                data.notation.strip(),
                "-->",
            ]
        )

        if data.meaning_notation.strip():
            parts.extend(
                [
                    "",
                    "<!-- TRANSITION_MEANING_NOTATION",
                    data.meaning_notation.strip(),
                    "-->",
                ]
            )
        if data.why_text.strip():
            parts.extend(
                [
                    "",
                    "<!-- TRANSITION_WHY",
                    data.why_text.strip(),
                    "-->",
                ]
            )

        if notation_generated:
            parts.extend(
                [
                    "",
                    f"**Сценарий перехода к сделке:** {notation_generated}",
                ]
            )
        if meaning_generated:
            parts.extend(
                [
                    "",
                    f"**Что это будет означать?:** {meaning_generated}",
                ]
            )
        if data.why_text.strip():
            parts.extend(
                [
                    "",
                    "**Почему?:**",
                    data.why_text.strip(),
                ]
            )
        return "\n".join(parts).strip()

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
        self._add_image_widget(TransitionScenarioImageData(image_path=image_file))
        self._update_image_titles()
        self.changed.emit()

    def _on_paste_image_clicked(self) -> None:
        image_path = image_path_from_clipboard()
        if image_path is None:
            QMessageBox.warning(self, "Буфер обмена", "В буфере обмена нет изображения.")
            return

        self._add_image_widget(TransitionScenarioImageData(image_path=str(image_path)))
        self._update_image_titles()
        self.changed.emit()

    def _add_image_widget(self, data: TransitionScenarioImageData) -> None:
        widget = TransitionScenarioImageWidget(data, self)
        widget.set_base_dir(self._base_dir)
        widget.set_read_mode(self._read_mode)
        widget.changed.connect(self.changed)
        widget.remove_requested.connect(self._remove_image_widget)
        self._images.append(widget)
        self._refresh_images_layout()

    def _remove_image_widget(self, widget: QWidget) -> None:
        if widget in self._images:
            self._images.remove(widget)
        widget.setParent(None)
        widget.deleteLater()
        self._refresh_images_layout()
        self._update_image_titles()
        self.changed.emit()

    def _update_image_titles(self) -> None:
        for index, image in enumerate(self._images, start=1):
            image.set_index(index)

    def _refresh_images_layout(self) -> None:
        while self.images_layout.count():
            self.images_layout.takeAt(0)

        columns = 2
        for index, image in enumerate(self._images):
            row = index // columns
            col = index % columns
            self.images_layout.addWidget(image, row, col)
            QTimer.singleShot(0, image._render_image_preview)

    def _on_notation_changed(self) -> None:
        notation_text = self.notation_edit.text().strip()
        generated, error = transition_notation_to_text(notation_text)
        has_action = transition_action_from_notation(notation_text) is not None
        self._set_follow_up_visible(has_action)
        self._on_meaning_notation_changed(emit_change=False)
        if error:
            self.notation_status.setText(f"Подсказка: {error}")
            self.notation_status.setStyleSheet("color: #9a6b00;")
            self.changed.emit()
            return

        self.notation_status.setText(generated or "")
        self.notation_status.setStyleSheet("color: #24d061;")
        self.changed.emit()

    def _on_meaning_notation_changed(self, emit_change: bool = True) -> None:
        if not self._follow_up_visible:
            self.meaning_status.clear()
            if emit_change:
                self.changed.emit()
            return

        meaning_text = self.meaning_notation_edit.text().strip()
        if not meaning_text:
            self.meaning_status.setText("Подсказка: заполните нотацию для вопроса 'Что это будет означать?'")
            self.meaning_status.setStyleSheet("color: #9a6b00;")
            if emit_change:
                self.changed.emit()
            return

        generated, error = transition_meaning_notation_to_text(meaning_text)
        if error:
            self.meaning_status.setText(f"Подсказка: {error}")
            self.meaning_status.setStyleSheet("color: #9a6b00;")
            if emit_change:
                self.changed.emit()
            return

        self.meaning_status.setText(generated or "")
        self.meaning_status.setStyleSheet("color: #24d061;")
        if emit_change:
            self.changed.emit()

    def _set_follow_up_visible(self, visible: bool) -> None:
        self._follow_up_visible = visible
        self.meaning_label.setVisible(visible)
        self.meaning_notation_edit.setVisible(visible and (not self._read_mode))
        self.meaning_status.setVisible(visible)
        self.why_label.setVisible(visible)
        self.manual_edit.setVisible(visible)

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
        self._read_mode = False
        self._entries: list[TransitionScenarioWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        top_row = QHBoxLayout()
        self.add_image_button = QPushButton("Добавить сценарий")
        self.add_image_button.clicked.connect(self._on_add_image_clicked)
        top_row.addWidget(self.add_image_button)
        self.paste_image_button = QPushButton("Вставить из буфера")
        self.paste_image_button.clicked.connect(self._on_paste_image_clicked)
        top_row.addWidget(self.paste_image_button)
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

    def set_read_mode(self, read_mode: bool) -> None:
        self._read_mode = read_mode
        self.add_image_button.setVisible(not read_mode)
        self.paste_image_button.setVisible(not read_mode)
        for entry in self._entries:
            entry.set_read_mode(read_mode)

    def load_from_markdown(self, markdown: str) -> None:
        self._clear_entries()
        for data in self._parse_entries(markdown):
            self._add_entry_widget(data)
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _on_paste_image_clicked(self) -> None:
        image_path = image_path_from_clipboard()
        if image_path is None:
            QMessageBox.warning(self, "Буфер обмена", "В буфере обмена нет изображения.")
            return

        self._add_entry_widget(
            TransitionScenarioData(
                images=[TransitionScenarioImageData(image_path=str(image_path))],
            )
        )
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

    def _add_entry_widget(self, data: TransitionScenarioData) -> None:
        entry = TransitionScenarioWidget(data, self)
        entry.set_base_dir(self._base_dir)
        entry.set_read_mode(self._read_mode)
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

        chunks = TransitionScenariosEditor._split_scenario_chunks(text)
        entries: list[TransitionScenarioData] = []
        for chunk in chunks:
            parsed = TransitionScenariosEditor._parse_chunk(chunk)
            if parsed is not None:
                entries.append(parsed)
        return entries

    @staticmethod
    def _split_scenario_chunks(text: str) -> list[str]:
        heading_matches = list(re.finditer(r"(?mi)^####\s+.+$", text))
        if heading_matches:
            chunks: list[str] = []
            for index, match in enumerate(heading_matches):
                start = match.start()
                end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(text)
                chunk = text[start:end].strip()
                if chunk:
                    chunks.append(chunk)
            return chunks

        return [chunk.strip() for chunk in re.split(r"(?mi)^\s*---+\s*$", text) if chunk.strip()]

    @staticmethod
    def _parse_chunk(chunk: str) -> TransitionScenarioData | None:
        image_matches = list(_IMAGE_RE.finditer(chunk))
        if not image_matches:
            return None

        images: list[TransitionScenarioImageData] = []
        for index, match in enumerate(image_matches):
            image_path = match.group(1).strip()
            start = match.end()
            end = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(chunk)
            image_section = chunk[start:end]

            timeframe_match = re.search(r"(?mi)^\s*(?:\*\*TF:\*\*|TF:)\s*(.+?)\s*$", image_section)
            timeframe = timeframe_match.group(1).strip() if timeframe_match else ""
            images.append(TransitionScenarioImageData(image_path=image_path, timeframe=timeframe))

        notation = TransitionScenariosEditor._extract_comment(chunk, "TRANSITION_NOTATION")
        if not notation:
            notation_match = re.search(r"(?is)Notation:\s*\n(.*?)(?:\n\s*Text:|\Z)", chunk)
            notation = notation_match.group(1).strip() if notation_match else ""

        meaning_notation = TransitionScenariosEditor._extract_comment(chunk, "TRANSITION_MEANING_NOTATION")
        why_text = TransitionScenariosEditor._extract_comment(chunk, "TRANSITION_WHY")

        if not why_text:
            why_section_match = re.search(r"(?is)\*\*(?:Why\?|Почему\?):\*\*\s*(.*)$", chunk)
            why_text = why_section_match.group(1).strip() if why_section_match else ""

        return TransitionScenarioData(
            images=images,
            notation=notation,
            meaning_notation=meaning_notation,
            why_text=why_text,
        )

    @staticmethod
    def _extract_comment(chunk: str, marker: str) -> str:
        match = re.search(rf"(?is)<!--\s*{re.escape(marker)}\s*(.*?)\s*-->", chunk)
        return match.group(1).strip() if match else ""

    def to_markdown(self) -> str:
        chunks = [entry.to_markdown(index + 1, self._base_dir) for index, entry in enumerate(self._entries)]
        return "\n\n---\n\n".join(chunks).strip()

    def has_content(self) -> bool:
        return bool(self._entries)

    def image_widgets(self) -> list[TransitionScenarioImageWidget]:
        widgets: list[TransitionScenarioImageWidget] = []
        for entry in self._entries:
            widgets.extend(entry.image_widgets())
        return widgets

    def scenario_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        for index, entry in enumerate(self._entries, start=1):
            data = entry.to_data()
            reference = data.notation.strip() or f"Сценарий #{index}"
            preview_source = data.notation.strip() or data.meaning_notation.strip() or data.why_text.strip()
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

        self._add_entry_widget(
            TransitionScenarioData(
                images=[TransitionScenarioImageData(image_path=image_file)],
            )
        )
        self._update_entry_titles()
        self._update_empty_state()
        self.content_changed.emit()

