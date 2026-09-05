# 小説RAG フロントエンド設計

> status: living | last-verified: 2026-09-05

小説DBの検索、QA、chat、読書会、書誌管理、OCR管理に関するフロントエンド設計。
backendの検索・QA契約は[小説RAG 検索QA設計](小説RAG_検索QA設計.md)、
データと時刻の正本は[小説RAG データ設計](小説RAG_データ.md)を参照する。

初期の計画形記述と移行経緯は
[小説RAG FE設計過程](../../../archive/小説RAG_FE設計過程.md)へ凍結済みであり、
本書には現行設計だけを記載する。

---

## 1. 画面構成

- `NovelDbPage`: 書籍一覧、series drilldown、全書籍検索。各`BookCard`は
  `catalog_summary`がある場合だけ「短い要約」として最大4行表示する。
- `NovelDetailPage`: 書誌、詳細あらすじ`summary`、character、類似書籍、書籍内検索、QA・履歴、chat。
  一覧向け`catalog_summary`で詳細あらすじを置き換えない。
- `NovelDiscussionPage`: 読書会生成と履歴。
- `NovelManagePage`: OCR / build job、Amazon情報取込、QA承認。
- `NovelReaderPage`: Kindle撮影画像の閲覧。検索結果から対象画面へ遷移する。

PageはURLと主要queryを組み合わせ、通信とSSE parsingは`features/novel_db/`または
`features/novel_build/`へ委譲する。

`LibrarySection`は表示・選択・URLの`dd`を所有し、一括作者/シリーズ操作の候補取得、
書籍順の逐次更新、成功時の再取得は`hooks/novel_db/useNovelLibraryBulkActions.ts`へ委譲する。
hookは再試行なしのmutationで候補取得と更新を実行する。作者は明示選択を必須とし、
途中失敗時は後続更新を止めて選択状態を残す。全件成功時だけ再取得と選択解除を行う。
候補取得失敗時の通知と空候補でのdialog表示、シリーズ巻数の対応も維持する。

---

## 2. Query cache

`features/novel_db/queries.ts`のQuery key Factoryを正本とする。

- books / seriesは画面間で同じcacheを共有する。
- 詳細、character、search、QA履歴、discussion履歴は対象bookまたはscopeをkeyへ含める。
- searchは`useInfiniteQuery`でpageを連結する。
- mutation成功後は対象book、一覧、履歴の必要なkeyだけをinvalidateする。
- `NovelReaderPage`はbooks queryの`page_count`を使い、DBに値がない場合だけ
  画像HEAD探索を別queryで実行する。

取得結果をPageのlocal stateへ複製しない。入力中の文字列、選択中tab、
SSE受信中本文だけをlocal stateに置く。

---

## 3. ScopeとURL

検索とQAの対象範囲は画面側が決定する。

- `NovelDbPage`の検索は固定の`all` scopeを使う。series drilldownは書籍一覧の絞り込みであり、検索scopeを変更しない。
- `NovelDetailPage`はURL pathの`bookName`からbook scopeを作り、書籍内検索、QA・履歴、chatへ渡す。
- 検索結果の画像リンクは`/novel/reader/:bookName?page=N`で対象画面を開く。

`useNovelDbScope`は実装ファイルとして残っているが、現行画面からは使用されない。
`scope` query parameterによる全体・series・book切替を、現行UIの契約として扱わない。

---

## 4. POST SSE

QA、chat、読書会はrequest bodyを必要とするため、標準`EventSource`ではなく
`fetch(POST)`と`ReadableStream`を使用する。

- transportは`features/novel_db/sse-transport.ts`へ集約し、`qa-sse.ts` / `chat-sse.ts` / `discussion-sse.ts`が用途別eventを変換する。
- `eventsource-parser`へSSE frame境界の解釈を委譲する。
- app側はJSON変換とevent typeの振り分けだけを行う。
- 中断は`AbortController`を使用し、serverのcanceled履歴契約を維持する。
- componentはraw chunk、改行、複数data行を解釈しない。
- error eventとHTTP errorを画面へ通知し、途中本文を成功扱いしない。

---

## 5. QAとchat

### QA

`QuestionSection`は入力を上部に固定し、下部を履歴一覧と選択詳細の2paneにする。
送信完了後は最新履歴を自動選択する。履歴詳細は選択時に取得する。

### Chat

session一覧、選択session、message一覧、入力を分離する。送信中のuser messageは
楽観表示できるが、server確定後にsession queryを再取得する。SSE transportはQAと共有し、
画面固有のsession状態まで無理に共通hookへ統合しない。

### 読書会

生成中turnをstream表示し、完了・削除後に該当履歴を再取得する。
停止、error、部分生成を完了と区別する。

---

## 6. 書籍・series管理

- books / series一覧は全Pageで共有するQuery cacheを使う。
- 一覧カードは選書用の`catalog_summary`だけを表示し、400〜700文字の全文はDOMに保持したまま
  CSSで最大4行に省略する。短縮要約が未生成の旧データでは要約欄自体を表示しない。
- 書籍詳細画面は網羅性優先の`summary`を「詳細あらすじ」として表示する。
  二つのフィールドをUI側で代替利用せず、用途を混同しない。
- series drilldownの並び替えは楽観更新し、失敗時にrollbackする。
- 書誌編集成功後は一覧と詳細の両keyを更新またはinvalidateする。
- 一括操作は選択対象と変更内容を確認し、mutation中の再送信を禁止する。

---

## 7. OCR管理

OCR runは処理中、QA待ち、承認済み、失敗を区別する。

- page type、layout type、quality flag、補正本文を同じrunのpageとして扱う。
- 原画像をmodalで参照し、OCR本文だけで正解を確定しない。
- verifiedへの変更は必要項目が揃うまでdisabledにする。
- publishはrun全体の検証後に行い、途中pageだけを正式索引へ混在させない。

詳細な品質条件は[OCR設計書](OCR設計書.md)を正本とする。

---

## 8. 日時表示

SQLite由来のtimezone情報なし文字列は、backend契約に従ってJSTとして解釈する。
`utils/date.ts`の共通関数を使い、componentで`new Date(raw)`を直接呼ばない。

関数名に歴史的な`Utc`が残る場合も、実際の入力契約をdocstringとtestで明示する。

---

## 9. エラーと再試行

- 一覧取得失敗を0件表示へ変換しない。
- SSE失敗時は受信済み本文とerrorを区別して表示する。
- mutation失敗時は入力と選択を維持する。
- stale responseが別bookや別scopeを上書きしないよう、Query keyとAbortSignalを使う。
- loading、empty、error、disabled、canceledを各主要画面で確認する。
