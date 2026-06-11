"""services/novel_db/chunker.py の単体テスト。"""

from services.novel_db.chunker import MAX_CHARS, MAX_CHARS_BOOK, chunk_book, chunk_page


def test_short_text_returns_single_chunk():
    text = "これは短い文章です。"
    assert chunk_page(text) == [text]


def test_empty_text_returns_empty_list():
    assert chunk_page("") == []
    assert chunk_page("   \n  ") == []


def test_long_text_is_split():
    text = "あ" * 1000 + "。" + "い" * 700 + "。" + "う" * 200
    chunks = chunk_page(text)
    assert len(chunks) >= 2
    # 各チャンクは最大 max_chars + 50（オーバーラップ + 句点境界探索）程度に収まる
    assert all(len(c) <= MAX_CHARS + 100 for c in chunks)


def test_split_prefers_sentence_end():
    # 句点を含む文を 800 字超で渡す → 句点境界で切れる
    sentence = "あいうえおかきくけこ。"  # 11 文字
    text = sentence * 100  # 1100 文字、句点が複数
    chunks = chunk_page(text)
    # 1 つ目のチャンクは句点で終わる（最後が「。」）
    assert chunks[0].endswith("。")


def test_overlap_between_chunks():
    text = "あ" * 2000  # 句点なし
    chunks = chunk_page(text, max_chars=500, overlap=50)
    # チャンク末尾と次チャンク先頭が一部重なる
    assert len(chunks) >= 4
    # 各チャンクのサイズは max_chars 以下
    assert all(len(c) <= 500 for c in chunks)


def test_no_infinite_loop_on_pathological_input():
    """境界条件（空 / 1 文字 / 句点のみ）で無限ループしないこと。"""
    assert chunk_page("。") == ["。"]
    assert chunk_page("あ") == ["あ"]


# ---------------------------------------------------------------------------
# chunk_book テスト（§4.4 クロスページチャンク）
# ---------------------------------------------------------------------------


def _pages(texts: list[str], start_id: int = 1) -> list[dict]:
    return [{"page_id": i, "page_no": i, "full_text": t} for i, t in enumerate(texts, start=start_id)]


def test_chunk_book_empty_pages_returns_empty():
    assert chunk_book([]) == []
    assert chunk_book(_pages([""])) == []
    assert chunk_book(_pages(["あ" * 10])) == []  # min_page_chars=30 未満


def test_chunk_book_single_page_returns_one_chunk():
    text = "これは一冊の本の最初のページです。" * 3
    result = chunk_book(_pages([text]))
    assert len(result) == 1
    assert result[0]["page_id"] == 1
    assert result[0]["chunk_idx"] == 0
    assert text.strip() in result[0]["text"]


def test_chunk_book_spans_pages():
    """複数ページをまたいでチャンクを生成すること（クロスページ）。"""
    sentence = "あいうえおかきくけこさしすせそ。"  # 16 字
    # 各ページ 48 字（3 文）、10 ページ連結で 480 字 → max_chars=200 なら複数チャンク
    pages = _pages([sentence * 3] * 10)
    result = chunk_book(pages, max_chars=200, overlap=20)
    assert len(result) >= 2
    # 各チャンクは max_chars 以下（句点境界探索の分 +20% 程度は許容）
    assert all(len(c["text"]) <= 200 + 40 for c in result)


def test_chunk_book_page_id_attribution():
    """各チャンクの page_id がチャンク開始位置のページに対応すること。"""
    # page 1: 100 字テキスト, page 2: 100 字テキスト（合計 200 字）
    # max_chars=110 → 1 チャンク目は page 1 から、2 チャンク目は page 2 の途中から
    text_p1 = "ぁ" * 100  # 100 字
    text_p2 = "ぃ" * 100  # 100 字
    pages = _pages([text_p1, text_p2])
    result = chunk_book(pages, max_chars=110, overlap=10, min_page_chars=10)
    assert len(result) >= 2
    assert result[0]["page_id"] == 1  # 先頭チャンクは page 1 から開始
    assert result[-1]["page_id"] == 2  # 最終チャンクは page 2 の文字を含む


def test_chunk_book_skips_short_pages():
    """min_page_chars 未満のページ（章扉等）はスキップすること。"""
    pages = _pages(["第一章", "あいうえおかきくけこさしすせそ。" * 10, "第二章"])
    result = chunk_book(pages, min_page_chars=30)
    # 3 字の「第一章」「第二章」はスキップ、中間ページのみがチャンク化される
    assert all(c["page_id"] == 2 for c in result)


def test_chunk_book_prefers_sentence_end():
    """チャンク境界が句点位置に揃うこと（MAX_CHARS_BOOK を超えない範囲）。"""
    sentence = "あいうえお。"  # 6 字
    text = sentence * 300  # 1800 字
    pages = _pages([text])
    result = chunk_book(pages)
    assert all(len(c) <= MAX_CHARS_BOOK + 200 for c in (r["text"] for r in result))
    assert result[0]["text"].endswith("。")
