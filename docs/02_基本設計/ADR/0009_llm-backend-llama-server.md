# ADR-0009: 小説 RAG の Qwen 推論バックエンドを Ollama から llama-server に切り替える

- **Status**: Accepted（実装完了 2026-05-11、commit `a1eee28`）
- **Date**: 2026-05-11
- **決定者**: プロジェクトオーナー
- **関連**: [ADR-0007](0007_llm-extraction-qwen-adoption.md) / [小説テキスト検索・RAG機能_バックエンド設計.md](../../03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md) / [小説RAG_技術知見.md](../../05_記録/小説RAG_技術知見.md) / [バックログ B-14](../../01_要件定義/バックログ.md) / [LLM 層リファクタリング_完了記録](../../99_アーカイブ/LLM層リファクタリング_完了記録.md)（A-0〜A-7、共通モジュールを `Qwen/` → `llm/` にリネーム + Backend 抽象化）
- **パス更新注記**: 2026-05-11 の A-0 で共通モジュールを `D:\61.tool\common\Qwen\lib\qwen_client.py` → `D:\61.tool\common\llm\local_llm\` に再構成。本 ADR 内のパス・API 名（`qwen_client` / `QwenError` 等）は決定時の歴史的記録としてそのまま残置（現行は `local_llm` パッケージ / `LLMError`）

## コンテキスト

ADR-0007 で小説 RAG の QA LLM を `qwen3.6:35b-a3b`（後に IQ4_XS 量子化版 = `qwen3.6-iq4xs`）に切り替えた。**Ollama 経由で動作させており**、本機（RTX 5070 / VRAM 12GB / システム RAM 32GB）では IQ4_XS でも 49% / 51% で CPU offload が発生する。

実測の生成速度は **scope=all で ~13 t/s（出力 256 tok を 24 秒程度）**。品質は十分だが、シリーズ全体スコープの質問では応答待ち時間が長く、UX 上の制約になっていた。

2026-05-11 に r/LocalLLaMA で報告された **llama.cpp 直叩き + MoE block を `-ncmoe` で細かく制御 + KV cache を q8_0 量子化** という設定が、RTX 3060 12GB で同じ Qwen3.6-35B-A3B IQ4_XS を 46.8 t/s で動かすという内容だったため、本機での再現性を検証した（[小説RAG_技術知見.md §9 LLM 推論バックエンド検証](../../05_記録/小説RAG_技術知見.md)）。

### 実機ベンチ結果（Phase 0〜4b、2026-05-11）

| シナリオ | Ollama tg | llama.cpp tg | tg 倍率 | Ollama 応答 | llama.cpp 応答 |
|---|---:|---:|---:|---:|---:|
| A_short (~120 tok in) | 17.1 t/s | 80.7 t/s | **4.72×** | 3.75 s | **0.71 s** |
| B_mid (~2,000 tok in) | 14.6 t/s | 80.5 t/s | **5.51×** | 21.25 s | **3.55 s** |
| C_long (~8,400 tok in) | 13.4 t/s | 78.0 t/s | **5.82×** | 24.22 s | **14.03 s** |

- 同一プロンプト・同一モデル（IQ4_XS GGUF）・同一 num_ctx (16384) 条件で計測
- llama.cpp 側は `chat_template_kwargs: {enable_thinking: false}` で thinking を抑制したフェアな比較
- 出力品質は実応答で同等（Ollama 416 chars ↔ llama.cpp 147 chars の差は冗長性のみで、論旨は一致）

## 検討した選択肢

| 選択肢 | 概要 | 採用可否 |
|---|---|---|
| A. Ollama 継続（現状） | 何もしない | 性能 5× を捨てる合理性がない |
| B. Ollama + 量子化を Q3 等にさらに下げる | 軽量化で速度向上 | 品質劣化リスク。本機は IQ4_XS で品質が成立している前提を崩したくない |
| **C. llama.cpp `llama-server` に切替 + `chat_template_kwargs` で thinking 抑制** | 性能 5× / 品質維持 / Ollama は他モデル用に併存 | **（採用）** |
| D. llama.cpp 直接ビルド（CUDA 13.x ネイティブビルド） | 最高性能の可能性 | ビルド工数が大きく、公式 b9101 Windows CUDA 13.1 ビルドで十分速い |
| E. vLLM / TGI 等の本格推論サーバー | バッチ性能◎ | 個人利用には過剰 + Windows 対応が弱い |

## 決定

1. **`backend/services/novel_db/llm.py` の Qwen 呼び出しバックエンドを llama-server (llama.cpp) に切り替える**。`NOVEL_DB_LLM_BACKEND` 環境変数で `ollama` / `llama_server` を切替可能にし、デフォルトは `llama_server`
2. **共通 Qwen モジュール (`D:\61.tool\common\Qwen\lib\qwen_client.py`) に llama-server バックエンドを追加**する。OpenAI 互換 `/v1/chat/completions` + `chat_template_kwargs: {enable_thinking: false}` で thinking を抑制
3. **llama-server は別ポート (`11435`) で常駐**させる。Ollama (`11434`) はそのまま稼働（Gemma / bge-m3 等は引き続き Ollama を使うため）
4. **llama-server の自動起動は Windows タスクスケジューラ**（NSSM 等のサービス化は採用しない）。起動コマンドは `D:\61.tool\common\llama.cpp\b9101\start-qwen-server.bat`（新規）
5. **本 ADR は ADR-0007 の追補扱い** とし、Superseded にはしない。Qwen3.6-35B-A3B IQ4_XS をモデルとして採用する判断は維持され、本 ADR は「同じモデルの実行バックエンド変更」のみを扱う

## 根拠

### llama-server を選んだ理由（数字）

- 検証フェーズで判定基準として事前に **1.5× = tg 20 t/s 以上**を採用ラインに設定。実測 4.7〜5.8× で大幅超過
- KV cache q8_0 量子化により、本機の 12GB VRAM で **16k token context を保持しても tg 76 t/s 維持**（[Phase 2b depth スイープ](../../05_記録/小説RAG_技術知見.md)）
- `-ncmoe 16` で MoE block のうち 16 個を CPU、残りを GPU に配置。投稿の `-ncmoe 18`（RTX 3060 想定）より 1 ステップ GPU 寄りで本機にフィット
- Flash Attention (`-fa 1`) + IQ4_XS で VRAM 11.8 GiB（97% 使用）に収まる

### llama-server を選んだ理由（運用）

- **Ollama を完全置換せず併存**。Gemma 4:e4b（主要登場人物抽出）/ bge-m3（embedding）は引き続き Ollama を使う。Qwen だけを llama-server に出す形で運用変更を最小化
- llama-server は OpenAI 互換 API を出すため、将来別 UI / 別ツールから叩く際にもエコシステムが豊富
- ロールバックは `NOVEL_DB_LLM_BACKEND=ollama` で 1 行（環境変数）で戻せる
  （※ Phase C / 2026-05-11 で本 rollback 経路は撤去。llama-server 採用後 1 ヶ月
  以上の実機運用で問題なしを確認したため、Ollama 上の `qwen3.6-iq4xs` を
  `ollama rm` で 23GB 解放。詳細は [LLM 層リファクタリング_完了記録 §5](../../99_アーカイブ/LLM層リファクタリング_完了記録.md)）

### thinking 抑制を `chat_template_kwargs` で行う理由

- Ollama 側の `think=False` パラメータは Ollama 独自拡張で、llama-server には存在しない
- llama-server の `--jinja` フラグで chat template を有効化し、`/v1/chat/completions` のリクエストボディに `chat_template_kwargs: {enable_thinking: false}` を渡すと Qwen 公式テンプレートが `<think>...</think>` ブロックを抑制する
- 検証フェーズ（Phase 4 → 4b）で thinking ありだと B_mid で `<think>Here's a thinking process:...</think>` が出力を食い潰す事象を実機で確認、4b で thinking 抑制により Ollama と同等品質を再現

