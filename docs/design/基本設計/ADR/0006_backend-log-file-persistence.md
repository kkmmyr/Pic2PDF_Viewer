# ADR-0006: バックエンドログを RotatingFileHandler でファイル永続化する

- **Status**: Accepted
- **Date**: 2026-05-07
- **決定者**: プロジェクトオーナー
- **関連**: [運用ガイド §5](../../環境構築/運用ガイド.md)、[セキュリティ設計書 §2-5 / §2-6](../../詳細設計/セキュリティ設計書.md)、[backend/utils/logger.py](../../../backend/utils/logger.py)（旧 `機能追加候補.md A-7` で起票、本 ADR で実装決定）

## コンテキスト

これまで `backend/utils/logger.py` の `get_logger()` は `StreamHandler(sys.stdout)` のみを設定しており、ログはターミナル（`start.bat` から起動した Windows Terminal タブ）にのみ出力されていた。実害として以下が出ていた:

- **タブを閉じるとログ履歴が消失** — エラー後の事後調査・再現確認が困難
- **セキュリティ監査ログ（[セキュリティ設計書 §2-5](../../詳細設計/セキュリティ設計書.md)）の保全性が無い** — ZIP bomb 拒否時の `logger.warning("Security: ZIP rejected ...")` がタブごと消える
- **Discord 通知連携や OCR 別プロセス連携のデバッグ時、過去ログを遡れない**

[運用ガイド §5「過去のサーバーログを確認したい」](../../環境構築/運用ガイド.md) に「PowerShell `Start-Transcript` で代用」という回避策を書いていたが、毎回手動起動が必要で実運用では機能していない。

個人 LAN ソロツールという信頼モデル（[ADR-0002](0002_fastapi-backend.md)、[セキュリティ設計書 §1](../../詳細設計/セキュリティ設計書.md)）の中でも、**自分の手元での調査用ログ**は最低限ファイル永続化したい。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| 現状維持（StreamHandler のみ） | 最小構成 | 前述の通り実害あり |
| `Start-Transcript` 等の OS 機能で代替 | コード変更不要 | 起動毎に手動運用、忘れる |
| `TimedRotatingFileHandler`（日次ローテ） | 「いつ起きたか」で切れる | 個人ツールでは「容量で切る」ほうが分かりやすく、ファイル数も予測しやすい |
| **`RotatingFileHandler`（容量ローテ）** | 標準ライブラリ、シンプル、最大容量が予測可能 | （採用） |
| 構造化ログ（JSON） | パース容易 | 個人ツールでは grep で読むため過剰、可読性が落ちる |
| セキュリティイベント別ファイル | 監査ログを切り離せる | `Security:` 接頭辞で grep 可能、別ファイル化は過剰設計（信頼モデルが LAN ソロのため） |
| 環境変数でログレベル / 出力先を可変化 | 柔軟性 | YAGNI、必要になってから追加 |

## 決定

`backend/utils/logger.py` の `get_logger()` に `logging.handlers.RotatingFileHandler` を追加する。

| 項目 | 値 | 理由 |
|---|---|---|
| 出力先 | `backend/data/logs/app.log` | `backend/data/` は既に [`.gitignore`](../../../.gitignore) 済み（コミットされない） |
| ローテーション戦略 | サイズベース（`RotatingFileHandler`） | 個人ツールでは容量を予測したい |
| 最大サイズ | **10 MB** × **5 世代**（合計 50 MB 上限） | 1 行 ≒ 100 バイト × 通常運用日次 1〜10k 行 ≒ 数日〜数週間分が常時確保できる |
| エンコーディング | UTF-8（明示） | Windows のデフォルト `cp932` で日本語ログが文字化けするのを回避 |
| フォーマット | 既存の StreamHandler と同一 | 違いを作らない |
| ログレベル | INFO（既存と同じ）／root logger は WARNING | 既存挙動を維持。サードパーティライブラリの DEBUG が混入しないよう root の閾値だけ上げる |
| StreamHandler | **維持**（各モジュール logger に直接付与、既存通り） | 開発時のターミナル可視性を失わない |
| ハンドラ取り付け先 | `RotatingFileHandler` は **root logger に 1 回だけ** | 各 logger 個別に付けると Windows でファイルハンドルが多重に開かれ、ローテーション時に競合するリスクがある |

