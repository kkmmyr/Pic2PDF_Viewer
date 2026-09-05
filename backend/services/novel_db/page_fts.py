"""page-level LanceDB ICU全文索引の後方互換公開窓口。"""

from .page_fts_builder import PageFtsBuildResult, build_page_fts_index
from .page_fts_query import build_page_fts_snippet, search_page_fts
from .page_fts_state import (
    PAGE_FTS_INDEX_CONFIG,
    PAGE_FTS_INDEX_NAME,
    PAGE_FTS_STATE_KEY,
    PageFtsBuildConflict,
    PageFtsBuildError,
    PageFtsState,
    PageFtsUnavailable,
    get_page_fts_state,
    logger,
    mark_page_fts_stale,
)

__all__ = [
    "PAGE_FTS_INDEX_NAME",
    "PAGE_FTS_INDEX_CONFIG",
    "PAGE_FTS_STATE_KEY",
    "PageFtsBuildConflict",
    "PageFtsBuildError",
    "PageFtsBuildResult",
    "PageFtsState",
    "PageFtsUnavailable",
    "build_page_fts_index",
    "build_page_fts_snippet",
    "get_page_fts_state",
    "logger",
    "mark_page_fts_stale",
    "search_page_fts",
]
