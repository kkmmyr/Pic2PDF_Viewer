"""Compare the generated FastAPI OpenAPI schema with a reviewed baseline."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
BASELINE_PATH = Path(__file__).with_name("openapi_baseline.json")


def normalize_schema(schema: dict[str, Any]) -> str:
    """Return deterministic JSON while omitting runtime-specific server URLs."""
    normalized = dict(schema)
    normalized.pop("servers", None)
    return json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def generate_schema() -> dict[str, Any]:
    backend_path = str(BACKEND_ROOT)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    from main import app

    return app.openapi()


def schema_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace the reviewed baseline with the current generated schema",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    current = normalize_schema(generate_schema())
    if args.update:
        BASELINE_PATH.write_text(current, encoding="utf-8")
        print(
            "OpenAPI baseline updated: "
            f"{schema_digest(current)[:12]} ({len(json.loads(current)['paths'])} paths)"
        )
        return 0

    if not BASELINE_PATH.exists():
        print(
            f"OpenAPI baseline is missing: {BASELINE_PATH.relative_to(PROJECT_ROOT)}",
            file=sys.stderr,
        )
        return 2
    baseline = BASELINE_PATH.read_text(encoding="utf-8")
    if baseline == current:
        schema = json.loads(current)
        print(
            "OpenAPI contract passed: "
            f"{schema_digest(current)[:12]} ({len(schema['paths'])} paths)"
        )
        return 0

    print(
        "OpenAPI contract changed. Review the diff and use --update only if intended:"
    )
    diff = difflib.unified_diff(
        baseline.splitlines(),
        current.splitlines(),
        fromfile="openapi_baseline.json",
        tofile="generated_openapi.json",
        lineterm="",
    )
    for index, line in enumerate(diff):
        if index >= 200:
            print("... diff truncated after 200 lines")
            break
        print(line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
