# ADR-0003: `generated` ソースを image-only モードに切替（PDF 生成・配信を廃止）

- **Status**: Accepted
- **Date**: 2026-05-05
- **決定者**: プロジェクトオーナー
- **関連**: [変更履歴 W19 inline](../../05_記録/変更履歴.md) `## 2026-05-05: feat — generated ソースを image-only モードに切替（pdfs_compressed 廃止）`

## コンテキスト

`generated` ソース（WebP 画像 → 圧縮 PDF を生成）は元来「生成された PDF をブラウザで配信」していた。`backend/data/main/pdfs_compressed/` に圧縮済み PDF を蓄積し、`/pdfs` 静的マウント経由で配信する設計。

しかし運用が進むにつれて以下が顕在化:

- 同じ画像から生成した PDF と元 WebP の **二重保存** によるディスク容量の膨張
- 圧縮 PDF を再生成する `/api/batch_compress` の存在自体が「PDF はキャッシュ品」であることを示している
- 元の WebP は `data/main/images/` に常に保持されている（PDF 生成のソース）

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| 現状維持（PDF + 画像の二重保存） | 配信形態を変えない | ディスク容量問題が解消しない |
| PDF 圧縮率を上げる | 既存 PDF を更に小さく | 二重保存の根本問題は残る、画質劣化も |
| 画像を削除し PDF のみ残す | PDF を「真ソース」に | 再圧縮・サムネイル再生成・ページ削除が PDF 操作になり重い |
| **WebP のみ保持し PDF をオンデマンド配信／非配信** | image-only モード化 | （採用） |

## 決定

`generated` ソースは **WebP 画像のみを保持し、PDF を恒常生成・配信しない** 設計に切り替える。`pdfs_compressed/` ディレクトリと `/pdfs` 静的マウントを廃止。フロントエンドは画像（WebP）を直接表示する。

`kindle` / `novel` ソースは引き続き PDF を保持・配信する（こちらは元画像を持たないユースケース）。

## 根拠

- **目的はディスク容量削減**。WebP 二重保存の解消が直接効く。
- **元ファイル（WebP）は常に残るため、PDF が必要になれば後から再生成可能**。可逆的な決定。
- **個人ツール**であり、自身の判断のみで決定可能（ユーザー合意プロセスのコストが無い）。
- 見開き表示は画像でも問題なく実現できている（フロント実装で対応）。
- 検索は元々 `novel` ソースでのみ運用しており（`novel` は PDF を継続）、`generated` で検索が必要になっていない。

## 結果

### ポジティブ
- ディスク使用量が大幅減（画像のみ保持）
- PDF 生成ジョブ・圧縮ジョブの運用が `generated` ソースで不要になり保守対象が減る
- サムネイル・ページ削除等の操作が WebP 直接操作になり高速化

### ネガティブ・受容したコスト
- `generated` ソースから PDF をエクスポートしたいユースケースで、再生成のひと手間が発生する
- 「ソースごとに配信形式が異なる」という非対称が API 仕様に残る（`source=generated` は image、`source=kindle/novel` は PDF）
- `/api/thumbnails/page` も `generated` は WebP 直接、`kindle`/`novel` は fitz レンダリング、と分岐が増えた

### 影響範囲
- `backend/data/main/pdfs_compressed/` ディレクトリ削除
- `backend/main.py` の `/pdfs` 静的マウント削除
- `routers/generate.py` / `routers/thumbnails.py` の image-only 分岐ロジック
- `frontend/src/components/reader/PdfCard.tsx` 等の表示経路
- 詳細設計書_共通.md の "image-only モード" 説明

## 将来の再評価条件

- `generated` ソースで全文検索（OCR 連携）が必要になったとき → PDF 化の再検討
- ユーザー数が個人を超えた場合 → 「PDF が欲しい」要望の声を考慮
- フロントエンドの WebP 一括表示パフォーマンスが書籍数増で破綻したとき → 中間形式の再導入検討
