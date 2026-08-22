"""hitomi監視の全実行経路で共有するprocess間lock。"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


class MonitorAlreadyRunningError(RuntimeError):
    """別processがhitomi監視lockを保持している。"""


def _acquire_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise MonitorAlreadyRunningError from exc
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise MonitorAlreadyRunningError from exc


def _release_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def monitor_process_lock(data_dir: Path) -> Iterator[None]:
    """同じdata directoryに対する監視を1 processへ限定する。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    handle = (data_dir / "monitor.lock").open("a+b")
    try:
        _acquire_lock(handle)
        try:
            yield
        finally:
            _release_lock(handle)
    finally:
        handle.close()
