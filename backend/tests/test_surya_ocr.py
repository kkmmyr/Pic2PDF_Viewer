from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from services.novel_db.surya_ocr import (
    SURYA_BLOCK_PROMPT,
    SURYA_LAYOUT_PROMPT,
    SURYA_PROMPT,
    OcrSessionPolicy,
    SuryaBlock,
    SuryaClient,
    SuryaPageResult,
    SuryaServer,
    crosscheck_ocr_results,
    evaluate_external_ocr,
    evaluate_page_quality,
    parse_surya_html,
    parse_surya_layout,
)
from services.novel_db.surya_parsing import parse_surya_html as parsing_parse_surya_html
from services.novel_db.surya_quality import evaluate_page_quality as quality_evaluate_page_quality
from services.novel_db.surya_runtime import SuryaClient as RuntimeSuryaClient
from services.novel_db.surya_runtime import SuryaServer as RuntimeSuryaServer
from services.novel_db.surya_server import SuryaServer as ServerSuryaServer
from services.novel_db.surya_transport import SuryaTransport
from services.novel_db.surya_types import SuryaPageResult as TypesSuryaPageResult


def test_facade_preserves_public_symbol_identity() -> None:
    assert parse_surya_html is parsing_parse_surya_html
    assert evaluate_page_quality is quality_evaluate_page_quality
    assert SuryaClient is RuntimeSuryaClient
    assert SuryaServer is RuntimeSuryaServer
    assert SuryaServer is ServerSuryaServer
    assert SuryaPageResult is TypesSuryaPageResult


def test_facade_imports_in_standalone_worker_mode() -> None:
    module_dir = Path(__file__).resolve().parents[1] / "services" / "novel_db"
    completed = subprocess.run(
        [sys.executable, "-c", "import surya_ocr; print(surya_ocr.SuryaClient.__name__)"],
        cwd=module_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "SuryaClient"


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


def test_parse_surya_html_keeps_body_and_discards_ruby_reading() -> None:
    raw = '<div data-label="Text" data-bbox="100 100 900 900">彼女は<ruby>莉杏<rt>りあん</rt></ruby>と呼ばれた。</div>'

    blocks = parse_surya_html(raw)

    assert len(blocks) == 1
    assert blocks[0].text == "彼女は莉杏と呼ばれた。"
    assert blocks[0].bbox == (100.0, 100.0, 900.0, 900.0)


def test_quality_gate_rejects_text_outside_ocr_bbox() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 50, 280), fill="black")
    draw.rectangle((150, 20, 180, 280), fill="black")
    raw = '<div data-label="Text" data-bbox="50 50 300 950">本文</div>'

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "failed"
    assert "low_ink_coverage" in result.quality_flags


def test_quality_gate_accepts_blank_page_with_explicit_flag() -> None:
    image = Image.new("RGB", (200, 300), "white")

    result = evaluate_page_quality(image, "", min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "passed"
    assert result.quality_flags == ["blank_page"]


def test_quality_gate_rejects_nonempty_malformed_html() -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 180, 280), fill="black")

    result = evaluate_page_quality(
        image,
        '<div data-bbox="<div data-bbox="broken',
        min_ink_coverage=0.85,
        attempt_count=1,
    )

    assert result.state == "failed"
    assert "malformed_output" in result.quality_flags


def test_edge_coverage_accepts_white_text_on_uniform_black_background() -> None:
    image = Image.new("RGB", (200, 300), "black")
    ImageDraw.Draw(image).rectangle((80, 50, 120, 250), fill="white")
    raw = '<div data-label="Text" data-bbox="350 100 650 900">白抜き本文</div>'

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "passed"
    assert result.ink_coverage is not None and result.ink_coverage > 0.95


def test_quality_gate_rejects_long_text_duplicated_into_another_block() -> None:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 80, 280), fill="black")
    draw.rectangle((120, 20, 180, 280), fill="black")
    duplicated = "同一の長い文章が別の列へそのまま複製されています"
    raw = (
        f'<div data-label="Text" data-bbox="50 50 450 950">{duplicated}</div>'
        f'<div data-label="Text" data-bbox="550 50 950 950">{duplicated}</div>'
    )

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "failed"
    assert "duplicate_text_block" in result.quality_flags


def test_quality_gate_rejects_repeated_text_inside_one_block() -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 180, 280), fill="black")
    repeated = "陛下、同じ文章が繰り返されています。" * 5
    raw = f'<div data-label="Text" data-bbox="50 50 950 950">{repeated}</div>'

    result = evaluate_page_quality(image, raw, min_ink_coverage=0.85, attempt_count=1)

    assert result.state == "failed"
    assert "repeated_text" in result.quality_flags


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


