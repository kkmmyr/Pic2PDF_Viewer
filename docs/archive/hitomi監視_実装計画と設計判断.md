# hitomi 監視 実装計画と設計判断（凍結: 2026-07-03）

> 📦 本書は hitomi新着監視設計書 から切り出した、完了済み Phase 1-4 実装計画・設計判断の経緯・デバッグ記録。歴史記録として凍結。現行の設計は [hitomi新着監視設計書](../design/詳細設計/機能別/hitomi新着監視設計書.md)。以後編集しない。

---

## 旧構成メモ（原 §2.1 内、Task Scheduler 時代）

> **旧構成メモ**: 2026-05-01〜2026-05-28 は Windows Task Scheduler（週1・月曜03:00）で動作していた。
> Linux サーバー常時稼働により systemd timer に移行。Windows 側タスクは削除済み。

---

## 2.2. 設計判断（Why）（原 §2.2、逐語移送）

- **既存 FastAPI に組み込まない理由:**
    - ポーリング側でリソースリーク・ハングが起きると Web 全体に波及する
    - 1 回の監視はミリ秒で完了する単発タスクで、cron 的実行と相性が極めて良い
- **JSON ファイル経由で連携する理由:**
    - プロセス間 IPC 不要、最小コスト
    - スクリプトとバックエンドのライフサイクルが完全独立（片方が死んでも片方は動く）
    - state ファイルのバージョン管理 / バックアップが容易
- **Linux systemd timer を選んだ理由（2026-05-28）:**
    - Linux サーバーが常時稼働中 → Windows PC のスリープ・シャットダウンに影響されない
    - `new_arrivals.json` / `state.json` を FastAPI と同一ホストで読み書きできる
    - `Persistent=true` で起動遅延時の missed run を自動補完できる

---

## 8.1.2. なぜ `_` で URL を組むと 404 になるか（原 §8.1.2、逐語移送）

検索ページの URL（`hitomi.la/search.html?artist:aka_shio`）では `_` が空白の代わりに使われる
ため、**初見では NOZOMI URL も `_` 区切りに見える**が、実際には NOZOMI ファイル名は空白を
そのまま含む別ストレージ。Phase 1 着手時にこの違いを誤認し、`/n/artist/aka_shio-japanese.nozomi`
（`_` 区切り）で 404 を踏んだ。正しくは `/n/artist/aka%20shio-japanese.nozomi`（空白を URL encode）。

---

## 9. Phase 別実装計画（原 §9、逐語移送）

### 進捗概観（2026-04-29 時点）

| Phase | ステータス | コミット | 補足 |
|---|---|---|---|
| Phase 1 | ✅ 完了（運用化待ち） | `18aec89` + `f61e9c0` | サービス層 + 監視 CLI + ユニットテスト |
| Phase 2 | ✅ 完了 | `f3d5fff` | 閲覧 API + 新着一覧 UI |
| Phase 3 | ✅ 完了 | `ef557bf` | watchlist 編集 UI + 規約整合 |
| 拡張: 「今すぐ取得」 | ✅ 完了 | `dd4801b` | UI から同期実行ボタン |
| 拡張: 直近 3 日スキップ | ✅ 完了 | `5fa45f3` | 過剰アクセス抑制 + 実行統計 |
| 拡張: 登録時 top_id 初期化 | ✅ 完了 | — | 登録前の既存作品を新着として誤検出しない |
| Phase 4: 表紙画像 | ⏸ **スキップ確定** | — | 実装コスト > 利益。`hitomi.la で開く` リンクで代替 |

**Phase 1 の運用化:** Task Scheduler 登録済み（2026-05-01）。毎週月曜 03:00 に自動実行。

### Phase 1: 監視スクリプト単体（UI なし） ✅

1. `backend/services/hitomi/nozomi.py` + 単体テスト
2. `backend/services/hitomi/metadata.py` + 単体テスト
3. `backend/services/hitomi/state_store.py` + 単体テスト
4. `backend/services/hitomi/watchlist.py` + 単体テスト
5. `backend/tools/hitomi_monitor.py`
6. `backend/data/hitomi/watchlist.json` を手動で作成し `aka_shio` を登録
7. `uv run python -m tools.hitomi_monitor` で動作確認
8. Task Scheduler 登録（→ §10）
9. 1 週間動かして `state.json` / `new_arrivals.json` の正常性を確認

**完了条件:** 新着 ID が `new_arrivals.json` に蓄積される

### Phase 2: 閲覧 UI ✅

1. `backend/routers/hitomi.py`（new-arrivals / dismiss / dismiss-all）
2. `frontend/src/types/hitomi.ts`
3. `frontend/src/hooks/useHitomiArrivals.ts`
4. `frontend/src/components/hitomi/HitomiArrivalCard.tsx`
5. `frontend/src/pages/HitomiPage.tsx`（当初 `HitomiNewArrivalsPage.tsx` として設計、実装時に `pages/` 配下のページコンポーネントに変更）
6. ヘッダーに「新着」リンクとバッジを追加

**完了条件:** ブラウザから新着確認 + 既読化が可能

### Phase 3: 監視対象管理 UI ✅

1. `backend/routers/hitomi.py` に watchlist CRUD 追加
2. `useHitomiArrivals.ts` と分離した `useHitomiWatchlist.ts` を新規作成（監視対象の取得・追加・削除を担当）
3. `HitomiWatchlistDialog.tsx`
4. 不正な作者名のバリデーション（NOZOMI 404 即時試験）

**完了条件:** UI から作者の追加・削除が可能

### Phase 4（任意）: 表紙画像表示 ⏸ スキップ確定

検討の結果、**実装コストが利益を上回るためスキップ判定**。理由:

1. **実装コスト**: hitomi.la の `gg.js` 画像 URL ハッシュ生成ロジックを移植する必要が
   あり、彼らの仕様変更で容易に壊れる。CORS / Referer 制約からバックエンド画像
   プロキシ + ローカルキャッシュの設計も必要となり、機能 1 つ分のコストが大きい
2. **利益が小さい**: カードに表紙画像が出るだけで、既に「hitomi.la で開く」ボタン
   から 1 クリックで原本の表紙含めて閲覧可能
3. **負荷観点**: ブラウザキャッシュ（`Cache-Control: max-age=31536000`）が効く前提
   なら実際の hitomi.la への負荷は誤差レベルだが、本機能の方針として `hitomi.la`
   への直リンクで完結させることに合致

**再検討トリガー**: 「どうしてもカード上で表紙を確認したい」運用シーンが出た時点で
本セクションを更新して着手する。

参考実装メモ（着手時の起点として残す）:
1. `https://ltn.gold-usergeneratedcontent.net/common.js` + `gg.js` から `gg.b()` /
   `gg.s()` 関数を読解しサブドメインハッシュアルゴリズムを移植
2. 画像 URL は概ね `https://<subdomain>.gold-usergeneratedcontent.net/webp/<hash>/<id>.webp`
3. CORS / Referer ヘッダ制約を確認し、必要なら `GET /api/hitomi/cover/{id}` の
   バックエンドプロキシ + `backend/data/hitomi/covers/<id>.webp` ローカルキャッシュ

---

## 10.5. Windows Task Scheduler について（原 §10.5、逐語移送）

2026-05-28 以降、Windows 側の `Pic2PDF Hitomi Monitor` タスクは**削除済み**。
二重実行を避けるためタスクスケジューラから削除すること（削除済みなら無視）。
