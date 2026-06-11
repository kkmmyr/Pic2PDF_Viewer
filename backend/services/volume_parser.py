"""巻数文字列のパース。

シリーズ判定の前段階として、タイトル末尾のサフィックスを正規化された
巻数（float）に変換する。`series_resolver` から純粋関数として切り出した
ため、外部依存・状態を持たない。

`series_index` を `float` で扱うことで `2.5` のような間巻号にも対応する。

対応パターン:
- 整数巻: ``"3"`` / ``"第3巻"`` / ``"03"``
- 小数巻: ``"2.5"`` / ``"4.5"``
- vol 表記: ``"vol.5"`` / ``"VOL.2.5"``
- 括弧表記: ``"(上)"`` / ``"（中）"`` (上→1 / 中→2 / 下→3 / 前→1 / 後→2)
- 漢数字: ``"一"`` 〜 ``"十"`` (二桁の ``"十一"`` 以降は非対応)
- 「巻数なし＝1 巻」: ペア判定で片方が空・もう片方が 2 以上の整数なら空側を 1 と扱う
"""

import re

# 漢数字の整数マップ（十一以降は曖昧さ回避のため非対応）
_KANJI_NUMS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
# 整数巻（"3", "第3巻", "03" 等）
_RE_INT = re.compile(r"^\s*[第]?\s*(\d+)\s*[巻]?\s*$")
# 小数巻（"2.5", "4.5" 等）。シリーズの間巻号を表す慣習に対応
_RE_FLOAT = re.compile(r"^\s*(\d+\.\d+)\s*$")
# vol.N / vol.N.M
_RE_VOL = re.compile(r"^\s*[vV][oO][lL]\.?\s*(\d+(?:\.\d+)?)\s*$")
_RE_PAREN = re.compile(r"^\s*[(（]([上中下前後]+)[)）]\s*$")
_RE_KANJI = re.compile(r"^\s*第?([一二三四五六七八九十百]+)巻?\s*$")
_PAREN_INDEX = {"上": 1, "中": 2, "下": 3, "前": 1, "後": 2}


def parse_volume_index(suffix: str) -> float | None:
    """サフィックスを巻数（1 始まり、float）に正規化する。マッチしなければ None。"""
    s = suffix.strip()
    if not s:
        return None
    if m := _RE_FLOAT.match(s):
        return float(m.group(1))
    if m := _RE_INT.match(s):
        return float(m.group(1))
    if m := _RE_VOL.match(s):
        return float(m.group(1))
    if m := _RE_PAREN.match(s):
        kana = m.group(1)
        # 単独文字のみ対応（「上下」のような並びは扱わない）
        if len(kana) == 1 and kana in _PAREN_INDEX:
            return float(_PAREN_INDEX[kana])
        return None
    if m := _RE_KANJI.match(s):
        kanji = m.group(1)
        # 単純な漢数字のみ対応（一〜十）
        if len(kanji) == 1 and kanji in _KANJI_NUMS:
            return float(_KANJI_NUMS[kanji])
        # 二桁: 「十一」「十二」… は省略（一〜十のみ対応）
        return None
    return None


def parse_pair_volume_indexes(
    suffix_a: str,
    suffix_b: str,
) -> tuple[float | None, float | None]:
    """ペアのサフィックスを巻数に変換する。

    片方が空文字でもう片方が **2 以上の整数** にマッチした場合、
    空側を 1 巻として扱う（「シリーズの 1 巻だけタイトルに巻数を付けない」慣習）。
    `2.5` のような小数巻には適用しない（曖昧さを避けるため）。
    """
    a = parse_volume_index(suffix_a)
    b = parse_volume_index(suffix_b)

    a_blank = not suffix_a.strip()
    b_blank = not suffix_b.strip()

    def _is_int_ge_2(v: float | None) -> bool:
        return v is not None and v >= 2.0 and v.is_integer()

    if a_blank and a is None and _is_int_ge_2(b):
        a = 1.0
    if b_blank and b is None and _is_int_ge_2(a):
        b = 1.0

    return a, b
