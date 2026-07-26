"""Surya OCRのHTML/layout出力解析。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

try:
    from .surya_types import SuryaBlock, SuryaLayoutBlock
except ImportError:  # Standalone ``python ocr_worker.py`` execution.
    from surya_types import SuryaBlock, SuryaLayoutBlock

SURYA_PROMPT = (
    "OCR this image to HTML. Each block is a div with data-label and data-bbox (x0 y0 x1 y1, normalized 0-1000)."
)
SURYA_LAYOUT_PROMPT = (
    'Output the layout of this image as JSON. Each entry is a dict with "label", '
    '"bbox", and "count" fields. Bbox is x0 y0 x1 y1, normalized 0-1000.'
)
SURYA_BLOCK_PROMPT = "OCR this block image to HTML."

CODE_FENCE_RE = re.compile(r"^\s*```(?:html)?\s*|\s*```\s*$", re.IGNORECASE)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_BBOX_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class _BlockBuilder:
    label: str
    bbox: tuple[float, float, float, float] | None
    text_parts: list[str]


class _SuryaHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._builders: list[_BlockBuilder] = []
        self._tag_stack: list[str] = []
        self.blocks: list[SuryaBlock] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "div":
            values = {key.lower(): value or "" for key, value in attrs}
            self._builders.append(
                _BlockBuilder(
                    label=values.get("data-label", "Text"),
                    bbox=parse_bbox(values.get("data-bbox", "")),
                    text_parts=[],
                )
            )
        elif tag == "br" and self._builders:
            self._builders[-1].text_parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "div" and self._builders:
            builder = self._builders.pop()
            if builder.bbox is not None:
                self.blocks.append(
                    SuryaBlock(
                        label=builder.label,
                        bbox=builder.bbox,
                        text=_normalize_block_text("".join(builder.text_parts)),
                    )
                )
        for index in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[index] == tag:
                del self._tag_stack[index]
                break

    def handle_data(self, data: str) -> None:
        if self._builders and "rt" not in self._tag_stack:
            self._builders[-1].text_parts.append(data)


def parse_bbox(value: str) -> tuple[float, float, float, float] | None:
    numbers = [float(item) for item in _BBOX_NUMBER_RE.findall(value)]
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _normalize_block_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_surya_html(raw_output: str) -> list[SuryaBlock]:
    """公式Surya GGUFのdiv出力を解析し、rubyのrt文字列を除外する。"""
    parser = _SuryaHtmlParser()
    parser.feed(CODE_FENCE_RE.sub("", raw_output.strip()))
    parser.close()
    return parser.blocks


def parse_surya_layout(raw_output: str) -> list[SuryaLayoutBlock]:
    """Surya layout task JSONと、誤って返されたtask drift出力を解析する。"""
    if parse_surya_html(raw_output):
        return []
    cleaned = CODE_FENCE_RE.sub("", raw_output.strip())
    match = _JSON_ARRAY_RE.search(cleaned)
    if match is None:
        return []
    try:
        payload = json.loads(match.group(0))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    blocks: list[SuryaLayoutBlock] = []
    for item in payload:
        if not isinstance(item, dict) or "label" not in item or "bbox" not in item:
            return []
        bbox = parse_bbox(str(item["bbox"]))
        if bbox is None:
            return []
        try:
            count = max(0, int(item.get("count", 0)))
        except (TypeError, ValueError):
            count = 0
        blocks.append(
            SuryaLayoutBlock(
                label=str(item["label"]),
                bbox=bbox,
                count=count,
            )
        )
    return blocks
