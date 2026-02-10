from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class AutoSaveController(QObject):
    save_requested = Signal(str)
    dirty_changed = Signal(bool)

    def __init__(self, debounce_ms: int = 1200, periodic_ms: int = 15000, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dirty = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(max(100, debounce_ms))
        self._debounce_timer.timeout.connect(lambda: self._emit_if_dirty("debounce"))

        self._periodic_timer = QTimer(self)
        self._periodic_timer.setSingleShot(False)
        self._periodic_timer.setInterval(max(1000, periodic_ms))
        self._periodic_timer.timeout.connect(lambda: self._emit_if_dirty("periodic"))

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.dirty_changed.emit(True)
        self._debounce_timer.start()
        if not self._periodic_timer.isActive():
            self._periodic_timer.start()

    def clear_dirty(self) -> None:
        if self._dirty:
            self._dirty = False
            self.dirty_changed.emit(False)
        self._debounce_timer.stop()
        self._periodic_timer.stop()

    def flush_now(self, reason: str = "manual") -> None:
        if self._dirty:
            self.save_requested.emit(reason)

    def _emit_if_dirty(self, reason: str) -> None:
        if self._dirty:
            self.save_requested.emit(reason)

