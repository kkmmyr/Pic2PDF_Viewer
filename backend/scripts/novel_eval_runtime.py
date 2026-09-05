"""評価 CLI のプラットフォーム依存ランタイム情報。"""

from __future__ import annotations

import sys


def process_max_rss_bytes() -> int:
    """Return the kernel-reported peak RSS without fabricating an unavailable value."""
    try:
        import resource
    except ModuleNotFoundError as error:
        raise RuntimeError("process maximum RSS is unavailable on this platform") from error

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)
