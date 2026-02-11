from __future__ import annotations

from dataclasses import dataclass
import re

SECTION_DEFINITIONS: list[tuple[str, str]] = [
    ("1. Описание текущей ситуации", "block1"),
    ("2. Описание сценариев перехода к сделкам", "block2"),
    ("3. Описание сценариев сделок", "block3"),
]

_TITLE_RE = re.compile(r"(?m)^\s*#\s+(.+?)\s*$")
_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_IMAGE_LINE_RE = re.compile(r"^!\[[^\]]*]\([^)]+\)\s*$")


def _normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


_CANONICAL_BY_HEADING = {_normalize_heading(heading): key for heading, key in SECTION_DEFINITIONS}
_CANONICAL_ORDER = [_normalize_heading(heading) for heading, _ in SECTION_DEFINITIONS]


@dataclass(slots=True)
class TradingPlan:
    title: str
    block1: str = ""
    block2: str = ""
    block3: str = ""
    extras: str = ""
    raw_markdown: str = ""
    structured: bool = True

    @classmethod
    def empty(cls, title: str = "Новый торговый план") -> "TradingPlan":
        return cls(title=title.strip() or "Новый торговый план")

    @classmethod
    def from_markdown(cls, markdown: str, fallback_title: str = "Без названия") -> "TradingPlan":
        text = markdown.replace("\r\n", "\n").replace("\r", "\n")
        title_match = _TITLE_RE.search(text)
        title = title_match.group(1).strip() if title_match else fallback_title

        h2_matches = list(_H2_RE.finditer(text))
        if not h2_matches:
            return cls(title=title, raw_markdown=text, structured=False)

        sections: dict[str, str] = {}
        extras_chunks: list[str] = []

        prefix_start = title_match.end() if title_match else 0
        prefix = text[prefix_start : h2_matches[0].start()]
        if prefix.strip():
            extras_chunks.append(prefix.strip("\n"))

        encountered_canonical: list[str] = []

        for index, match in enumerate(h2_matches):
            heading = match.group(1).strip()
            normalized = _normalize_heading(heading)
            body_start = match.end()
            body_end = h2_matches[index + 1].start() if index + 1 < len(h2_matches) else len(text)
            body = text[body_start:body_end].strip("\n")

            canonical_key = _CANONICAL_BY_HEADING.get(normalized)
            if canonical_key is not None and canonical_key not in sections:
                sections[canonical_key] = body
                encountered_canonical.append(normalized)
                continue

            extra_section = f"## {heading}\n"
            if body:
                extra_section += f"{body.rstrip()}\n"
            extras_chunks.append(extra_section.strip("\n"))

        structured = all(key in sections for _, key in SECTION_DEFINITIONS)
        if structured:
            position = -1
            for canonical_heading in _CANONICAL_ORDER:
                try:
                    next_pos = encountered_canonical.index(canonical_heading, position + 1)
                except ValueError:
                    structured = False
                    break
                position = next_pos

        if not structured:
            return cls(title=title, raw_markdown=text, structured=False)

        extras = "\n\n".join(chunk for chunk in extras_chunks if chunk.strip())
        return cls(
            title=title,
            block1=sections.get("block1", ""),
            block2=sections.get("block2", ""),
            block3=sections.get("block3", ""),
            extras=extras,
            raw_markdown=text,
            structured=True,
        )

    @classmethod
    def normalize_raw(cls, raw_markdown: str, title: str) -> "TradingPlan":
        return cls(
            title=title.strip() or "Новый торговый план",
            block1=raw_markdown.strip("\n"),
            block2="",
            block3="",
            extras="",
            raw_markdown="",
            structured=True,
        )

    def to_markdown(self) -> str:
        title = self.title.strip() or "Без названия"
        lines: list[str] = [f"# {title}", ""]

        for heading, key in SECTION_DEFINITIONS:
            body = getattr(self, key, "").strip("\n")
            lines.append(f"## {heading}")
            if body:
                lines.append(body)
            lines.append("")

        extras = self.extras.strip("\n")
        if extras:
            lines.append(extras)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


def apply_title_to_markdown(markdown: str, title: str) -> str:
    clean_title = title.strip() or "Без названия"
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    if _TITLE_RE.search(text):
        replaced = _TITLE_RE.sub(f"# {clean_title}", text, count=1)
        return replaced.rstrip() + "\n"

    if text.strip():
        return f"# {clean_title}\n\n{text.lstrip(chr(10)).rstrip()}\n"

    return f"# {clean_title}\n\n"


def find_first_image_without_text(markdown_block: str) -> int | None:
    lines = markdown_block.splitlines()

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not _IMAGE_LINE_RE.match(line):
            continue

        has_text_below = False
        for next_raw in lines[index + 1 :]:
            next_line = next_raw.strip()
            if not next_line:
                continue
            if _IMAGE_LINE_RE.match(next_line):
                break
            has_text_below = True
            break

        if not has_text_below:
            return index + 1

    return None
