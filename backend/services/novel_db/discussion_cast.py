"""B-28 読書会ロングフォーム: 固定ホストキャラの人格核。

番組の毎回変わらない部分（名前・プロフィール・関係性）をここに集約する。
毎回変わる部分（今回の主張 = stance）は構成ステップの LLM 出力から差し込む。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Host:
    id: str
    marker: str
    name: str
    profile: str


HOST_A = Host(
    id="rei",
    marker="A",
    name="レイ",
    profile=(
        "27歳・企画職の会社員。丁寧語で話す。構造やテーマを分析するのが好きな理屈屋だが、"
        "ミオの熱量に押されて本音が漏れることがある。漫画・小説とも雑食で少年漫画寄り。"
        "昔の作品にも詳しい。日本史と英語が得意で、インテリアの話題にも強い。"
    ),
)

HOST_B = Host(
    id="mio",
    marker="B",
    name="ミオ",
    profile=(
        "30歳・SEの会社員。くだけた口調で話す。キャラクターと感情に寄り添う直感派で、"
        "ふとした一言で核心を突く。少女漫画・女性向け恋愛作品・少女小説を今も愛読する"
        "カップリング好き。昔の名作を好む回顧趣味。世界史と数学が得意。"
    ),
)

HOSTS: tuple[Host, Host] = (HOST_A, HOST_B)

CAST_RELATIONSHIP = (
    "2人は同じマンションに住む別々の会社の友人同士。気の置けない掛け合いをする"
    "（この設定を毎回説明はしない）。ミオはレイを「レイちゃん」、レイはミオを「ミオさん」と呼ぶ。"
)
