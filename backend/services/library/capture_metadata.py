"""撮影登録に必要なLibraryメタ検査・更新・補償用snapshot。"""

from copy import deepcopy
from dataclasses import dataclass, field

from services.meta_store import MetaDict, MetaEntry, load_meta, update_meta_locked


def validate_capture_replacement(source: str, book_id: str, asin: str) -> None:
    """画像置換の前に既存メタが同一書籍を示すことを確認する。"""
    existing_meta = load_meta(source).get(book_id)
    if existing_meta is None or existing_meta.get("asin") != asin:
        raise ValueError("同名の別書籍が既にあるため置換できません")


@dataclass
class CaptureMetadataChange:
    previous_entry: MetaEntry | None = field(default=None, init=False)

    def apply(self, source: str, book_id: str, asin: str) -> None:
        def _apply(data: MetaDict) -> None:
            self.previous_entry = deepcopy(data.get(book_id))
            entry = data.setdefault(book_id, {"authors": []})
            entry["asin"] = asin

        update_meta_locked(source, _apply)

    def restore(self, source: str, book_id: str) -> None:
        def _restore(data: MetaDict) -> None:
            if self.previous_entry is None:
                data.pop(book_id, None)
            else:
                data[book_id] = self.previous_entry

        update_meta_locked(source, _restore)
