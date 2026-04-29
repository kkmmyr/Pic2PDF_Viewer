"""services.hitomi.nozomi のユニットテスト（純粋関数のみ）。

実 NOZOMI を取得しないため、ネットワークなしで完結する。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi.nozomi import parse_nozomi_bytes


class TestParseNozomiBytes:
    def test_decodes_3_ids_big_endian(self):
        # big-endian: 0x00FFAABB, 0x12345678, 0xDEADBEEF
        data = bytes.fromhex("00FFAABB" "12345678" "DEADBEEF")
        assert parse_nozomi_bytes(data) == [0x00FFAABB, 0x12345678, 0xDEADBEEF]

    def test_decodes_single_id(self):
        # ID = 1 in big-endian: 0x00 0x00 0x00 0x01
        assert parse_nozomi_bytes(b"\x00\x00\x00\x01") == [1]

    def test_truncates_partial_trailing_bytes(self):
        # 4 bytes (1 ID) + 2 partial bytes → partial は切り捨て
        data = bytes.fromhex("00112233" "4455")
        assert parse_nozomi_bytes(data) == [0x00112233]

    def test_empty_returns_empty_list(self):
        assert parse_nozomi_bytes(b"") == []

    def test_under_4_bytes_returns_empty(self):
        # 4 バイト未満は ID 1 個分にも満たないので空
        assert parse_nozomi_bytes(b"\x00\x01") == []
        assert parse_nozomi_bytes(b"\x00\x01\x02") == []

    def test_endianness_distinguishes_from_little_endian(self):
        # ID = 1 を little-endian にすると 0x01 0x00 0x00 0x00 → big-endian で読むと 0x01000000
        data = b"\x01\x00\x00\x00"
        assert parse_nozomi_bytes(data) == [0x01000000]
        # 念のため逆向きも検証: big-endian の 1 は 0x00 0x00 0x00 0x01
        assert parse_nozomi_bytes(b"\x00\x00\x00\x01") == [1]

    @pytest.mark.parametrize("ids", [
        [],
        [1],
        [1, 2, 3, 4, 5],
        [2034567, 2031045, 2027890],
    ])
    def test_roundtrip_via_struct_pack(self, ids):
        import struct
        if not ids:
            data = b""
        else:
            data = struct.pack(f">{len(ids)}I", *ids)
        assert parse_nozomi_bytes(data) == ids
