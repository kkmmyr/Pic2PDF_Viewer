"""OCR worker — D:\\61.tool\\common\\ocr\\venv\\Scripts\\python.exe で実行するスタンドアロンスクリプト。

Usage:
    python ocr_worker.py <images_dir1> [<images_dir2> ...]

各 images_dir を OCR 処理し、1 書籍につき 1 行の JSON を stdout に出力する:
    {"book_name": "<name>", "pages": [{"page_no": N, "full_text": "...", "char_count": N}, ...]}
    {"book_name": "<name>", "error": "<message>"}  # エラー時

yomitoku は一度だけ初期化して全書籍で再利用する。
"""

import json
import sys
from pathlib import Path

_OCR_PATH = r"D:\61.tool\common\ocr"
if _OCR_PATH not in sys.path:
    sys.path.insert(0, _OCR_PATH)

from ocr_engine import get_ocr_engine  # noqa: E402


def _process_book(images_dir: Path, engine) -> list[dict]:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    pages = []
    for img_path in sorted(images_dir.glob("*.png")):
        try:
            page_no = int(img_path.stem)
        except ValueError:
            continue
        # cv2.imread は Windows で非 ASCII パスを ANSI 解釈するため文字化けする。
        # numpy.fromfile でバイト列を読んでから imdecode する。
        buf = np.fromfile(str(img_path), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            continue
        results = engine.extract_text(img)
        full_text = "\n".join(r["text"] for r in results if r.get("text", "").strip())
        pages.append({"page_no": page_no, "full_text": full_text, "char_count": len(full_text)})
    return pages


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no images_dirs provided"}), flush=True)
        sys.exit(1)

    engine = get_ocr_engine("yomitoku")
    engine.initialize()

    for images_dir_str in sys.argv[1:]:
        images_dir = Path(images_dir_str)
        book_name = images_dir.name
        try:
            pages = _process_book(images_dir, engine)
            print(json.dumps({"book_name": book_name, "pages": pages}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"book_name": book_name, "error": str(exc)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
