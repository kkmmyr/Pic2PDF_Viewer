from __future__ import annotations

from services.novel_db.ocr_content_guards import detect_sample_boundary, has_suspicious_repetition


def test_detect_sample_boundary_from_late_explicit_marker() -> None:
    pages = [
        (3, "本書には電子特別お試し版を収録しています"),
        (70, "あとがき"),
        (84, "紅茶執事のお嬢様 電子特別お試し版"),
        (85, "第一章 新しい物語"),
    ]

    assert detect_sample_boundary(pages, page_count=105) == 84


def test_detect_sample_boundary_ignores_front_matter_notice() -> None:
    pages = [
        (3, "巻末に試し読み版を収録しています"),
        (40, "本文"),
        (79, "物語の終わり"),
    ]

    assert detect_sample_boundary(pages, page_count=80) is None


def test_detect_sample_boundary_from_second_toc_after_afterword() -> None:
    pages = [
        (71, "あとがき"),
        (72, "著者紹介"),
        (75, "目次\n第一章\n第二章\n第三章"),
        (76, "第一章 別の物語"),
    ]

    assert detect_sample_boundary(pages, page_count=86) == 75


def test_detect_sample_boundary_does_not_treat_late_chapters_as_sample() -> None:
    pages = [
        (60, "第八章"),
        (70, "第九章"),
        (80, "終章"),
    ]

    assert detect_sample_boundary(pages, page_count=82) is None


def test_repetition_detects_repeated_long_line() -> None:
    assert has_suspicious_repetition("\n".join(["茉莉花は静かに書類へ目を落とした。"] * 3))


def test_repetition_detects_same_long_line_twice() -> None:
    line = (
        "茉莉花は官吏たちの報告を読み、問題の原因と解決策を一つずつ丁寧に書き出し、"
        "関係者へ確認する順番まで整理していった。"
    )
    assert has_suspicious_repetition(f"{line}\n別の文章です。\n{line}")


def test_repetition_detects_repeated_two_line_block() -> None:
    block = [
        "これは十分に長い一行目の文章として扱われます。",
        "こちらも十分に長い二行目の文章として扱われます。",
    ]
    assert has_suspicious_repetition("\n".join([*block, "間の文章", *block]))


def test_repetition_detects_inline_generation_loop() -> None:
    repeated_phrase = "それを先を豊かにすることが"

    assert has_suspicious_repetition(f"本文の始まり。{repeated_phrase * 8}本文の終わり。")


def test_repetition_allows_inline_phrase_below_loop_threshold() -> None:
    repeated_phrase = "それを先を豊かにすることが"

    assert not has_suspicious_repetition(repeated_phrase * 7)


def test_repetition_ignores_short_dialogue_and_normal_prose() -> None:
    text = "\n".join(["はい", "はい", "はい", "茉莉花は書類を読んだ。", "珀陽は窓の外を見た。"])
    assert not has_suspicious_repetition(text)


def test_repetition_ignores_alternating_blank_lines() -> None:
    text = "\n".join(["茉莉花は大虎へ報告した。", "", "茉莉花は大虎へ報告した。"])
    assert not has_suspicious_repetition(text)


def test_repetition_ignores_intentional_short_onomatopoeia() -> None:
    assert not has_suspicious_repetition("\n".join(["コンコン……カサカサ……"] * 4))
