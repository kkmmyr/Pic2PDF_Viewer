# Build 画面: 進捗詳細化 — 要件定義

> 2026-05-13 /grill-me セッションで確定。4.6「本構築専用管理画面」の続きフェーズ。

---

## 1. 概要と目的

Full Build（本構築）実行中に「どの程度進んでいるか」が分からず、処理が止まっているのか動いているのか判断できない。各ステップ内でチャンク単位の細粒度メッセージを表示し、スピナーで「生きている」ことを示す。

**対象の痛み**:
- step 2/3（Qwen サマリ + キャラクタ抽出）が特に長く（1 冊あたり数分）、途中経過が全く見えない。
- step 3/3（Contextual Retrieval: チャンクごとに Gemma4 呼び出し）も 200〜300 チャンク × 数秒で長い。

---

## 2. 表示仕様

### 2.1 RunningJobCard の追加要素

現状の `RunningJobCard` に以下を追加:

| 追加要素 | 内容 |
|---|---|
| **`current_detail` メッセージ** | ステップ名の下に小さめのテキストで表示 |
| **スピナー / パルスアニメ** | ステップ名またはメッセージの左に配置。処理中を明示 |

### 2.2 `current_detail` メッセージ例

**単冊ビルド時**:
```
step 1/3: rebuild_from_pages  ⟳
  embedding 50/200 チャンク

step 2/3: summarize + characters  ⟳
  サマリ生成中 / キャラクタ抽出中 / コンテキスト 30/200 チャンク

step 3/3: generate_contexts  ⟳
  コンテキスト 50/303 チャンク
```

**全冊ビルド時**（最大 11 冊）:
```
step 3/3: generate_contexts  ⟳
  冊 1/11 処理中 | コンテキスト 50/303 チャンク
```

`progress_done / progress_total`（冊単位の進捗バー）は現状のまま維持し、`current_detail` でさらに細粒度の状況を補完する。

### 2.3 step ごとのメッセージ設計

| ステップ | `current_detail` 内容 | コールバック発火タイミング |
|---|---|---|
| step 1/3: rebuild_from_pages | `embedding N/M チャンク` | chunk embedding ループ内、N チャンクごと |
| step 2/3: summarize + characters | `サマリ生成中` → `キャラクタ抽出中` → `コンテキスト N/M チャンク` | 各サブ処理の開始時 |
| step 3/3: generate_contexts | `コンテキスト N/M チャンク` | Gemma4 呼び出しループ内、1 チャンクごと |

全冊モードでは各 step のメッセージ先頭に `冊 X/M 処理中 | ` を付ける。

---

## 3. データモデル変更

### 3.1 `rebuild_jobs` テーブルに `current_detail` カラムを追加

```sql
ALTER TABLE rebuild_jobs ADD COLUMN current_detail TEXT;
```

マイグレーション: `backend/services/novel_db/schema.py` の `_migrations` リストに追加。

### 3.2 Python 型への反映

`backend/services/novel_db/job_queue.py`:
- `_update_detail(job_id: int, detail: str)` メソッドを追加（`_update_step` と同パターン）。
- `get_status()` の返却型に `current_detail: str | None` を追加。

`backend/services/novel_db/full_builder.py`:
- `step_callback` に加えて `detail_callback(detail: str)` を引数として受け取るよう拡張。
- 各ステップのループ内で `detail_callback` を呼び出す。

---

## 4. API / フロントエンド型への反映

### 4.1 SSE レスポンス

`/api/novel/build/stream` が返す `BuildJob` に `current_detail: str | None` を追加。
既存フィールドはそのまま維持（後方互換）。

### 4.2 フロントエンド型

`frontend/src/features/novel_build/types.ts`:
```typescript
interface BuildJob {
  // 既存
  id: number;
  target_id: string | null;
  mode: string;
  state: string;
  enqueued_at: string;
  started_at: string | null;
  progress_total: number | null;
  progress_done: number | null;
  current_step: string | null;
  // 追加
  current_detail: string | null;
}
```

### 4.3 RunningJobCard の変更

`frontend/src/components/novel_build/RunningJobCard.tsx`:
- `current_step` 表示部分の左にスピナー（`<Spinner>` or Tailwind の `animate-spin`）を追加。
- `current_detail` が `null` でない場合、ステップ名の下に小テキストで表示。

---

## 5. スコープ外

- リアルタイムログストリーミング（tail -f 的な UI）。
- 推定残り時間（ETA）表示。
- OCR 画面への適用（今回は Full Build の `rebuild_jobs` テーブルのみ対象）。
- 全冊の合計チャンク数集計（過大な先行計算が必要なため省略）。

---

## 6. 完了条件

- [ ] 実機で全冊ビルドを走らせ、step ごとに `current_detail` がリアルタイム更新されることを確認。
- [ ] スピナーがステップ処理中に表示され、完了後に消えることを確認。
- [ ] `uv run pytest -q` が全通過（`_update_detail` 呼び出しのユニットテスト追加）。
- [ ] `npx tsc --noEmit` がエラーなし。

---

## 7. 影響ファイル（想定）

**バックエンド**:
- `backend/services/novel_db/schema.py` — `_migrations` に ALTER TABLE 追加
- `backend/services/novel_db/job_queue.py` — `_update_detail()` 追加、`get_status()` 返却型拡張
- `backend/services/novel_db/full_builder.py` — `detail_callback` 引数追加、各ステップ内での呼び出し
- `backend/routers/novel_build.py` — SSE レスポンスに `current_detail` を含める

**フロントエンド**:
- `frontend/src/features/novel_build/types.ts` — `BuildJob` 型に `current_detail` 追加
- `frontend/src/components/novel_build/RunningJobCard.tsx` — スピナー + detail メッセージ表示

**設計書**:
- `docs/03_詳細設計/詳細設計書_バックエンド編.md` — rebuild_jobs スキーマ更新、job_queue API 変更
- `docs/03_詳細設計/API仕様書.md` — BuildJob 型に current_detail 追記
- `docs/05_記録/変更履歴.md` — 実装完了時に追記
