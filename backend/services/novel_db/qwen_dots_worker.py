"""Sequential Qwen3.5 + dots.mocr worker for mandatory-review OCR runs."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .ocr_content_guards import has_suspicious_repetition
    from .ocr_layout_types import suggest_layout_type
    from .ocr_worker_protocol import OcrWorkerTask, emit, emit_progress, page_payload
    from .surya_types import SuryaPageResult
except ImportError:
    from ocr_content_guards import has_suspicious_repetition
    from ocr_layout_types import suggest_layout_type
    from ocr_worker_protocol import OcrWorkerTask, emit, emit_progress, page_payload
    from surya_types import SuryaPageResult

QWEN_MODEL_REVISION = "dc58acc05962cb2ca129c8d3533ab7e5a651cc02"
DOTS_MODEL_REVISION = "e539fbb52280393adc081b289ec597430a0f9031"
QWEN_ENGINE_VERSION = "5.12.0"
DOTS_ENGINE_VERSION = "0.6.15"
QWEN_PROMPT_ID = "qwen3.5-ocr-jp-html-layout-v1"
DOTS_PROMPT_ID = "dots-mocr-prompt-layout-v1"
QWEN_PROMPT_SHA256 = "1dda14e45822c6b783fa7f5f09ba6c22de56c47d266d45256f7b4a0bd41030aa"
DOTS_PROMPT_SHA256 = "16ff71ac5d218f35e5b3db41240b6e70741498bc099db3fa922ce1ff972e3b2f"
COMPOSITE_MODEL_REVISION = f"qwen:{QWEN_MODEL_REVISION}+dots:{DOTS_MODEL_REVISION}"
_ROOT_DIR = Path(__file__).resolve().parents[3]
_QWEN_SCRIPT = _ROOT_DIR / "scripts" / "maintenance" / "qwen35_ocr_jp_vertical_predict.py"
_DOTS_SCRIPT = _ROOT_DIR / "scripts" / "maintenance" / "dots_mocr_vertical_predict.py"
_SELECT_SCRIPT = _ROOT_DIR / "scripts" / "maintenance" / "select_qwen35_dots_predictions.py"
_STREAM_END = object()


@dataclass(frozen=True)
class CompositeSettings:
    qwen_python: Path
    dots_python: Path
    qwen_model_path: Path
    dots_model_path: Path
    artifact_dir: Path
    stage_timeout_sec: float

    @classmethod
    def from_env(cls) -> CompositeSettings:
        def required_path(name: str, *, directory: bool) -> Path:
            value = os.environ.get(name)
            if not value:
                raise ValueError(f"{name} is required for qwen35_dots_review_v1")
            configured = Path(value).expanduser()
            path = configured.resolve() if directory else configured.absolute()
            valid = path.is_dir() if directory else path.is_file()
            if not valid:
                kind = "directory" if directory else "file"
                raise ValueError(f"{name} must be an existing {kind}: {path}")
            return path

        artifact_value = os.environ.get("OCR_QWEN_DOTS_ARTIFACT_DIR")
        if not artifact_value:
            raise ValueError("OCR_QWEN_DOTS_ARTIFACT_DIR is required for qwen35_dots_review_v1")
        timeout = float(os.environ.get("OCR_QWEN_DOTS_STAGE_TIMEOUT_SEC", "21600"))
        if timeout <= 0:
            raise ValueError("OCR_QWEN_DOTS_STAGE_TIMEOUT_SEC must be positive")
        return cls(
            qwen_python=required_path("OCR_QWEN_PYTHON", directory=False),
            dots_python=required_path("OCR_DOTS_PYTHON", directory=False),
            qwen_model_path=required_path("OCR_QWEN_MODEL_PATH", directory=True),
            dots_model_path=required_path("OCR_DOTS_MODEL_PATH", directory=True),
            artifact_dir=Path(artifact_value).expanduser().resolve(),
            stage_timeout_sec=timeout,
        )


@dataclass(frozen=True)
class PreparedScope:
    dataset_root: Path
    scope_dir: Path
    metadata_path: Path
    task_by_id: dict[str, OcrWorkerTask]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _prepare_scope(tasks: list[OcrWorkerTask], settings: CompositeSettings) -> PreparedScope:
    records: list[dict[str, Any]] = []
    task_by_id: dict[str, OcrWorkerTask] = {}
    dataset_root: Path | None = None
    scope_items: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        image_path = Path(task["image_path"]).resolve()
        book_name = str(task["book_name"])
        page_no = int(task["page_no"])
        if not image_path.is_file():
            raise ValueError(f"OCR input image is missing: {image_path}")
        if image_path.parent.name != book_name or image_path.parents[1].name != "images":
            raise ValueError(f"composite OCR input must be images/<book>/<page>: {image_path}")
        current_root = image_path.parents[2]
        if dataset_root is None:
            dataset_root = current_root
        elif current_root != dataset_root:
            raise ValueError("composite OCR tasks must share one dataset root")
        if image_path.stem != str(page_no).zfill(len(image_path.stem)):
            raise ValueError(f"OCR task page number does not match image filename: {image_path}")
        image_sha256 = _sha256(image_path)
        record_id = f"page-{index:08d}"
        relative_path = image_path.relative_to(current_root).as_posix()
        records.append(
            {
                "id": record_id,
                "is_vertical": True,
                "output_path": relative_path,
            }
        )
        task_by_id[record_id] = task
        scope_items.append(
            {
                "id": record_id,
                "book_name": book_name,
                "page_no": page_no,
                "image_relpath": relative_path,
                "image_sha256": image_sha256,
            }
        )
    if dataset_root is None:
        raise ValueError("composite OCR task list is empty")
    scope_payload = {
        "schema": "qwen35-dots-scope-v1",
        "qwen_revision": QWEN_MODEL_REVISION,
        "dots_revision": DOTS_MODEL_REVISION,
        "pages": scope_items,
    }
    digest = hashlib.sha256(
        json.dumps(scope_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    scope_dir = settings.artifact_dir / digest
    metadata_path = scope_dir / "metadata.jsonl"
    metadata = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    _write_atomic(metadata_path, metadata)
    _write_atomic(
        scope_dir / "scope.json",
        json.dumps(scope_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    return PreparedScope(dataset_root, scope_dir, metadata_path, task_by_id)


def _read_process_output(stream: Any, events: queue.Queue[object]) -> None:
    try:
        for line in stream:
            events.put(line)
    except BaseException as exc:
        events.put(exc)
    finally:
        events.put(_STREAM_END)


def _stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _run_stage(stage: str, command: list[str], *, timeout_sec: float, total_pages: int) -> None:
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdout is not None
    events: queue.Queue[object] = queue.Queue()
    reader = threading.Thread(
        target=_read_process_output,
        args=(proc.stdout, events),
        name=f"ocr-{stage}-output",
        daemon=True,
    )
    reader.start()
    deadline = time.monotonic() + timeout_sec
    try:
        emit_progress(stage + "_started", server_generation=0, total_pages=total_pages)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{stage} exceeded {timeout_sec:g} seconds")
            try:
                event = events.get(timeout=min(5.0, remaining))
            except queue.Empty:
                continue
            if event is _STREAM_END:
                break
            if isinstance(event, BaseException):
                raise RuntimeError(f"{stage} output reader failed") from event
            detail = str(event).strip()
            if detail:
                emit_progress(
                    stage + "_progress",
                    server_generation=0,
                    total_pages=total_pages,
                    detail=detail[-1000:],
                )
        proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        if proc.returncode != 0:
            raise RuntimeError(f"{stage} exited with code {proc.returncode}")
        emit_progress(stage + "_completed", server_generation=0, total_pages=total_pages)
    finally:
        _stop_process(proc)
        reader.join(timeout=1)


def _load_selected(path: Path, expected_ids: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = record.get("id")
            if not isinstance(record_id, str) or record_id in seen:
                raise ValueError(f"selected output line {line_number} has invalid id")
            seen.add(record_id)
            records.append(record)
    if seen != expected_ids:
        raise ValueError("selected output page set does not match OCR task set")
    return records


def _audit_envelope(record: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema": "qwen35-dots-page-v1",
            "selection_reason": record["selection_reason"],
            "primary": {
                "text": record["primary_text"],
                "raw_output": record["primary_raw_output"],
                "provenance": record["primary_provenance"],
            },
            "external": {
                "text": record["external_text"],
                "raw_output": record["external_raw_output"],
                "provenance": record["external_provenance"],
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def run_qwen_dots_review(tasks: list[OcrWorkerTask]) -> None:
    settings = CompositeSettings.from_env()
    scope = _prepare_scope(tasks, settings)
    qwen_output = scope.scope_dir / "qwen.jsonl"
    dots_output = scope.scope_dir / "dots.jsonl"
    selected_output = scope.scope_dir / "selected.jsonl"
    qwen_command = [
        str(settings.qwen_python),
        str(_QWEN_SCRIPT),
        "--metadata",
        str(scope.metadata_path),
        "--dataset-root",
        str(scope.dataset_root),
        "--output",
        str(qwen_output),
        "--model-path",
        str(settings.qwen_model_path),
        "--model-revision",
        QWEN_MODEL_REVISION,
        "--engine-version",
        QWEN_ENGINE_VERSION,
        "--allow-empty-candidate",
    ]
    dots_command = [
        str(settings.dots_python),
        str(_DOTS_SCRIPT),
        "--metadata",
        str(scope.metadata_path),
        "--dataset-root",
        str(scope.dataset_root),
        "--output",
        str(dots_output),
        "--model-path",
        str(settings.dots_model_path),
        "--model-revision",
        DOTS_MODEL_REVISION,
        "--engine-version",
        DOTS_ENGINE_VERSION,
        "--prompt-mode",
        "layout",
        "--prompt-id",
        DOTS_PROMPT_ID,
        "--allow-custom-model-code",
        "--allow-empty-candidate",
    ]
    _run_stage("qwen", qwen_command, timeout_sec=settings.stage_timeout_sec, total_pages=len(tasks))
    _run_stage("dots", dots_command, timeout_sec=settings.stage_timeout_sec, total_pages=len(tasks))
    _run_stage(
        "selector",
        [
            str(settings.qwen_python),
            str(_SELECT_SCRIPT),
            "--qwen-predictions",
            str(qwen_output),
            "--dots-predictions",
            str(dots_output),
            "--output",
            str(selected_output),
            "--allow-empty-candidates",
        ],
        timeout_sec=min(settings.stage_timeout_sec, 600.0),
        total_pages=len(tasks),
    )
    records = _load_selected(selected_output, set(scope.task_by_id))
    for record in records:
        task = scope.task_by_id[record["id"]]
        selected_text = str(record.get("pred") or "")
        primary_text = str(record.get("primary_text") or "")
        external_text = str(record.get("external_text") or "")
        primary_raw = record.get("primary_raw_output")
        external_raw = record.get("external_raw_output")
        selection_reason = str(record["selection_reason"])
        image_only = selection_reason == "dots_image_only_review_required"
        if (not selected_text.strip() and not image_only) or has_suspicious_repetition(selected_text):
            raise ValueError(f"selected OCR candidate is empty or repetitive: {record['id']}")
        if not isinstance(primary_raw, str) or not primary_raw.strip():
            raise ValueError(f"Qwen raw output is missing: {record['id']}")
        if not isinstance(external_raw, str) or not external_raw.strip():
            raise ValueError(f"dots raw output is missing: {record['id']}")
        image_path = Path(task["image_path"])
        image_sha256 = _sha256(image_path)
        if image_sha256 != record.get("input_sha256"):
            raise ValueError(f"source image changed after composite OCR: {record['id']}")
        selected_engine = "external" if record["selected_engine"] == "dots.mocr" else "primary"
        selected_raw = external_raw if selected_engine == "external" else primary_raw
        layout_type = suggest_layout_type(
            raw_output=selected_raw,
            full_text=selected_text,
            char_count=len(selected_text),
        )
        flags = ["review_assisted_composite", f"selection_reason:{selection_reason}"]
        if primary_text != external_text:
            flags.append("candidate_disagreement")
        result = SuryaPageResult(
            full_text=selected_text,
            raw_output=_audit_envelope(record),
            blocks=[],
            state="passed",
            quality_flags=flags,
            ink_coverage=None,
            attempt_count=2,
        )
        payload = page_payload(
            str(task["book_name"]),
            int(task["page_no"]),
            image_sha256,
            result,
            0,
            layout_type=layout_type,
            primary_text=primary_text,
            external_text=external_text,
            selected_engine=selected_engine,
            selection_reason=selection_reason,
        )
        emit(payload)
