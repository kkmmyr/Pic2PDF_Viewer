# ADR-0020: Page-level LanceDB ICU BM25を世代管理shadowで導入

- **Status**: Accepted
- **Date**: 2026-08-22
- **適用状態**: production stage 1 `shadow`適用済み（LanceDB 0.34.0 / 8,576ページ）。別3冊の未調整holdoutとroot所有backup unitの共通lock反映は完了。利用者への返却はFTS5を維持し、実利用shadow観測と`lance_icu`昇格承認は未完了
- **決定者**: プロジェクトオーナー / Codex
- **関連**: [小説RAG 検索・QA設計 §10](../../詳細設計/機能別/小説RAG_検索QA設計.md#10-日本語検索基盤の比較検証ゲート)、[小説RAG データ設計](../../詳細設計/機能別/小説RAG_データ.md)、バックログ B-37

## コンテキスト

現行の lexical 検索は SQLite FTS5 trigram index に、質問文から作った長い phrase を OR
指定する。2026-08-22 の固定20問では18問が0-hitとなった。一方、SQLite `pages` の
`index_eligible=1`を隔離コピーして作った page-level LanceDB ICU BM25 は Recall@10
`.886`、MRR@10 `.720`、nDCG@10 `.708`、p95 `2.12 ms`で、個別 Recall@10 の回帰は
0件だった。

ただし既存のLanceDB `chunks` snapshotはSQLiteに対して重複32行・欠落2,781 IDがあり、
移行元として信用できない。LanceDBのFTS indexは本文更新と別ストアに存在するため、古い
indexの誤利用、構築途中の公開、障害時の検索停止も防ぐ必要がある。また、検証時に使用した
LanceDB 0.34系のFTS APIは今後変わり得る。

## 検討した選択肢

| 選択肢 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. FTS5 queryだけを調整 | 現行SQLite indexを維持し、phrase分割等を変更 | ICUの実測優位を再現できず、比較済み候補より不確実。旧経路はfallbackとして残す方が安全 |
| B. 既存`chunks`または固定名tableを直接更新 | 現行LanceDBを流用し、ページ更新ごとにadd/delete/optimize | 既存snapshotが不完全。SQLiteとの二重書込み、未索引行、途中失敗の補償が複雑 |
| **C. SQLite `pages`から世代別tableを完全再構築しshadow導入** | immutableなpage tableを新規作成し、整合確認後にSQLiteのactive pointerだけを切替 | （採用） |

## 決定

`index_eligible=1`のSQLite `pages`を正本として、LanceDB 0.34系のICU FTS indexを
世代別tableへ完全再構築する。件数・page ID一意性・source SHA-256・FTS index統計を
検証してから、SQLite `novel_search_index_state`のactive pointerを条件付き更新する。

lexical backendは`fts5` / `shadow` / `lance_icu`の3モードとし、初期既定値は`fts5`を
維持する。`shadow`は利用者へFTS5結果だけを返し、ICUとの件数・上位重複・latencyを本文や
queryを記録せず観測する。`lance_icu`はactive世代が最新の場合だけICUを返し、索引欠落・
stale・LanceDB例外時はFTS5へ縮退する。空のICU検索結果は正常結果として扱いfallbackしない。

productionは信頼済みoperator 1名の個人環境として運用する。このため短時間停止、手動shadow監視、
旧世代の手動整理は受容し、初回導入で高可用性・自動alert・自動GCを要求しない。ただし個人利用を理由に
dependency lock、writer停止確認、backup / restore検査、manifest検証、FTS5 fallbackを省略しない。

## 根拠

- 完全再構築は検証コーパス8,576ページで約2.45秒・26.1MBと十分小さく、初期段階で
  増分更新・`optimize()`・未索引行を管理する複雑さを負う利点がない。
- active pointerの更新を最後のSQLiteトランザクションに限定すると、LanceDB構築失敗や
  同時本文更新があっても旧active世代を壊さない。
- canonical本文更新と同じSQLiteトランザクションで`source_revision`を進めて`stale`にすれば、
  外部ストアの古い本文を検索へ返さない。
- page IDとbook IDによる数値prefilter、検索後のSQLite再読込みにより、scope・公開可否・snippet
  の正本をSQLiteへ保てる。
- LanceDB公式は通常検索が未索引行もflat scanする一方、`fast_search()`は未索引行を省くと説明する。
  今回は完全構築後の`num_unindexed_rows=0`を公開条件とし、`fast_search()`を使わない。
- 既存20問と別の3冊12問をcommit `89fc93e`で評価前に封印した一回holdoutでは、FTS5の12 / 12
  0-hitに対しICUは0-hit 0件、Recall@10 `.792`、MRR@10 `.833`、nDCG@10 `.748`、p95 `3.486ms`、
  個別Recall@10回帰0件だった。正解が12位だった1問を含め、開封後のquery・正解・設定調整は行わない。

参考: [LanceDB Full-Text Search](https://docs.lancedb.com/search/full-text-search)、
[Reindexing](https://docs.lancedb.com/indexing/reindexing)、
[Updating data](https://docs.lancedb.com/tables/update)、
[LanceDB releases](https://github.com/lancedb/lancedb/releases)。filterまわりの回帰事例として
[lancedb/lancedb#1656](https://github.com/lancedb/lancedb/issues/1656)も確認した。

## 結果（Consequences）

### ポジティブ

- 本番レスポンスを変えずに実コーパス・実queryでICUの健全性とlatencyを観測できる。
- 構築中・失敗・同時更新ではactive pointerを切り替えず、stale時は自動的にFTS5へ縮退する。
- 既存`chunks` / `summaries` tableと1024次元bge-m3索引を変更しない。
- `NOVEL_DB_LEXICAL_BACKEND=fts5`へ戻すだけで即時rollbackできる。

### ネガティブ・受容したコスト

- SQLiteとLanceDBにpage本文を重複保持し、世代tableを明示的に整理するまで容量を使う。
- 本文を書き換える全経路が`source_revision`を更新する必要があり、直接SQL編集は契約外となる。
- ICUはLanceDB / Tantivyのversionに依存するため、0.35以降への更新は同じfixtureと障害注入testで
  再評価が必要。
- ICUはhighlight offsetを返さないため、snippetのmarkはquery断片の決定的な近似表示になる。

### 影響範囲

- `services/novel_db/page_fts.py`: 構築、active世代検証、ICU検索、stale管理
- `services/novel_db/search.py`: lexical backend選択、shadow観測、FTS5 fallback
- `models.py` / Alembic revision 0014: `novel_search_index_state`
- OCR公開・legacy OCR保存・1ページ補正: canonical本文変更時のstale更新
- `scripts/build_page_fts_index.py`: 手動の完全再構築・active切替

## 将来の再評価条件

- 未調整holdout品質ゲートとroot所有backup unitの共通lock反映は合格済み。実運用shadowの
  非0件観測を満たしたとき、既定値を`lance_icu`へ切り替えるか別承認で判断する。
- LanceDB 0.35以降、tokenizer / score / prefilter semanticsが変わったとき。
- 完全再構築時間または世代容量が運用上無視できなくなったとき、増分更新と安全な世代GCを検討する。
- canonical本文をSQLite以外から更新する経路を追加するとき、同じrevision契約へ組み込む。
