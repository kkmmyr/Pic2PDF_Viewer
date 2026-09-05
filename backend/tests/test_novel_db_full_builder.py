"""services/novel_db/full_builder.py の単体テスト。

外部LLMはモック化し、スキップ条件・コールバック呼び出し・
DB書き込みロジックのみを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.novel_db import with_db
from services.novel_db.full_builder import (
    _run_combined_step,
    build_book_full,
)
from services.novel_db.migrations import upgrade_head
from services.novel_db.summary_grounding import GroundingError


@pytest.fixture
def db_conn(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        yield conn


def _insert_book(
    conn,
    name: str,
    summary: str | None = None,
    catalog_summary: str | None = None,
) -> int:
    if summary is not None and catalog_summary is None:
        catalog_summary = "既存の一覧向け要約"
    cur = conn.execute(
        """
        INSERT INTO books
            (name, pdf_path, images_dir, page_count, indexed_at, summary, catalog_summary)
        VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
        """,
        (name, f"/{name}.pdf", "/imgs", 10, summary, catalog_summary),
    )
    conn.commit()
    return cur.lastrowid


def _insert_page(conn, book_id: int, page_no: int, text: str) -> int:
    cur = conn.execute(
        "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
        (book_id, page_no, None, text, len(text)),
    )
    conn.commit()
    return cur.lastrowid


class TestRunCombinedStep:
    """_run_combined_step のスキップ条件と正常フローを検証する。"""

    def test_skips_when_book_not_found(self, db_conn):
        logs = []
        _run_combined_step(db_conn, "no-such-book", redo=False, log=logs.append)
        assert any("skip" in m for m in logs)

    def test_skips_when_summary_and_chars_exist(self, db_conn):
        book_id = _insert_book(db_conn, "mybook", summary="既存サマリ")
        # book_characters に summary 付きレコードを追加
        db_conn.execute(
            "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, "キャラA", "説明", 1, 5),
        )
        db_conn.commit()

        logs = []
        with patch("services.novel_db.full_builder.summarize_book_with_characters") as mock_sum:
            _run_combined_step(db_conn, "mybook", redo=False, log=logs.append)
            mock_sum.assert_not_called()

        assert any("skip" in m for m in logs)

    def test_redo_true_replaces_existing_generated_content(self, db_conn):
        """redo=True なら既存のサマリ・キャラクタがあっても実行する。"""
        book_id = _insert_book(db_conn, "mybook2", summary="古いサマリ")
        _insert_page(db_conn, book_id, 1, "キャラは行動した。")
        db_conn.execute(
            "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, "キャラ", "説明", 1, 3),
        )
        db_conn.commit()

        logs = []
        mock_summarize = MagicMock(return_value=("新サマリ", "新しい一覧向け要約", {"キャラ": "キャラは行動した。"}))
        with (
            patch("services.novel_db.full_builder.summarize_book_with_characters", mock_summarize),
            patch("services.novel_db.full_builder.index_book_summary"),
        ):
            _run_combined_step(db_conn, "mybook2", redo=True, log=logs.append)

        mock_summarize.assert_called_once()
        row = db_conn.execute(
            "SELECT summary, catalog_summary FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        assert row[0] == "新サマリ"
        assert row[1] == "新しい一覧向け要約"

    def test_characters_are_inserted_to_db(self, db_conn):
        """summarize_book_with_characters が返したキャラクターが DB に INSERT される。"""
        book_id = _insert_book(db_conn, "charbook")
        _insert_page(db_conn, book_id, 1, "アリスはふしぎの国の住人")

        char_summaries = {"アリス": "主人公の少女"}
        mock_summarize = MagicMock(return_value=("本のサマリ", "一覧向け要約", char_summaries))

        with (
            patch("services.novel_db.full_builder.summarize_book_with_characters", mock_summarize),
            patch("services.novel_db.full_builder.index_book_summary"),
        ):
            _run_combined_step(db_conn, "charbook", redo=False, log=lambda _: None)

        chars = db_conn.execute("SELECT name FROM book_characters WHERE book_id = ?", (book_id,)).fetchall()
        assert [r[0] for r in chars] == ["アリス"]

    def test_characters_are_normalized_merged_and_require_page_evidence(self, db_conn):
        book_id = _insert_book(db_conn, "guarded-charbook")
        _insert_page(db_conn, book_id, 3, "第一皇子 守伸は茉莉花に書類を渡した。")
        _insert_page(db_conn, book_id, 8, "守伸殿は静かにうなずいた。")

        char_summaries = {
            "第一皇子 守伸": "第一皇子。",
            "守伸殿": "茉莉花を支える。",
            "幻の人物": "本文には存在しない。",
            "国王陛下": "匿名の役職。",
        }
        mock_summarize = MagicMock(return_value=("本のサマリ", "一覧向け要約", char_summaries))
        logs: list[str] = []

        with (
            patch("services.novel_db.full_builder.summarize_book_with_characters", mock_summarize),
            patch("services.novel_db.full_builder.index_book_summary"),
        ):
            _run_combined_step(db_conn, "guarded-charbook", redo=False, log=logs.append)

        chars = db_conn.execute(
            "SELECT name, summary, first_page, page_count FROM book_characters WHERE book_id = ?",
            (book_id,),
        ).fetchall()
        assert [tuple(row) for row in chars] == [
            ("守伸", "第一皇子。\n茉莉花を支える。", 3, 2),
        ]
        assert any("omit character without page evidence: 幻の人物" in message for message in logs)

    def test_derived_character_alias_requires_repeated_page_evidence(self, db_conn):
        book_id = _insert_book(db_conn, "derived-alias-book")
        _insert_page(db_conn, book_id, 2, "茉莉花は書類を読んだ。ラーナシュは歩いた。天河の名も一度だけ出た。")
        _insert_page(db_conn, book_id, 5, "茉莉花は珀陽へ報告した。ラーナシュも同席した。")

        mock_summarize = MagicMock(
            return_value=(
                "本のサマリ",
                "一覧向け要約",
                {
                    "皓茉莉花": "主人公。",
                    "ラーナシュ・ヴァルマ": "異国の人物。",
                    "黎天河": "一度だけ似た短名が出る。",
                },
            )
        )

        with (
            patch("services.novel_db.full_builder.summarize_book_with_characters", mock_summarize),
            patch("services.novel_db.full_builder.index_book_summary"),
        ):
            _run_combined_step(db_conn, "derived-alias-book", redo=False, log=lambda _: None)

        chars = db_conn.execute(
            "SELECT name, first_page, page_count FROM book_characters WHERE book_id=? ORDER BY name",
            (book_id,),
        ).fetchall()
        assert [tuple(row) for row in chars] == [
            ("ラーナシュ・ヴァルマ", 2, 2),
            ("皓茉莉花", 2, 2),
        ]

    def test_redo_preserves_published_canonical_names_for_aliases(self, db_conn):
        book_id = _insert_book(db_conn, "canonical-book", summary="旧サマリ")
        _insert_page(db_conn, book_id, 2, "皓茉莉花は芳子星に相談し、封大虎と出発した。")
        for name in ("皓茉莉花", "芳子星", "封大虎"):
            db_conn.execute(
                "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, name, f"旧{name}説明", 2, 1),
            )
        db_conn.commit()

        generated = {
            "茉莉花": "茉莉花は主人公として行動する。",
            "子星": "子星は茉莉花を指導する。",
            "冬虎皇子": "冬虎皇子（封大虎）は茉莉花に同行する。",
        }
        with (
            patch(
                "services.novel_db.full_builder.summarize_book_with_characters",
                return_value=("新サマリ", "新しい一覧向け要約", generated),
            ),
            patch("services.novel_db.full_builder.index_book_summary"),
        ):
            _run_combined_step(db_conn, "canonical-book", redo=True, log=lambda _: None)

        rows = db_conn.execute(
            "SELECT name FROM book_characters WHERE book_id = ? ORDER BY name",
            (book_id,),
        ).fetchall()
        assert [row[0] for row in rows] == ["封大虎", "皓茉莉花", "芳子星"]

    def test_evidenced_published_character_deletion_preserves_old_content(self, db_conn):
        book_id = _insert_book(db_conn, "deletion-guard-book", summary="旧サマリ")
        _insert_page(db_conn, book_id, 2, "既存人物と削除人物が協力した。")
        for name in ("既存人物", "削除人物"):
            db_conn.execute(
                "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, name, f"旧{name}説明", 2, 1),
            )
        db_conn.commit()

        with patch(
            "services.novel_db.full_builder.summarize_book_with_characters",
            return_value=("新サマリ", "新しい一覧向け要約", {"既存人物": "既存人物の新説明。"}),
        ):
            with pytest.raises(ValueError, match="evidenced published characters missing: 削除人物"):
                _run_combined_step(db_conn, "deletion-guard-book", redo=True, log=lambda _: None)

        book = db_conn.execute(
            "SELECT summary, catalog_summary FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        rows = db_conn.execute(
            "SELECT name, summary FROM book_characters WHERE book_id = ? ORDER BY name",
            (book_id,),
        ).fetchall()
        assert tuple(book) == ("旧サマリ", "既存の一覧向け要約")
        assert [tuple(row) for row in rows] == [
            ("削除人物", "旧削除人物説明"),
            ("既存人物", "旧既存人物説明"),
        ]

    def test_published_character_without_current_evidence_can_be_removed(self, db_conn):
        book_id = _insert_book(db_conn, "stale-character-book", summary="旧サマリ")
        _insert_page(db_conn, book_id, 2, "既存人物だけが行動した。")
        for name in ("既存人物", "旧ノイズ"):
            db_conn.execute(
                "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, name, f"旧{name}説明", 2, 1),
            )
        db_conn.commit()
        logs: list[str] = []

        with (
            patch(
                "services.novel_db.full_builder.summarize_book_with_characters",
                return_value=("新サマリ", "新しい一覧向け要約", {"既存人物": "既存人物の新説明。"}),
            ),
            patch("services.novel_db.full_builder.index_book_summary"),
        ):
            _run_combined_step(db_conn, "stale-character-book", redo=True, log=logs.append)

        rows = db_conn.execute(
            "SELECT name FROM book_characters WHERE book_id = ?",
            (book_id,),
        ).fetchall()
        assert [row[0] for row in rows] == ["既存人物"]
        assert any("allow removal without current page evidence: 旧ノイズ" in message for message in logs)

    def test_invalid_new_characters_preserve_existing_summary_and_dictionary(self, db_conn):
        book_id = _insert_book(db_conn, "atomic-book", summary="旧サマリ")
        _insert_page(db_conn, book_id, 1, "既存人物は登場する。")
        db_conn.execute(
            "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, "既存人物", "旧人物説明", 1, 1),
        )
        db_conn.commit()

        with patch(
            "services.novel_db.full_builder.summarize_book_with_characters",
            return_value=("新サマリ", "新しい一覧向け要約", {"幻の人物": "本文に根拠がない。"}),
        ):
            with pytest.raises(ValueError, match="existing generated content was preserved"):
                _run_combined_step(
                    db_conn,
                    "atomic-book",
                    redo=True,
                    log=lambda _: None,
                )

        book = db_conn.execute(
            "SELECT summary, catalog_summary FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        characters = db_conn.execute(
            "SELECT name, summary FROM book_characters WHERE book_id = ?",
            (book_id,),
        ).fetchall()
        assert tuple(book) == ("旧サマリ", "既存の一覧向け要約")
        assert [tuple(row) for row in characters] == [("既存人物", "旧人物説明")]

    def test_grounding_failure_preserves_existing_summary_and_dictionary(self, db_conn):
        book_id = _insert_book(db_conn, "grounding-fail-book", summary="旧サマリ")
        _insert_page(db_conn, book_id, 1, "既存人物は登場する。")
        db_conn.execute(
            "INSERT INTO book_characters (book_id, name, summary, first_page, page_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, "既存人物", "旧人物説明", 1, 1),
        )
        db_conn.commit()

        with patch(
            "services.novel_db.full_builder.summarize_book_with_characters",
            side_effect=GroundingError("summary grounding failed"),
        ):
            with pytest.raises(GroundingError, match="grounding failed"):
                _run_combined_step(
                    db_conn,
                    "grounding-fail-book",
                    redo=True,
                    log=lambda _: None,
                )

        book = db_conn.execute(
            "SELECT summary, catalog_summary FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        characters = db_conn.execute(
            "SELECT name, summary FROM book_characters WHERE book_id = ?",
            (book_id,),
        ).fetchall()
        assert tuple(book) == ("旧サマリ", "既存の一覧向け要約")
        assert [tuple(row) for row in characters] == [("既存人物", "旧人物説明")]


class TestBuildBookFull:
    """build_book_full の高レベルフローを検証する。"""

    def test_calls_rebuild_and_combined_step(self, db_conn, monkeypatch):
        """rebuild_from_pages と _run_combined_step が順に呼ばれることを確認。"""
        mock_rebuild = MagicMock()
        mock_combined = MagicMock()

        with (
            patch("services.novel_db.full_builder.rebuild_from_pages", mock_rebuild),
            patch("services.novel_db.full_builder._run_combined_step", mock_combined),
        ):
            build_book_full("test-book")

        mock_rebuild.assert_called_once()
        mock_combined.assert_called_once()

    def test_step_callback_is_called(self, db_conn, monkeypatch):
        """step_callback に各ステップ名が渡される。"""
        steps = []
        mock_rebuild = MagicMock()
        mock_combined = MagicMock()

        with (
            patch("services.novel_db.full_builder.rebuild_from_pages", mock_rebuild),
            patch("services.novel_db.full_builder._run_combined_step", mock_combined),
        ):
            build_book_full("test-book", step_callback=steps.append)

        # start / step1 / step2 / finished の順で呼ばれる
        assert len(steps) >= 4
        assert "start" in steps[0]
        assert "finished" in steps[-1]
