"""後方互換用のAPIスキーマ再export。

新規モデルは ``routers.schemas`` の機能別moduleへ追加する。
"""

from routers.schemas import *  # noqa: F403
from routers.schemas import __all__ as __all__
