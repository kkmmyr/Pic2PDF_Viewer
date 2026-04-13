# リファクタリング計画書

作成日: 2026-04-12  
対象: Pic2PDF_Viewer (バックエンド: FastAPI/Python、フロントエンド: React/TypeScript)

---

## 概要

コードベース全体を調査した結果、以下の4フェーズに分けてリファクタリングを実施する。  
各フェーズは独立して実施可能。優先度は高→低の順。

---

## フェーズ 1: セキュリティ・安定性の修正 (Critical) — **完了 2026-03-08**

### 1-1. パスバリデーションの一元化

**対象:** `backend/routers/library.py`  
**問題:** `../` や `/` のチェックが4箇所以上に重複しており、漏れが生じやすい。  
**対応:**
```python
# 新規: backend/utils/path_utils.py を作成
def validate_safe_path(path: str) -> str:
    """ディレクトリトラバーサル攻撃を防ぐパス検証"""
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    return os.path.normpath(path)
```
- `library.py` 内の重複チェックを全て `validate_safe_path()` 呼び出しに置き換える
- `pathlib.Path` を使って文字列操作の `.replace("\\", "/")` を排除する

---

### 1-2. スレッドセーフティの修正

**対象:** `backend/routers/pdfs.py` の `GenerateState`、`backend/services/ocr_service.py`  
**問題:** シングルトン状態管理がスレッドアンセーフ。同時リクエスト時に競合状態が発生する。  
**対応:**
- `GenerateState` に `threading.Lock` を追加
- ステータス文字列を `StatusEnum` 定数に変更 (`"not_started"` / `"in_progress"` / `"completed"`)
- `ocr_service.py` のシングルトンにもロックを追加

---

### 1-3. ファイル操作のトランザクション安全性

**対象:** `backend/routers/library.py` の `move_items()`、`backend/services/pdf_generator.py` の `execute_moves()`  
**問題:** PDF・サムネイル・画像の複数ファイル操作が途中で失敗した場合にロールバックできない。  
**対応:**
- バックアップ→操作→確認→クリーンアップ のパターンを実装
- `execute_moves()` は削除前に一時バックアップを作成し、例外時にリストア

---

## フェーズ 2: 高優先度リファクタリング (High) — **完了 2026-03-08**

### 2-1. ViewerPage.tsx の分割

**対象:** `frontend/src/pages/ViewerPage.tsx` (現在386行、useState 13個以上)  
**問題:** ライブラリ閲覧・PDF表示・編集機能が1ファイルに混在し、保守が困難。  
**対応:** 以下のコンポーネントに分割する

```
pages/
  ViewerPage.tsx       ← 薄いラッパー・状態オーケストレーション
components/viewer/
  LibraryPanel.tsx     ← ライブラリ一覧・フォルダ操作
  ReaderPanel.tsx      ← PDF表示・ページナビゲーション
  EditPanel.tsx        ← ページ削除・編集操作
```

- 多数の `useState` は `useReducer` に集約
- URL 同期ロジックは `useUrlState()` カスタムフックに抽出

---

### 2-2. ポーリングの共通フック化

**対象:** `frontend/src/hooks/usePdfStatus.ts`、`useOcrStatus.ts`  
**問題:** 両フックで 1000ms 固定インターバルのポーリングが重複実装。リソース浪費。  
**対応:** 共通フック `usePolling()` を作成

```typescript
// hooks/usePolling.ts
function usePolling<T>(
  fetcher: () => Promise<T>,
  options: { interval: number; enabled: boolean; onSuccess?: (data: T) => void }
): { data: T | null; error: Error | null }
```

- AbortController でアンマウント時にリクエストキャンセル
- アイドル時はポーリング停止（状態が "completed" / "not_started" になったら止める）
- インターバルを設定から変更可能にする

---

### 2-3. APIクライアントのエラー処理強化

**対象:** `frontend/src/config/api_client.ts`  
**問題:** エラー種別を区別せず、ユーザーにそのままエラーメッセージを表示。  
**対応:**
- `NetworkError` / `ValidationError` / `ServerError` の型を定義
- レスポンスインターセプターで種別を判定してラップ
- タイムアウト設定を追加（デフォルト 30 秒）

---

### 2-4. pdf_generator.py の重複ロジック統合

**対象:** `backend/services/pdf_generator.py`  
**問題:** `process_zip()` と `process_directory()` がサムネイル生成・PDF生成・画像移動の同じ処理を重複実装（各約50行）。  
**対応:**
- 共通の `_process_images()` メソッドに抽出
- `progress_callback` を全コードパスで一貫して使用するか削除

---

## フェーズ 3: コード品質向上 (Medium) — **完了 2026-03-08**

### 3-1. TypeScript の型安全性強化