## 結果（Consequences）

### ポジティブ

- **scope=all の質問応答が 24 秒 → 14 秒（さらに cold start なら推定 5 秒）に短縮**。UX が大幅改善
- KV cache q8_0 量子化で 32k context 程度までは性能を維持できる見込み（さらなる num_ctx 拡大の余地）
- llama.cpp の更新が早く、新モデル（Qwen 3.7 等）への追従が Ollama より速い
- MTP（Multi-Token Prediction）版モデル等、Ollama 未対応の高速化技術を取り込める

### ネガティブ・受容したコスト

- **常駐プロセスが 1 つ増える**（llama-server.exe）。VRAM 11.8 GiB を保持し続けるため、Ollama 経由で他重量モデルを同時利用したい場面では衝突する。本機で Gemma 4:26b（17GB）を Ollama で同時稼働させた場合 OOM の可能性大 → **同時実行ガード**（後述の運用ルール）
- llama-server の Windows サービス化は標準では存在せず、タスクスケジューラ + バッチでの自動起動になる。起動失敗時の検知は Health endpoint ポーリングに依存
- **Ollama + llama-server の 2 系統運用**となり、構成把握コストが微増。CLAUDE.md とアーキテクチャ詳細書への追記が必要
- 環境変数 `NOVEL_DB_LLM_BACKEND` の追加で、設定マトリクスが増える

