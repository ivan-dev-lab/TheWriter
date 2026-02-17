from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .current_situation import ELEMENT_OPTIONS, TIMEFRAME_OPTIONS
from .deal_scenarios import DealScenarioData, DealScenarioImageData
from .transition_scenarios import (
    TransitionScenarioData,
    TransitionScenarioImageData,
    transition_meaning_notation_to_text,
    transition_notation_to_text,
)

_DEFAULT_ZONES = ["Premium", "Discount", "Equilibrium"]


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass(slots=True)
class ScenarioTemplate:
    file_path: Path
    template_id: str
    name: str
    description: str
    image_path: Path
    random_options: dict[str, list[str]]
    defaults: dict[str, str]
    text_templates: dict[str, str]

    @property
    def file_label(self) -> str:
        return self.file_path.name

    @staticmethod
    def from_file(path: Path) -> ScenarioTemplate | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        template_id = str(payload.get("id") or path.stem).strip() or path.stem
        name = str(payload.get("name") or path.stem).strip() or path.stem
        description = str(payload.get("description") or "").strip()
        image_raw = str(payload.get("image") or "").strip()
        image_path = (path.parent / image_raw).resolve() if image_raw else Path("")

        random_options_raw = payload.get("random_options")
        if not isinstance(random_options_raw, dict):
            random_options_raw = {}

        normalized_random: dict[str, list[str]] = {}
        for key, values in random_options_raw.items():
            if not isinstance(values, list):
                continue
            normalized_values = [str(item).strip() for item in values if str(item).strip()]
            if normalized_values:
                normalized_random[str(key)] = normalized_values

        defaults_raw = payload.get("defaults")
        if not isinstance(defaults_raw, dict):
            defaults_raw = {}
        defaults = {str(key): str(value).strip() for key, value in defaults_raw.items()}

        text_templates_raw = payload.get("text_templates")
        if not isinstance(text_templates_raw, dict):
            text_templates_raw = {}
        text_templates = {str(key): str(value) for key, value in text_templates_raw.items()}

        return ScenarioTemplate(
            file_path=path,
            template_id=template_id,
            name=name,
            description=description,
            image_path=image_path,
            random_options=normalized_random,
            defaults=defaults,
            text_templates=text_templates,
        )


def load_scenario_templates(directory: Path | None = None) -> list[ScenarioTemplate]:
    templates_dir = directory or (Path(__file__).resolve().parent / "templates")
    if not templates_dir.exists():
        return []

    items: list[ScenarioTemplate] = []
    for template_file in sorted(templates_dir.glob("*.json")):
        template = ScenarioTemplate.from_file(template_file)
        if template is not None:
            items.append(template)
    return items


@dataclass(slots=True)
class TemplateApplyResult:
    transition_data: TransitionScenarioData
    deal_data: DealScenarioData


class ScenarioTemplateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Использовать шаблоны")
        self.resize(1120, 760)
        self.setModal(True)

        self._templates = load_scenario_templates()
        self._current_template: ScenarioTemplate | None = None
        self._result: TemplateApplyResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left_container = QWidget(splitter)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("Шаблоны (файлы)"))
        self.templates_list = QListWidget(left_container)
        left_layout.addWidget(self.templates_list, 1)
        splitter.addWidget(left_container)

        right_container = QWidget(splitter)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        right_layout.addWidget(self.title_label)

        self.preview_image = QLabel("Изображение шаблона не найдено")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview_image.setMinimumHeight(220)
        self.preview_image.setStyleSheet("QLabel { border: 1px solid #d8dde6; border-radius: 6px; }")
        right_layout.addWidget(self.preview_image)

        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        right_layout.addWidget(self.description_label)

        self.description_source_label = QLabel("")
        self.description_source_label.setObjectName("muted")
        self.description_source_label.setWordWrap(True)
        right_layout.addWidget(self.description_source_label)

        controls = QWidget(right_container)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        left_form_widget = QWidget(controls)
        left_form = QFormLayout(left_form_widget)
        left_form.setContentsMargins(0, 0, 0, 0)
        left_form.setSpacing(6)

        self.break_sign = QComboBox()
        self.break_tf = QComboBox()
        self.break_element = QComboBox()
        self.break_range_kind = QComboBox()
        self.break_range_sign = QComboBox()
        self.break_range_tf = QComboBox()
        self.break_range_zone = QComboBox()

        self.ineff_sign = QComboBox()
        self.ineff_tf = QComboBox()
        self.ineff_element = QComboBox()
        self.ineff_range_kind = QComboBox()
        self.ineff_range_sign = QComboBox()
        self.ineff_range_tf = QComboBox()
        self.ineff_range_zone = QComboBox()

        self.meaning_side = QComboBox()
        self.meaning_level = QComboBox()
        self.meaning_range_kind = QComboBox()
        self.meaning_range_sign = QComboBox()
        self.meaning_range_tf = QComboBox()
        self.meaning_range_zone = QComboBox()

        left_form.addRow("Пробой: направление", self.break_sign)
        left_form.addRow("Пробой: TF", self.break_tf)
        left_form.addRow("Пробой: элемент", self.break_element)
        left_form.addRow("Пробой: диапазон", self._row_widget(self.break_range_kind, self.break_range_sign, self.break_range_tf, self.break_range_zone))

        left_form.addRow("Неэффективность: направление", self.ineff_sign)
        left_form.addRow("Неэффективность: TF", self.ineff_tf)
        left_form.addRow("Неэффективность: элемент", self.ineff_element)
        left_form.addRow("Неэффективность: диапазон", self._row_widget(self.ineff_range_kind, self.ineff_range_sign, self.ineff_range_tf, self.ineff_range_zone))

        left_form.addRow("ADV: BUY/SELL", self.meaning_side)
        left_form.addRow("ADV: UP/DOWN", self.meaning_level)
        left_form.addRow("ADV: диапазон", self._row_widget(self.meaning_range_kind, self.meaning_range_sign, self.meaning_range_tf, self.meaning_range_zone))

        controls_layout.addWidget(left_form_widget, 1)

        right_form_widget = QWidget(controls)
        right_form = QFormLayout(right_form_widget)
        right_form.setContentsMargins(0, 0, 0, 0)
        right_form.setSpacing(6)

        self.idea_edit = self._create_text_edit(72)
        self.entry_edit = self._create_text_edit(72)
        self.sl_edit = self._create_text_edit(72)
        self.tp_edit = self._create_text_edit(72)

        self.transition_notation_preview = self._create_text_edit(52, read_only=True)
        self.meaning_notation_preview = self._create_text_edit(52, read_only=True)
        self.transition_text_preview = self._create_text_edit(78, read_only=True)
        self.meaning_text_preview = self._create_text_edit(78, read_only=True)

        right_form.addRow("Идея сделки", self.idea_edit)
        right_form.addRow("Entry", self.entry_edit)
        right_form.addRow("SL", self.sl_edit)
        right_form.addRow("TP", self.tp_edit)
        right_form.addRow("Нотация перехода", self.transition_notation_preview)
        right_form.addRow("Нотация значения", self.meaning_notation_preview)
        right_form.addRow("Текст перехода", self.transition_text_preview)
        right_form.addRow("Текст значения", self.meaning_text_preview)

        controls_layout.addWidget(right_form_widget, 1)
        right_layout.addWidget(controls, 1)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self.cancel_button = QPushButton("Отмена")
        self.apply_button = QPushButton("Использовать этот шаблон")
        buttons_row.addWidget(self.cancel_button)
        buttons_row.addWidget(self.apply_button)
        right_layout.addLayout(buttons_row)

        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 800])

        self._connect_signals()
        self._load_templates_to_list()

    def selected_result(self) -> TemplateApplyResult | None:
        return self._result

    def _connect_signals(self) -> None:
        self.templates_list.currentRowChanged.connect(self._on_template_selected)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._apply_template)

        combos = [
            self.break_sign,
            self.break_tf,
            self.break_element,
            self.break_range_kind,
            self.break_range_sign,
            self.break_range_tf,
            self.break_range_zone,
            self.ineff_sign,
            self.ineff_tf,
            self.ineff_element,
            self.ineff_range_kind,
            self.ineff_range_sign,
            self.ineff_range_tf,
            self.ineff_range_zone,
            self.meaning_side,
            self.meaning_level,
            self.meaning_range_kind,
            self.meaning_range_sign,
            self.meaning_range_tf,
            self.meaning_range_zone,
        ]
        for combo in combos:
            combo.currentIndexChanged.connect(self._update_notation_previews)

    def _load_templates_to_list(self) -> None:
        self.templates_list.clear()
        for template in self._templates:
            item = QListWidgetItem(template.file_label)
            item.setData(Qt.ItemDataRole.UserRole, template.template_id)
            item.setToolTip(template.name)
            self.templates_list.addItem(item)

        has_templates = bool(self._templates)
        self.apply_button.setEnabled(has_templates)
        if has_templates:
            self.templates_list.setCurrentRow(0)
        else:
            self.title_label.setText("Шаблоны не найдены")
            self.description_label.setText("Добавьте json-файлы в папку app/ui/templates.")
            self.description_source_label.clear()

    def _on_template_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._templates):
            return
        self._current_template = self._templates[row]
        self._render_template(self._current_template)
        self._fill_random_values(self._current_template)
        self._apply_default_texts(self._current_template)
        self._update_notation_previews()

    def _render_template(self, template: ScenarioTemplate) -> None:
        self.title_label.setText(template.name)
        self.description_label.setText(template.description)
        self.description_source_label.setText(
            f"Описание шаблона редактируется в: {template.file_path.as_posix()} (поле description)"
        )
        if template.image_path and template.image_path.exists():
            pixmap = QPixmap(str(template.image_path))
            if not pixmap.isNull():
                scaled = pixmap.scaledToWidth(680, Qt.TransformationMode.SmoothTransformation)
                if scaled.height() > 320:
                    scaled = scaled.scaledToHeight(320, Qt.TransformationMode.SmoothTransformation)
                self.preview_image.setText("")
                self.preview_image.setPixmap(scaled)
                return
        self.preview_image.setPixmap(QPixmap())
        self.preview_image.setText("Изображение шаблона не найдено")

    def _fill_random_values(self, template: ScenarioTemplate) -> None:
        options = template.random_options
        signs = options.get("signs", ["+", "-"])
        tfs = options.get("timeframes", [item.upper() for item in TIMEFRAME_OPTIONS])
        elements = options.get("elements", ELEMENT_OPTIONS)
        zones = options.get("zones", _DEFAULT_ZONES)
        sides = options.get("sides", ["SELL", "BUY"])
        levels = options.get("levels", ["UP", "DOWN"])
        range_kinds = options.get("range_kinds", ["ACTUAL", "PREV"])

        self._fill_combo(self.break_sign, signs, random.choice(signs))
        self._fill_combo(self.break_tf, tfs, random.choice(tfs))
        self._fill_combo(self.break_element, elements, random.choice(elements))
        self._fill_combo(self.break_range_kind, range_kinds, template.defaults.get("breakout_range_kind", "PREV"))
        self._fill_combo(self.break_range_sign, signs, random.choice(signs))
        self._fill_combo(self.break_range_tf, tfs, random.choice(tfs))
        self._fill_combo(self.break_range_zone, zones, random.choice(zones))

        self._fill_combo(self.ineff_sign, signs, random.choice(signs))
        self._fill_combo(self.ineff_tf, tfs, random.choice(tfs))
        self._fill_combo(self.ineff_element, elements, random.choice(elements))
        self._fill_combo(self.ineff_range_kind, range_kinds, template.defaults.get("inefficiency_range_kind", "ACTUAL"))
        self._fill_combo(self.ineff_range_sign, signs, random.choice(signs))
        self._fill_combo(self.ineff_range_tf, tfs, random.choice(tfs))
        self._fill_combo(self.ineff_range_zone, zones, random.choice(zones))

        self._fill_combo(self.meaning_side, sides, random.choice(sides))
        self._fill_combo(self.meaning_level, levels, random.choice(levels))
        self._fill_combo(
            self.meaning_range_kind,
            range_kinds,
            random.choice(range_kinds),
        )
        self._fill_combo(self.meaning_range_sign, signs, random.choice(signs))
        self._fill_combo(self.meaning_range_tf, tfs, random.choice(tfs))
        self._fill_combo(self.meaning_range_zone, zones, random.choice(zones))

    def _apply_default_texts(self, template: ScenarioTemplate) -> None:
        context = self._template_context()
        self.idea_edit.setPlainText(template.text_templates.get("idea", "").format_map(_SafeDict(context)).strip())
        self.entry_edit.setPlainText(template.text_templates.get("entry", "").format_map(_SafeDict(context)).strip())
        self.sl_edit.setPlainText(template.text_templates.get("sl", "").format_map(_SafeDict(context)).strip())
        self.tp_edit.setPlainText(template.text_templates.get("tp", "").format_map(_SafeDict(context)).strip())

    def _update_notation_previews(self) -> None:
        transition_notation, meaning_notation = self._build_notations()
        transition_text, transition_error = transition_notation_to_text(transition_notation)
        meaning_text, meaning_error = transition_meaning_notation_to_text(meaning_notation)

        self.transition_notation_preview.setPlainText(transition_notation)
        self.meaning_notation_preview.setPlainText(meaning_notation)

        if transition_error:
            self.transition_text_preview.setPlainText(f"Ошибка: {transition_error}")
        else:
            self.transition_text_preview.setPlainText((transition_text or "").strip())

        if meaning_error:
            self.meaning_text_preview.setPlainText(f"Ошибка: {meaning_error}")
        else:
            self.meaning_text_preview.setPlainText((meaning_text or "").strip())

    def _apply_template(self) -> None:
        template = self._current_template
        if template is None:
            QMessageBox.warning(self, "Шаблоны", "Выберите шаблон.")
            return

        transition_notation, meaning_notation = self._build_notations()
        transition_text, transition_error = transition_notation_to_text(transition_notation)
        if transition_error or not transition_text:
            QMessageBox.warning(self, "Шаблоны", transition_error or "Некорректная нотация перехода.")
            return

        meaning_text, meaning_error = transition_meaning_notation_to_text(meaning_notation)
        if meaning_error or not meaning_text:
            QMessageBox.warning(self, "Шаблоны", meaning_error or "Некорректная нотация смысла.")
            return

        context = self._template_context()
        why_text = template.text_templates.get("why", "").format_map(_SafeDict(context)).strip()
        image_path = str(template.image_path) if template.image_path else ""
        deal_timeframe = self.break_tf.currentData() or self.break_tf.currentText()

        transition_data = TransitionScenarioData(
            images=[TransitionScenarioImageData(image_path=image_path, timeframe=str(deal_timeframe))],
            notation=transition_notation,
            scenario_text=transition_text.strip(),
            meaning_notation=meaning_notation,
            meaning_text=meaning_text.strip(),
            why_text=why_text,
        )

        deal_data = DealScenarioData(
            images=[DealScenarioImageData(image_path=image_path)],
            timeframe=str(deal_timeframe),
            transition_ref=transition_notation,
            idea=self.idea_edit.toPlainText().strip(),
            entry=self.entry_edit.toPlainText().strip(),
            sl=self.sl_edit.toPlainText().strip(),
            tp=self.tp_edit.toPlainText().strip(),
        )

        self._result = TemplateApplyResult(transition_data=transition_data, deal_data=deal_data)
        self.accept()

    def _build_notations(self) -> tuple[str, str]:
        break_sign = self.break_sign.currentData() or self.break_sign.currentText()
        break_tf = self.break_tf.currentData() or self.break_tf.currentText()
        break_element = self.break_element.currentData() or self.break_element.currentText()
        break_range_kind = self.break_range_kind.currentData() or self.break_range_kind.currentText()
        break_range_sign = self.break_range_sign.currentData() or self.break_range_sign.currentText()
        break_range_tf = self.break_range_tf.currentData() or self.break_range_tf.currentText()
        break_range_zone = self.break_range_zone.currentData() or self.break_range_zone.currentText()

        ineff_sign = self.ineff_sign.currentData() or self.ineff_sign.currentText()
        ineff_tf = self.ineff_tf.currentData() or self.ineff_tf.currentText()
        ineff_element = self.ineff_element.currentData() or self.ineff_element.currentText()
        ineff_range_kind = self.ineff_range_kind.currentData() or self.ineff_range_kind.currentText()
        ineff_range_sign = self.ineff_range_sign.currentData() or self.ineff_range_sign.currentText()
        ineff_range_tf = self.ineff_range_tf.currentData() or self.ineff_range_tf.currentText()
        ineff_range_zone = self.ineff_range_zone.currentData() or self.ineff_range_zone.currentText()

        side = self.meaning_side.currentData() or self.meaning_side.currentText()
        level = self.meaning_level.currentData() or self.meaning_level.currentText()
        meaning_range_kind = self.meaning_range_kind.currentData() or self.meaning_range_kind.currentText()
        meaning_range_sign = self.meaning_range_sign.currentData() or self.meaning_range_sign.currentText()
        meaning_range_tf = self.meaning_range_tf.currentData() or self.meaning_range_tf.currentText()
        meaning_range_zone = self.meaning_range_zone.currentData() or self.meaning_range_zone.currentText()

        transition_notation = (
            "CREATE "
            f"{break_sign} {str(break_tf).upper()} {break_element} "
            f"{str(break_range_kind).upper()} {break_range_sign} {str(break_range_tf).upper()} DR {break_range_zone} "
            "WITH "
            f"{ineff_sign} {str(ineff_tf).upper()} {ineff_element} "
            f"{str(ineff_range_kind).upper()} {ineff_range_sign} {str(ineff_range_tf).upper()} DR {ineff_range_zone} "
            "BREAK"
        )
        meaning_notation = (
            "ADV "
            f"{str(side).upper()} {str(level).upper()} "
            f"{str(meaning_range_kind).upper()} {meaning_range_sign} {str(meaning_range_tf).upper()} DR {meaning_range_zone}"
        )
        return transition_notation, meaning_notation

    def _template_context(self) -> dict[str, Any]:
        transition_notation, meaning_notation = self._build_notations()
        transition_text, _ = transition_notation_to_text(transition_notation)
        meaning_text, _ = transition_meaning_notation_to_text(meaning_notation)
        return {
            "template_name": self._current_template.name if self._current_template else "",
            "transition_notation": transition_notation,
            "meaning_notation": meaning_notation,
            "transition_text": (transition_text or "").strip(),
            "meaning_text": (meaning_text or "").strip(),
            "breakout_tf": str(self.break_tf.currentData() or self.break_tf.currentText()).upper(),
            "inefficiency_tf": str(self.ineff_tf.currentData() or self.ineff_tf.currentText()).upper(),
            "breakout_element": str(self.break_element.currentData() or self.break_element.currentText()),
            "inefficiency_element": str(self.ineff_element.currentData() or self.ineff_element.currentText()),
            "side": str(self.meaning_side.currentData() or self.meaning_side.currentText()).upper(),
            "level": str(self.meaning_level.currentData() or self.meaning_level.currentText()).upper(),
        }

    @staticmethod
    def _create_text_edit(min_height: int, read_only: bool = False) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setMinimumHeight(min_height)
        edit.setReadOnly(read_only)
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return edit

    @staticmethod
    def _fill_combo(combo: QComboBox, values: list[str], selected: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for value in values:
            combo.addItem(value, value)
        index = combo.findData(selected)
        if index < 0 and values:
            index = 0
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    @staticmethod
    def _row_widget(*widgets: QWidget) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        for widget in widgets:
            row_layout.addWidget(widget)
        return row
