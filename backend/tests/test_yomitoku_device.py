from __future__ import annotations

import pytest

from services.novel_db import ocr_worker_engines


class _DeviceAwareEngine:
    def __init__(self) -> None:
        self.devices: list[str] = []

    def initialize(self, *, device: str) -> None:
        self.devices.append(device)


class _LegacyEngine:
    def __init__(self) -> None:
        self.use_gpu_values: list[bool] = []

    def initialize(self, *, use_gpu: bool) -> None:
        self.use_gpu_values.append(use_gpu)


def test_initialize_yomitoku_engine_passes_requested_device_to_new_wrapper(monkeypatch) -> None:
    monkeypatch.setenv("OCR_YOMITOKU_DEVICE", "mps")
    engine = _DeviceAwareEngine()

    ocr_worker_engines._initialize_yomitoku_engine(engine)

    assert engine.devices == ["mps"]


def test_initialize_yomitoku_engine_keeps_legacy_cuda_wrapper_compatible(monkeypatch) -> None:
    monkeypatch.setenv("OCR_YOMITOKU_DEVICE", "cuda")
    engine = _LegacyEngine()

    ocr_worker_engines._initialize_yomitoku_engine(engine)

    assert engine.use_gpu_values == [True]


def test_initialize_yomitoku_engine_maps_legacy_auto_to_windows_gpu(monkeypatch) -> None:
    monkeypatch.setenv("OCR_YOMITOKU_DEVICE", "auto")
    monkeypatch.setattr(ocr_worker_engines.platform, "system", lambda: "Windows")
    engine = _LegacyEngine()

    ocr_worker_engines._initialize_yomitoku_engine(engine)

    assert engine.use_gpu_values == [True]


def test_initialize_yomitoku_engine_rejects_legacy_wrapper_for_mac_auto(monkeypatch) -> None:
    monkeypatch.setenv("OCR_YOMITOKU_DEVICE", "auto")
    monkeypatch.setattr(ocr_worker_engines.platform, "system", lambda: "Darwin")

    with pytest.raises(RuntimeError, match=r"initialize\(device=\.\.\.\)"):
        ocr_worker_engines._initialize_yomitoku_engine(_LegacyEngine())


def test_requested_yomitoku_device_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("OCR_YOMITOKU_DEVICE", "metal")

    with pytest.raises(ValueError, match="invalid OCR_YOMITOKU_DEVICE"):
        ocr_worker_engines._requested_yomitoku_device()


def test_ocr_worker_env_forwards_yomitoku_device(monkeypatch) -> None:
    from config import app_settings
    from services.novel_db.extractor import _ocr_worker_env

    monkeypatch.setattr(app_settings, "OCR_YOMITOKU_DEVICE", "mps")

    assert _ocr_worker_env()["OCR_YOMITOKU_DEVICE"] == "mps"
