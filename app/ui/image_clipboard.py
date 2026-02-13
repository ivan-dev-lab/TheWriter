from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from PySide6.QtGui import QGuiApplication

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}


def image_path_from_clipboard() -> Path | None:
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:
        return None

    mime_data = clipboard.mimeData()
    if mime_data is None:
        return None

    if mime_data.hasUrls():
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in _IMAGE_EXTENSIONS and path.exists():
                return path

    image = clipboard.image()
    if image.isNull():
        pixmap = clipboard.pixmap()
        if pixmap.isNull():
            return None
        image = pixmap.toImage()
        if image.isNull():
            return None

    target_dir = Path(gettempdir()) / "thewriter_clipboard"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"clipboard_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}.png"
    if not image.save(str(target_path), "PNG"):
        return None
    return target_path
