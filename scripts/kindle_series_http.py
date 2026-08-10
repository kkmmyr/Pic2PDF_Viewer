from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from kindle_series_models import SeriesBook, SeriesCaptureError


class HttpCaptureApi:
    def __init__(self, api_base: str, timeout_seconds: float = 30.0) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
    ) -> dict:
        url = f"{self.api_base}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SeriesCaptureError(
                f"API request failed: {method} {path}: {exc}"
            ) from exc

    def list_books(self, query: str) -> list[dict]:
        response = self._request(
            "GET",
            "/api/kindle-catalog/books",
            query={"q": query, "page": 1, "page_size": 200},
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise SeriesCaptureError("Catalog response does not contain an items list")
        if response.get("total") != len(items):
            raise SeriesCaptureError(
                "Series search exceeded the supported 200-book inventory"
            )
        return items

    def list_jobs(self) -> list[dict]:
        response = self._request(
            "GET",
            "/api/kindle-catalog/capture-jobs",
            query={"limit": 500},
        )
        items = response.get("items")
        if not isinstance(items, list):
            raise SeriesCaptureError(
                "Capture job response does not contain an items list"
            )
        return items

    def create_job(self, book: SeriesBook) -> dict:
        return self._request(
            "POST",
            "/api/kindle-catalog/capture-jobs",
            body={
                "asin": book.asin,
                "source": book.source,
                "direction": "left",
                "expected_screens": None,
            },
        )

    def get_book(self, asin: str) -> dict:
        response = self._request(
            "GET",
            "/api/kindle-catalog/books",
            query={"q": asin, "page": 1, "page_size": 50},
        )
        matches = [
            item for item in response.get("items", []) if item.get("asin") == asin
        ]
        if len(matches) != 1:
            raise SeriesCaptureError(
                f"Catalog did not return exactly one book for ASIN {asin}"
            )
        return matches[0]
