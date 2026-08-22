from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from kindle_series_models import SeriesBook, SeriesCaptureError
from kindle_series_screen_count import normalize_screen_count_warning

SESSION_SCHEMA_VERSION = 2


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
    captured_screens_by_asin: dict[str, int] = field(default_factory=dict)
    quality_warnings: list[dict] = field(default_factory=list)

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
            return cls._resume(digest, state_path, books, resume=resume)
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
        books: list[SeriesBook],
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
        if (
            data.get("schema_version") != SESSION_SCHEMA_VERSION
            or data.get("manifest_digest") != digest
        ):
            raise SeriesCaptureError("Session state does not match this inventory")
        if data.get("state") != "running":
            raise SeriesCaptureError("Tripped or completed session cannot be resumed")
        recovery_attempts, download_failures, completed_asins = cls._resume_fields(data)
        book_sources = {book.asin: book.source for book in books}
        captured_screens = cls._resume_screen_counts(
            data,
            completed_asins=set(completed_asins),
            allowed_asins=set(book_sources),
        )
        warnings = cls._resume_warnings(
            data,
            book_sources=book_sources,
            captured_screens_by_asin=captured_screens,
        )
        return cls(
            manifest_digest=digest,
            state_path=state_path,
            state=data["state"],
            trip_reason=data.get("trip_reason"),
            kindle_recovery_attempts=recovery_attempts,
            consecutive_download_failures=download_failures,
            completed_asins=completed_asins,
            captured_screens_by_asin=captured_screens,
            quality_warnings=warnings,
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
                or len(completed_asins) != len(set(completed_asins))
            ):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise SeriesCaptureError("Session state counters are invalid") from exc
        return recovery_attempts, download_failures, completed_asins

    @staticmethod
    def _resume_screen_counts(
        data: dict,
        *,
        completed_asins: set[str],
        allowed_asins: set[str],
    ) -> dict[str, int]:
        if "captured_screens_by_asin" not in data:
            raise SeriesCaptureError("Session screen-count observations are missing")
        value = data["captured_screens_by_asin"]
        if not isinstance(value, dict):
            raise SeriesCaptureError("Session screen-count observations are invalid")
        counts: dict[str, int] = {}
        for asin, count in value.items():
            if (
                not isinstance(asin, str)
                or asin not in completed_asins
                or asin not in allowed_asins
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count <= 0
            ):
                raise SeriesCaptureError(
                    "Session screen-count observations are invalid"
                )
            counts[asin] = count
        if set(counts) != completed_asins:
            raise SeriesCaptureError(
                "Session completed ASINs and screen counts do not match"
            )
        return counts

    @staticmethod
    def _resume_warnings(
        data: dict,
        *,
        book_sources: dict[str, str],
        captured_screens_by_asin: dict[str, int],
    ) -> list[dict]:
        if "quality_warnings" not in data:
            raise SeriesCaptureError("Session quality warnings are missing")
        value = data["quality_warnings"]
        if not isinstance(value, list):
            raise SeriesCaptureError("Session quality warnings are invalid")
        warnings = [
            normalize_screen_count_warning(item, allowed_asins=set(book_sources))
            for item in value
        ]
        warning_asins = [str(item["asin"]) for item in warnings]
        if len(warning_asins) != len(set(warning_asins)):
            raise SeriesCaptureError("Session quality warnings are invalid")
        for warning in warnings:
            asin = str(warning["asin"])
            if warning["source"] != book_sources[asin] or warning[
                "captured_screens"
            ] != captured_screens_by_asin.get(asin):
                raise SeriesCaptureError(
                    "Session quality warning does not match its observation"
                )
        return warnings

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "manifest_digest": self.manifest_digest,
            "state": self.state,
            "trip_reason": self.trip_reason,
            "kindle_recovery_attempts": self.kindle_recovery_attempts,
            "consecutive_download_failures": self.consecutive_download_failures,
            "completed_asins": self.completed_asins,
            "captured_screens_by_asin": self.captured_screens_by_asin,
            "quality_warnings": self.quality_warnings,
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

    def record_success(
        self,
        book: SeriesBook,
        *,
        captured_screens: int,
        warning: dict | None,
    ) -> None:
        if (
            isinstance(captured_screens, bool)
            or not isinstance(captured_screens, int)
            or captured_screens <= 0
        ):
            raise SeriesCaptureError("Successful capture screen count is invalid")
        normalized_warning = (
            normalize_screen_count_warning(
                warning,
                allowed_asins={book.asin},
            )
            if warning is not None
            else None
        )
        self.consecutive_download_failures = 0
        if book.asin not in self.completed_asins:
            self.completed_asins.append(book.asin)
        self.captured_screens_by_asin[book.asin] = captured_screens
        if normalized_warning is not None:
            self.quality_warnings = [
                item for item in self.quality_warnings if item["asin"] != book.asin
            ]
            self.quality_warnings.append(normalized_warning)
        self._persist()

    def trip(self, reason: str) -> None:
        self.state = "tripped"
        self.trip_reason = reason
        self._persist()
        raise SeriesCaptureError(f"Session safety breaker tripped: {reason}")

    def complete(self) -> None:
        self.state = "completed"
        self._persist()
