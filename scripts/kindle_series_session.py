from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from kindle_series_models import SeriesBook, SeriesCaptureError


@dataclass
class SessionSafetyGuard:
    """シリーズ全体の失敗回数を保持し、trip後の次job作成を拒否する。"""

    manifest_digest: str
    state_path: Path | None = None
    state: str = "running"
    trip_reason: str | None = None
    kindle_recovery_attempts: int = 0
    consecutive_download_failures: int = 0
    completed_asins: list[str] = field(default_factory=list)

    @staticmethod
    def digest_books(books: list[SeriesBook]) -> str:
        payload = [
            {
                "asin": book.asin,
                "title": book.title,
                "source": book.source,
                "volume_number": book.volume_number,
            }
            for book in books
        ]
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(canonical).hexdigest()

    @classmethod
    def open(
        cls,
        books: list[SeriesBook],
        state_path: Path | None,
        *,
        resume: bool = False,
    ) -> SessionSafetyGuard:
        digest = cls.digest_books(books)
        if state_path is None:
            return cls(manifest_digest=digest)
        if state_path.exists():
            return cls._resume(digest, state_path, resume=resume)
        if resume:
            raise SeriesCaptureError("Session state does not exist for resume")
        guard = cls(manifest_digest=digest, state_path=state_path)
        guard._persist()
        return guard

    @classmethod
    def _resume(
        cls,
        digest: str,
        state_path: Path,
        *,
        resume: bool,
    ) -> SessionSafetyGuard:
        if not resume:
            raise SeriesCaptureError(
                "Session state already exists; use explicit resume after inspection"
            )
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SeriesCaptureError("Session state is unreadable") from exc
        if data.get("schema_version") != 1 or data.get("manifest_digest") != digest:
            raise SeriesCaptureError("Session state does not match this inventory")
        if data.get("state") != "running":
            raise SeriesCaptureError("Tripped or completed session cannot be resumed")
        recovery_attempts, download_failures, completed_asins = cls._resume_fields(data)
        return cls(
            manifest_digest=digest,
            state_path=state_path,
            state=data["state"],
            trip_reason=data.get("trip_reason"),
            kindle_recovery_attempts=recovery_attempts,
            consecutive_download_failures=download_failures,
            completed_asins=completed_asins,
        )

    @staticmethod
    def _resume_fields(data: dict) -> tuple[int, int, list[str]]:
        try:
            recovery_attempts = int(data.get("kindle_recovery_attempts", 0))
            download_failures = int(data.get("consecutive_download_failures", 0))
            completed_asins = data.get("completed_asins") or []
            if (
                recovery_attempts < 0
                or download_failures < 0
                or not isinstance(completed_asins, list)
                or not all(isinstance(asin, str) for asin in completed_asins)
            ):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise SeriesCaptureError("Session state counters are invalid") from exc
        return recovery_attempts, download_failures, completed_asins

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "manifest_digest": self.manifest_digest,
            "state": self.state,
            "trip_reason": self.trip_reason,
            "kindle_recovery_attempts": self.kindle_recovery_attempts,
            "consecutive_download_failures": self.consecutive_download_failures,
            "completed_asins": self.completed_asins,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        temporary = self.state_path.with_name(f"{self.state_path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)

    def before_create(self, book: SeriesBook) -> None:
        if self.state != "running":
            raise SeriesCaptureError(
                f"Session safety breaker is {self.state}: {self.trip_reason}"
            )
        if book.asin in self.completed_asins:
            self.trip(f"duplicate_completed_asin:{book.asin}")

    def record_recovery_attempt(self, book: SeriesBook) -> None:
        self.kindle_recovery_attempts += 1
        if self.kindle_recovery_attempts > 1:
            self.trip(f"kindle_recovery_limit:{book.asin}")
        self._persist()

    def record_failure(self, book: SeriesBook, result: dict) -> None:
        error_code = str(result.get("error_code") or "unknown")
        if error_code == "download_failed":
            self.consecutive_download_failures += 1
            if self.consecutive_download_failures >= 3:
                self.trip(f"consecutive_download_failed:{book.asin}")
            self._persist()
            return
        self.trip(f"{error_code}:{book.asin}")

    def record_success(self, book: SeriesBook) -> None:
        self.consecutive_download_failures = 0
        if book.asin not in self.completed_asins:
            self.completed_asins.append(book.asin)
        self._persist()

    def trip(self, reason: str) -> None:
        self.state = "tripped"
        self.trip_reason = reason
        self._persist()
        raise SeriesCaptureError(f"Session safety breaker tripped: {reason}")

    def complete(self) -> None:
        self.state = "completed"
        self._persist()
