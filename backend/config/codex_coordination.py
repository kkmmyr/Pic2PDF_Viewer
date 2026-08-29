"""Codex端末間MCPサービスの設定。"""

from pathlib import Path
from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class CodexCoordinationSettings(BaseSettings):
    """環境変数`CODEX_COORDINATION_*`からMCP設定を読む。"""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="CODEX_COORDINATION_",
        extra="ignore",
    )

    db_path: Path = _BACKEND_DIR / "data" / "codex_coordination.db"
    host: str = "127.0.0.1"
    port: int = 8790
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


codex_coordination_settings = CodexCoordinationSettings()