**対象:** `frontend/src/pages/ViewerPage.tsx`、`GeneratorPage.tsx`、各フック  
**問題:** `any` 型が複数箇所に存在し、型チェックが無効化されている。  
**対応:**
- `any` を全て具体的な型に置き換え
- `src/types/index.ts` の `GenerateRequest` に欠落フィールド (`generate_compressed`, `quality`) を追加
- API レスポンスの型定義を完備

---

### 3-2. Python 型ヒントの追加

**対象:** `backend/services/pdf_service.py`、`pdf_generator.py`、`thumbnail_service.py`  
**問題:** 型ヒントがなく、IDE サポートやリファクタリングが困難。  
**対応:**
- 全関数に引数・戻り値の型ヒントを追加
- `get_dirs_by_source()` の戻り値を `TypedDict` で定義

---

### 3-3. ロギングの整備

**対象:** バックエンド全体（現在 `print()` が散在）  
**問題:** `print()` によるログは本番環境でのトレースが困難。  
**対応:**
- `logging` モジュールを導入し、`backend/utils/logger.py` を作成
- 全 `print()` を適切なログレベル（`logger.info()` / `logger.warning()` / `logger.error()`）に置き換え

---

### 3-4. config.py の整理

**対象:** `backend/config.py`  
**問題:** `os.makedirs()` が各ディレクトリ構造ごとに重複。`BASE_DIR` が定義されているが未使用。  
**対応:**
- ディレクトリ生成をループで統一
- `BASE_DIR` を削除または使用
- CORS オリジンを環境変数 (`ALLOWED_ORIGINS`) から読み込むよう変更

---

### 3-5. GeneratorPage.tsx の UX 改善

**対象:** `frontend/src/pages/GeneratorPage.tsx`  
**問題:** 2つのボタンが同じ `loading` 状態を共有しており、どちらの操作中か判別不能。クオリティ値 `50` がハードコード。  
**対応:**
- `isGenerating` / `isCompressing` を分離した状態に変更
- クオリティのデフォルト値を定数 `DEFAULT_QUALITY = 50` に集約

---

## フェーズ 4: 品質向上・将来対応 (Low) — **完了 2026-04-12**

### 4-1. テスト基盤の整備

**バックエンド:**
```
requirements-dev.txt に追加: pytest, pytest-asyncio, httpx
```
- `backend/tests/` ディレクトリを作成
- `validate_safe_path()` などの純粋関数からテストを開始

**フロントエンド:**
```
devDependencies に追加: vitest, @testing-library/react
```
- `usePolling()`、`useReaderNavigation()` などのカスタムフックをテスト対象とする

---

### 4-2. エラーバウンダリの追加

**対象:** `frontend/src/App.tsx`  
**問題:** 子コンポーネントのエラーがアプリ全体をクラッシュさせる。  
**対応:**
- `ErrorBoundary` コンポーネントを追加して主要ページをラップ
- ユーザー向けフォールバック UI を表示

---

### 4-3. フォルダ作成 UI の改善

**対象:** `frontend/src/hooks/useLibraryManagement.ts`  
**問題:** `window.prompt()` でフォルダ名を入力させており、バリデーションもない。  
**対応:**
- MUI の `Dialog` コンポーネントを使ったモーダルに変更
- フォルダ名のバリデーション（禁止文字、空文字チェック）を追加

---

### 4-4. 環境変数の整備

**対象:** プロジェクト全体  
**対応:**
- `.env.example` を作成し、必要な環境変数を文書化
- `python-dotenv` を導入してバックエンドの設定を `.env` ファイルから読み込む

---

## 実施優先度まとめ

| 優先度 | 項目 | 工数目安 |
|--------|------|----------|
| Critical | 1-1 パスバリデーション一元化 | 0.5日 |
| Critical | 1-2 スレッドセーフティ修正 | 0.5日 |
| Critical | 1-3 ファイル操作のロールバック | 1日 |
| High | 2-1 ViewerPage 分割 | 2日 |
| High | 2-2 ポーリング共通化 | 1日 |
| High | 2-3 APIクライアント強化 | 0.5日 |
| High | 2-4 pdf_generator 重複排除 | 0.5日 |
| Medium | 3-1〜3-5 型安全性・ロギング等 | 各0.5日 |
| Low | 4-1〜4-4 テスト・UX改善等 | 各0.5〜1日 |

---

## 変更しない箇所

以下は現状のまま維持する（スコープ外）:

- Kindle キャプチャツール (`kindle-pdf/`) — 別サブシステム
- データディレクトリ構造 (`backend/data/`) — 既存データとの互換性維持
- API エンドポイントの URL 設計 — フロントエンドとの整合性維持
- `react-pdf` の設定 — ライブラリの制約内で動作している
