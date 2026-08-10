"""通常画面で参照する旧Kindle DB入力元の軽量状態。"""

from pathlib import Path

import config


def source_status() -> dict:
    raw = config.KINDLE_LEGACY_DB_PATH
    path = Path(raw) if raw else None
    return {
        "legacy_db_configured": path is not None,
        "legacy_db_available": bool(path and path.is_file()),
        "legacy_db_name": path.name if path else None,
        "amazon_data_configured": bool(config.AMAZON_DATA_DIR),
    }
