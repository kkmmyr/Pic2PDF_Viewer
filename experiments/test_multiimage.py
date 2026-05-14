"""複数ページ: PIL で縦連結して 1 枚に合成してから送る。"""
import base64, sys, io, requests
from pathlib import Path
from PIL import Image as PILImage
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BOOK = Path(r"d:/61.tool/Pic2PDF_Viewer/backend/data/comic/images/不条理なあたし達 (楽園コミックス)")
pages = sorted(BOOK.glob("*.png"))
MODEL = "qwen3-vl:8b"
URL = "http://localhost:11434/api/chat"

def combine_pages(img_paths: list[Path], max_width: int = 800) -> bytes:
    """複数ページを縦に並べて 1 枚の PNG にする。"""
    imgs = [PILImage.open(p) for p in img_paths]
    # 幅を揃えてリサイズ
    resized = []
    for im in imgs:
        ratio = max_width / im.width
        new_h = int(im.height * ratio)
        resized.append(im.resize((max_width, new_h), PILImage.LANCZOS))
    total_h = sum(im.height for im in resized)
    combined = PILImage.new("RGB", (max_width, total_h), (255, 255, 255))
    y = 0
    for im in resized:
        combined.paste(im, (0, y))
        y += im.height
    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    return buf.getvalue()

def call_combined(img_paths, prompt, max_width=800):
    img_bytes = combine_pages(img_paths, max_width)
    b64img = base64.b64encode(img_bytes).decode()
    r = requests.post(URL, json={
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [b64img]}],
        "stream": False,
    }, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"] or ""

print("=== 縦連結（2枚）===")
ans2 = call_combined(pages[50:52], "これは漫画の連続する2ページです（上が先）。右から左、上から下の順に読みます。何が起きているか日本語で説明してください。")
print(f"len={len(ans2)}: {ans2[:500]}")

print("\n=== 縦連結（5枚）===")
ans5 = call_combined(pages[50:55], "これは漫画の連続する5ページです（上から順）。右から左、上から下の順に読みます。ストーリーを日本語で要約してください。", max_width=600)
print(f"len={len(ans5)}: {ans5[:600]}")
