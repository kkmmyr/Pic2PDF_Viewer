"""services/novel_db/chunker.py の単体テスト。"""
from services.novel_db.chunker import MAX_CHARS, chunk_page


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
