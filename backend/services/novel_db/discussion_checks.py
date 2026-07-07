"""B-28 読書会ロングフォーム: DoD 層1 機械チェック（M1〜M5）。

生成台本に対して LLM を使わず機械的に検証できる品質項目のみを扱う。
面白さ等の主観品質は層2（人間レビュー）の領分。
"""

from __future__ import annotations

import re

# M1: 台本全体の合計字数レンジ
_TOTAL_CHARS_MIN = 3_000
_TOTAL_CHARS_MAX = 4_500

# M2: 必須セグメント
_REQUIRED_SEGMENTS = frozenset({"op_hook", "theme1", "theme2", "tangent", "closing"})

# M3: 話者分割の健全性
_MIN_TURNS = 15
_MAX_TURN_CHARS = 600
_MARKER_RESIDUE = ("[A", "[B", "[S")

# M4: 簡体字専用文字（日本語の新字体と同形のもの [学/国/会/写 等] は入れない）
_SIMPLIFIED_ONLY_CHARS = frozenset(
    "们这说话对时东车买卖门问间闻马鸟读谁谢过还进运鱼头实变让认识请调谈论"
    "语见觉观现发书长风飞爱乐电汉华关开张阳阴难题单满战术众优传场"
)

# M4: 4文字以上の連続英字のうち許容する語（小文字で比較）。
# OP/ED 等の頻出略語は 3 字以下なので引っかからない。必要になったら追加する
_ENGLISH_ALLOWLIST: frozenset[str] = frozenset({"bleach"})

_ENGLISH_RUN_RE = re.compile(r"[A-Za-z]{4,}")


def _check_m1(turns: list[dict]) -> tuple[bool, str]:
    n = sum(len(t["text"]) for t in turns)
    return _TOTAL_CHARS_MIN <= n <= _TOTAL_CHARS_MAX, f"実測 {n:,} 字"


def _check_m2(segments_seen: list[str]) -> tuple[bool, str]:
    missing = sorted(_REQUIRED_SEGMENTS - set(segments_seen))
    if missing:
        return False, f"欠落: {', '.join(missing)}"
    return True, "5セグメントすべて出現"


def _check_m3(turns: list[dict]) -> tuple[bool, str]:
    problems = []
    if len(turns) < _MIN_TURNS:
        problems.append(f"ターン数 {len(turns)} < {_MIN_TURNS}")
    residues = [
        f"turn {i}: マーカー残骸 {marker!r}"
        for i, turn in enumerate(turns)
        for marker in _MARKER_RESIDUE
        if marker in turn["text"]
    ]
    problems.extend(residues)
    longest = max((len(t["text"]) for t in turns), default=0)
    if longest > _MAX_TURN_CHARS:
        problems.append(f"最長ターン {longest} 字 > {_MAX_TURN_CHARS}")
    if problems:
        return False, "; ".join(problems)
    return True, f"ターン数 {len(turns)}・最長 {longest} 字"


def _check_m4(full_text: str) -> tuple[bool, str]:
    leaks = [f"{ch}(位置{i})" for i, ch in enumerate(full_text) if ch in _SIMPLIFIED_ONLY_CHARS]
    for m in _ENGLISH_RUN_RE.finditer(full_text):
        if m.group().lower() not in _ENGLISH_ALLOWLIST:
            leaks.append(f"{m.group()}(位置{m.start()})")
    if leaks:
        return False, f"検出: {', '.join(leaks[:20])}" + ("…" if len(leaks) > 20 else "")
    return True, "リークなし"


def _check_m5(full_text: str, cards: list[dict]) -> tuple[bool, str]:
    for card in cards:
        matched = [kw for kw in card.get("keywords", []) if kw and kw in full_text]
        if matched:
            return True, f"「{card.get('title', '')}」のキーワード {matched[0]} が出現"
    return False, "いずれのカードのキーワードも台本に出現しない"


def run_checks(turns: list[dict], segments_seen: list[str], cards: list[dict]) -> dict:
    """DoD 層1 機械チェック M1〜M5 を実行して結果 dict を返す。

    返り値: {"passed": bool, "results": [{"id", "label", "passed", "detail"}]}
    """
    full_text = "\n".join(t["text"] for t in turns)
    checks = [
        ("M1", "字数 3,000〜4,500", _check_m1(turns)),
        ("M2", "5セグメント出現", _check_m2(segments_seen)),
        ("M3", "話者分割成功", _check_m3(turns)),
        ("M4", "言語リーク0", _check_m4(full_text)),
        ("M5", "ネタカード言及", _check_m5(full_text, cards)),
    ]
    results = [
        {"id": check_id, "label": label, "passed": passed, "detail": detail}
        for check_id, label, (passed, detail) in checks
    ]
    return {"passed": all(r["passed"] for r in results), "results": results}
