from __future__ import annotations

import json

import pytest
from PIL import Image, ImageDraw

from services.novel_db.surya_parsing import (
    SURYA_BLOCK_PROMPT,
    SURYA_LAYOUT_PROMPT,
    SURYA_PROMPT,
    parse_surya_layout,
)
from services.novel_db.surya_quality import evaluate_page_quality
from services.novel_db.surya_runtime import SuryaClient
from services.novel_db.surya_transport import SuryaTransport
from services.novel_db.surya_types import OcrSessionPolicy


def test_session_policy_restarts_at_page_limit() -> None:
    policy = OcrSessionPolicy(
        max_pages=3,
        consecutive_failure_limit=2,
        failure_window=4,
        failure_rate=0.75,
    )

    assert policy.record(False) is None
    assert policy.record(False) is None
    assert policy.record(False) == "page_limit"


def test_session_policy_restarts_after_consecutive_surya_failures() -> None:
    policy = OcrSessionPolicy(
        max_pages=24,
        consecutive_failure_limit=2,
        failure_window=8,
        failure_rate=0.5,
    )

    assert policy.record(True) is None
    assert policy.record(True) == "consecutive_surya_failures"


def test_session_policy_restarts_on_failure_rate() -> None:
    policy = OcrSessionPolicy(
        max_pages=24,
        consecutive_failure_limit=4,
        failure_window=4,
        failure_rate=0.5,
    )

    assert policy.record(True) is None
    assert policy.record(False) is None
    assert policy.record(True) is None
    assert policy.record(False) == "surya_failure_rate"


def test_structured_page_can_exempt_decoration_only_coverage_shortfall() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 40, 290), fill="black")
    draw.rectangle((100, 80, 180, 220), fill="black")
    raw = (
        '<div data-label="Section-Header" data-bbox="450 100 650 190">目次</div>'
        '<div data-label="Table-Of-Contents" data-bbox="450 200 950 800">目次の全項目</div>'
    )
    failed = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    result = SuryaClient._accept_structured_coverage(failed)

    assert result.state == "passed"
    assert "low_ink_coverage" in result.quality_flags
    assert "structured_page_coverage_exempt" in result.quality_flags


def test_sparse_page_accepts_matching_independent_variants() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 40, 290), fill="black")
    draw.rectangle((150, 20, 180, 280), fill="black")
    raw = '<div data-label="Text" data-bbox="700 50 950 950">イラスト / Izumi</div>'
    first = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)
    second = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=2)

    result = SuryaClient._accept_sparse_page(first, [first, second])

    assert result.state == "passed"
    assert "sparse_page_variant_consensus" in result.quality_flags


def test_sparse_page_prefers_clean_block_fallback_over_duplicate_candidate() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 40, 290), fill="black")
    duplicate_text = "同じ文章が誤って別列にも複製されている長い文章です"
    duplicate_raw = (
        f'<div data-label="Text" data-bbox="700 50 800 950">{duplicate_text}</div>'
        f'<div data-label="Text" data-bbox="850 50 950 950">{duplicate_text}</div>'
    )
    clean_raw = (
        '<div data-label="Text" data-bbox="700 50 800 950">正しい第一列です</div>'
        '<div data-label="Text" data-bbox="850 50 950 950">正しい第二列です</div>'
    )
    duplicate = evaluate_page_quality(image, duplicate_raw, min_ink_coverage=0.85, attempt_count=1)
    clean = evaluate_page_quality(image, clean_raw, min_ink_coverage=0.85, attempt_count=2)
    clean = SuryaClient._add_quality_flag(clean, "layout_block_fallback")

    best = max([duplicate, clean], key=SuryaClient._candidate_score)
    result = SuryaClient._accept_sparse_page(best, [duplicate, clean])

    assert result.state == "passed"
    assert "duplicate_text_block" not in result.quality_flags
    assert "sparse_page_block_fallback" in result.quality_flags


def test_task_drift_uses_official_block_fallback(monkeypatch) -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 180, 280), fill="black")
    client = SuryaClient("http://localhost/v1", "surya", 1, 0.85)
    calls: list[tuple[str, int]] = []

    def fake_recognize(_image, *, prompt=SURYA_PROMPT, max_tokens=12288):
        calls.append((prompt, max_tokens))
        if len(calls) == 1:
            return '[{"label":"Text","bbox":"50 50 950 950","count":200}]'
        return "<p>縦書き本文</p>"

    monkeypatch.setattr(client, "_recognize", fake_recognize)

    result = client.recognize_with_quality(image, max_attempts=1)

    assert result.state == "passed"
    assert result.full_text == "縦書き本文"
    assert "layout_block_fallback" in result.quality_flags
    assert calls[1] == (SURYA_BLOCK_PROMPT, 300)


def test_low_coverage_uses_explicit_layout_then_block_fallback(monkeypatch) -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 50, 280), fill="black")
    draw.rectangle((150, 20, 180, 280), fill="black")
    client = SuryaClient("http://localhost/v1", "surya", 1, 0.85)
    calls: list[tuple[str, int]] = []

    def fake_recognize(_image, *, prompt=SURYA_PROMPT, max_tokens=12288):
        calls.append((prompt, max_tokens))
        if prompt == SURYA_LAYOUT_PROMPT:
            return '[{"label":"Text","bbox":"50 50 950 950","count":100}]'
        if prompt == SURYA_BLOCK_PROMPT:
            return "本文"
        return '<div data-label="Text" data-bbox="50 50 300 950">欠落</div>'

    monkeypatch.setattr(client, "_recognize", fake_recognize)

    result = client.recognize_with_quality(image, max_attempts=1)

    assert result.state == "passed"
    assert result.full_text == "本文"
    assert result.attempt_count == 2
    assert "layout_block_fallback" in result.quality_flags
    assert (SURYA_LAYOUT_PROMPT, 3072) in calls


def test_openai_payload_places_image_before_prompt(monkeypatch) -> None:
    image = Image.new("RGB", (20, 30), "white")
    client = SuryaClient("http://localhost/v1", "surya", 1, 0.85)
    captured: dict = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"result"}}]}'

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        assert timeout == 1
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert client._recognize(image) == "result"
    content = captured["messages"][0]["content"]
    assert [part["type"] for part in content] == ["image_url", "text"]
    assert captured["top_p"] == 0.1
    assert captured["seed"] == 0


def test_transport_joins_openai_list_content() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "first"},
                        {"type": "text", "text": " second"},
                    ]
                }
            }
        ]
    }

    assert SuryaTransport._content(data) == "first second"


def test_transport_rejects_non_text_content() -> None:
    data = {"choices": [{"message": {"content": 42}}]}

    with pytest.raises(ValueError, match="response content is not text"):
        SuryaTransport._content(data)


def test_block_fallback_rejects_nested_layout_json(monkeypatch) -> None:
    image = Image.new("RGB", (200, 300), "white")
    client = SuryaClient("http://localhost/v1", "surya", 1, 0.85)
    layout = parse_surya_layout('[{"label":"Text","bbox":"50 50 950 950","count":100}]')

    def fake_recognize(_image, *, prompt=SURYA_PROMPT, max_tokens=12288):
        assert prompt == SURYA_BLOCK_PROMPT
        return '[{"label":"Text","bbox":"0 0 1000 1000","count":100}]'

    monkeypatch.setattr(client, "_recognize", fake_recognize)

    with pytest.raises(ValueError, match="block OCR returned layout JSON"):
        client._recognize_layout_blocks(image, layout)