### 影響範囲

- 変更が及ぶファイル:
  - `backend/config.py` — `NOVEL_DB_LLM_BACKEND` / `NOVEL_DB_LLAMA_SERVER_URL` 追加
  - `backend/services/novel_db/llm.py` — qwen_client の使い方を変更（バックエンド切替を意識する）
  - `D:\61.tool\common\Qwen\lib\qwen_client.py` — llama-server バックエンドを追加（`_dispatch_backend` 関数で分岐）
  - `D:\61.tool\common\llama.cpp\b9101\start-qwen-server.bat` — 新規。起動コマンドをラップ
  - `docs/03_詳細設計/小説RAG_LLMバックエンド切替設計案.md` — 新規ドラフト（本 ADR 採用時に本体設計書にマージ。Phase A の A-7 で削除済み、内容は §7.1 へ移行）
  - `docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md` — §7 LLM 呼び出し部分を更新
  - `docs/03_詳細設計/詳細設計書_バックエンド編.md §1.5` — ファイルマップを更新
  - `docs/04_環境構築/GPU環境セットアップ.md` — llama.cpp Windows CUDA ビルド入手手順を追加
  - `docs/05_記録/小説RAG_技術知見.md` — §9 LLM 推論バックエンド検証として Phase 0〜4b 結果を追記
- 後続作業:
  - Phase 5（実装）: qwen_client 拡張 → 動作確認 → 既存テストの実行
  - Phase 6（運用）: Windows タスクスケジューラ登録 / Health endpoint 監視
  - Phase 7（記録）: 採用後 2 週間使ってみて応答品質の体感差を 技術知見.md に追記

## 実装完了（2026-05-11）

Phase 5（実装）完了:
- `qwen_client.py` に `QWEN_BACKEND` 切替（`llama_server` / `ollama`）追加（commit `a1eee28`）
- 共通モジュール側 + Pic2PDF 側で計 28 件のテスト追加、backend 全 725 件 pass
- ロールバック動作確認済み

Phase 6（運用）完了:
- Windows タスクスケジューラに `llama-server-qwen` を ONLOGON / Limited / Interactive で登録（admin 不要）
- 起動 bat: `D:\61.tool\common\llama.cpp\b9101\start-qwen-server.bat`

採用後の運用上の進化（同日 2026-05-11）:
- **B-13 段階 B 採用** (commit `2bf05f3`): `num_ctx=32768 / top_k=64 / max_per_book=5`。llama-server を `-c 36864 -ncmoe 18` で再起動
- **B-13 段階 C 本採用** (commit `7c06326`): scope=book で `load_all_pages_of_book()` 経由の全 page 読み込み（`NOVEL_DB_QA_FULL_BOOK_MODE=true` 既定）。llama-server を `-c 131072 -ncmoe 28` に再設定（ncmoe スイープで生成速度と VRAM 余裕の両立点として決定）
- **質問履歴の JST 表示 + 応答時間表示** (commit `b17439f`): SQLite UTC 文字列を frontend で JST に変換 + elapsed 併記

採用最適設定の更新は [小説RAG_技術知見.md §9.3](../../05_記録/小説RAG_技術知見.md) を参照（B-14 時点 / B-13 段階 C 本採用後 を併記）。

## 将来の再評価条件

- VRAM 不足で他モデル（Gemma 26b 等）と同時運用したくなった → llama-server を停止する運用ガードを追加 or VRAM 24GB 機への移行を検討
- llama.cpp / Ollama のいずれかが破壊的変更を出した → 該当バックエンドの切替コードを見直し
- MTP 版 GGUF (`Qwen3.6-35B-A3B-MTP-IQ4_XS.gguf`) で速度がさらに 1.5× 以上向上することが確認できた → 採用 GGUF を MTP 版に切替
- vLLM / SGLang 等が Windows 対応した、または Linux への移行を行った → 推論サーバーの再選定