def test_parse_surya_layout_detects_layout_task_output() -> None:
    raw = '[{"label":"Text","bbox":"100 20 900 980","count":250}]'

    blocks = parse_surya_layout(raw)

    assert len(blocks) == 1
    assert blocks[0].label == "Text"
    assert blocks[0].bbox == (100.0, 20.0, 900.0, 980.0)
    assert blocks[0].count == 250


def test_parse_surya_layout_does_not_reclassify_valid_html() -> None:
    raw = '<div data-label="Text" data-bbox="100 20 900 980">[{"label":"Text","bbox":"1 2 3 4","count":1}]</div>'

    assert parse_surya_layout(raw) == []


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


def test_external_ocr_adjudication_accepts_high_confidence_sparse_vertical_text() -> None:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((330, 20, 350, 280), fill="black")
    draw.rectangle((360, 20, 380, 280), fill="black")
    items = [
        {
            "text": "本作品 は縦書きでレイアウトされています 。",
            "confidence": 0.999,
            "position": [[330, 20], [350, 20], [350, 280], [330, 280]],
        },
        {
            "text": "表示の差が認められることがあります。",
            "confidence": 0.995,
            "position": [[360, 20], [380, 20], [380, 280], [360, 280]],
        },
    ]

    result = evaluate_external_ocr(
        image,
        items,
        min_ink_coverage=0.85,
        attempt_count=5,
        engine_flag="yomitoku_adjudication",
    )

    assert result.state == "passed"
    assert "yomitoku_adjudication" in result.quality_flags
    assert "本作品は縦書き" in result.full_text
    assert "作品 は" not in result.full_text


def test_external_ocr_adjudication_rejects_low_confidence_result() -> None:
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((150, 20, 180, 280), fill="black")
    items = [
        {
            "text": "不確かな本文",
            "confidence": 0.7,
            "position": [[150, 20], [180, 20], [180, 280], [150, 280]],
        }
    ]

    result = evaluate_external_ocr(
        image,
        items,
        min_ink_coverage=0.85,
        attempt_count=5,
        engine_flag="yomitoku_adjudication",
    )

    assert result.state == "failed"
    assert "external_ocr_low_confidence" in result.quality_flags


def test_external_ocr_adjudication_accepts_confidence_distribution_with_one_low_block() -> None:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    items = []
    for index, confidence in enumerate([0.99, 0.97, 0.95, 0.92, 0.40]):
        x0 = 350 - index * 50
        draw.rectangle((x0, 20, x0 + 30, 280), fill="black")
        items.append(
            {
                "text": f"十分な長さの縦書き本文です{index}" if confidence >= 0.9 else "短い注記",
                "confidence": confidence,
                "position": [[x0, 20], [x0 + 30, 20], [x0 + 30, 280], [x0, 280]],
            }
        )

    result = evaluate_external_ocr(
        image,
        items,
        min_ink_coverage=0.85,
        attempt_count=2,
        engine_flag="yomitoku_adjudication",
    )

    assert result.state == "passed"
    assert "external_ocr_distribution_accepted" in result.quality_flags


def _page_result(text: str, *, state: str = "passed") -> SuryaPageResult:
    return SuryaPageResult(
        full_text=text,
        raw_output="",
        blocks=[SuryaBlock("Text", (0, 0, 1000, 1000), text)],
        state=state,
        quality_flags=[],
        ink_coverage=1.0,
        attempt_count=1,
        error_message="failed" if state == "failed" else None,
    )


def test_crosscheck_prefers_more_complete_consistent_external_text() -> None:
    primary = _page_result("今はまだ踏みとどまれている。けれども、踏みとどま")
    external = _page_result("今はまだ踏みとどまれている。けれども、踏みとどまらなくていいのだ。")

    result = crosscheck_ocr_results(primary, external, min_similarity=0.7)

    assert result.state == "passed"
    assert result.full_text == external.full_text
    assert "external_ocr_more_complete" in result.quality_flags


def test_crosscheck_rejects_material_engine_disagreement() -> None:
    primary = _page_result("第一章。これは正しい本文です。")
    external = _page_result("目次。まったく異なる文字列です。")

    result = crosscheck_ocr_results(primary, external, min_similarity=0.85)

    assert result.state == "failed"
    assert "cross_engine_disagreement" in result.quality_flags