## 根拠

- **標準ライブラリで完結**: 追加依存なし。`logging.handlers.RotatingFileHandler` は十分に枯れている。
- **書き込み先を `backend/data/logs/` に置く理由**: 既に `backend/data/` は gitignore 済みで、ログがコミットされる事故を防げる。`backend/logs/` のような別パスを切ると新たに gitignore 追加が必要。
- **10MB × 5 世代の根拠**: 通常運用 1 行 ≒ 100 バイトと仮定し、INFO 中心の出力で日次 1〜10k 行（特に hitomi 監視・OCR 連携時にバースト）を想定。10MB ≒ 10 万行 ≒ 数日〜数週間分。5 世代あれば最低でも直近の重大事象を取り損なわない。容量上限 50MB は LAN ソロツールでは無視できる規模。
- **root logger 集約方式**: 各 `get_logger(__name__)` が個別に `RotatingFileHandler` を持つと、N モジュール × N ファイルハンドルになり、Windows 上で `doRollover()` 呼び出し時に競合する典型的な落とし穴がある。`logger.propagate = True`（デフォルト）に乗せて root に流せば、ファイルへの書き込みハンドルは常に 1 個。
- **StreamHandler 二重出力の回避**: StreamHandler を root に付けてしまうと、各モジュール logger 自身の StreamHandler と合わせて二重出力になる。よって StreamHandler は従来どおり各モジュール logger 直付けに留め、root には FileHandler のみ追加する。
- **セキュリティイベント分離は当面しない理由**: `Security:` 接頭辞は既に [セキュリティ設計書 §2-5](../../詳細設計/セキュリティ設計書.md) で標準化済み。`grep "^.*Security:" app.log*` で抽出できるため、ファイル分割の運用コストは個人 LAN ツールでは見合わない。

## 結果（Consequences）

### ポジティブ
- ターミナルを閉じてもログが残る → 事後調査が可能
- セキュリティ監査ログ（`Security: ZIP rejected ...` 等）が保全される
- 容量が `10MB × 5 = 50MB` に固定されるため、ディスクが逼迫することはない
- ハンドラ周りの構造変更は最小（root に 1 つ追加するだけ）

### ネガティブ・受容したコスト
- ローテーション切替の瞬間（`app.log → app.log.1`）に Windows でファイル名変更がブロックされる場合がまれにある（多重プロセス起動時など）。LAN ソロ運用では実害はほぼ無いと判断
- 50MB 程度の永続データが `backend/data/logs/` に常駐する
- ログが書き換わるため、**長期保管したい場合は手動アーカイブが必要**（個人ツール前提では運用ガイドに記載するに留める）

### 影響範囲
- [backend/utils/logger.py](../../../backend/utils/logger.py) — 実装変更
- [backend/tests/test_logger.py](../../../backend/tests/test_logger.py) — テスト追加（FileHandler 付与・ディレクトリ作成・既存挙動互換）
- [docs/03_詳細設計/詳細設計書_バックエンド編.md](../../詳細設計/詳細設計書_バックエンド編.md) — ロギング節の更新
- [docs/03_詳細設計/セキュリティ設計書.md](../../詳細設計/セキュリティ設計書.md) — §2-5 の「監査ログ保全」が成立するようになった旨を反映
- [docs/04_環境構築/運用ガイド.md §5](../../環境構築/運用ガイド.md) — 「過去のサーバーログを確認したい」の記述を「`backend/data/logs/app.log` を見る」に書き換え

## 将来の再評価条件

このとき決定を見直す:

- **ログ容量が逼迫したとき** — 1 日で 10MB を超えるなら世代数を増やす or サイズ拡張
- **長期監査が必要になったとき**（LAN 外公開・複数ユーザー化など） — `TimedRotatingFileHandler` への切替や、外部ログ収集（journald / Loki 等）を検討
- **セキュリティイベント（`Security:` 接頭辞）の発生頻度が増えたとき** — 別ファイル分離 + 長期保存に切替
- **構造化ログが必要になったとき**（CI 統合や Discord 通知でフィールド単位のフィルタが欲しくなったら） — JSON フォーマッタへ移行
