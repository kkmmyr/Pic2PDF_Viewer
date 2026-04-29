"""diff_unseen_ids（前回の top_id より新しい ID を抽出するロジック）のユニットテスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi.nozomi import diff_unseen_ids


class TestDiffUnseenIds:
    def test_no_prev_returns_all(self):
        # 初回監視（前回 top なし）→ 全件が新着
        assert diff_unseen_ids([3, 2, 1], None) == [3, 2, 1]

    def test_prev_matches_first_returns_empty(self):
        # 先頭が前回 top と一致 → 新着なし
        assert diff_unseen_ids([5, 4, 3], 5) == []

    def test_prev_matches_middle_returns_prefix(self):
        # 配列途中で一致 → それより前（新しい）の ID のみ返す
        assert diff_unseen_ids([10, 9, 8, 7], 8) == [10, 9]

    def test_prev_not_found_returns_all(self):
        # 一致なし（取得期間内に多数の新着があった）→ 全件返す
        assert diff_unseen_ids([20, 19, 18], 5) == [20, 19, 18]

    def test_empty_input_returns_empty(self):
        assert diff_unseen_ids([], None) == []
        assert diff_unseen_ids([], 100) == []

    def test_returns_new_list_not_reference(self):
        # 戻り値が引数と同一参照ではないこと（破壊的変更を防ぐ）
        ids = [3, 2, 1]
        result = diff_unseen_ids(ids, None)
        assert result == ids
        assert result is not ids
