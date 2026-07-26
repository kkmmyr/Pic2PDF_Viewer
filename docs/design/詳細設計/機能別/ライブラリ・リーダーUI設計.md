# ライブラリ・リーダーUI設計

> status: living | last-verified: 2026-07-26

`doujin` / `comic` / `novel`のライブラリ表示と、画像・PDF readerの現行設計を定める。
ファイルの所在は
[フロントエンド ファイルマップ](../詳細設計書_フロントエンド_ファイルマップ.md)、
共通規約は[詳細設計書（フロントエンド編）](../詳細設計書_フロントエンド編.md)を参照する。

---

## 1. 画面とURL

`ViewerPage`はURLからsource、path、選択書籍を導出し、ライブラリとreaderを切り替える。

- source: URL pathから`doujin | comic | novel`を導出。
- path / file: `?path=` / `?file=`。
- 作者・シリーズdrilldown: `?author=` / `?series=`。
- ブラウザーの戻る・進むで一覧階層と選択書籍を復元できる。

ライブラリは書籍表示中もmountを維持し、`display:none`で隠す。readerを閉じたときに
一覧DOMとスクロール位置を再利用するためである。

---

## 2. ライブラリのデータフロー

```text
URL / libraryStore
  └─ useLibraryPanel
      ├─ useLibraryPdfs（server state）
      ├─ useBookMeta / useGenres（server state）
      ├─ filter / sort / grouping（derived state）
      └─ LibraryPanelContext
          ├─ LibraryHeader
          ├─ PdfGrid
          └─ LibraryDialogs
```

- PDF一覧、meta、genre、設定はTanStack Queryで取得する。
- `libraryStore`はcurrent path、選択mode、選択項目などUI状態だけを保持する。
- 取得失敗を空配列へ変換せず、error alertと再試行を表示する。
- sort、filter、groupingは入力値から導出し、保存しない。

### フィルターとsort

- タイトル・作者検索、作者、genre、series、read state、hiddenを組み合わせる。
- `view_desc`は閲覧回数降順、`recent_view`は最終閲覧日時降順。
- 検索中はgroupingを無効化し、hitした個別書籍を直接表示する。
- series drilldown中は`series_index`昇順を優先する。

### grouping

`none | series | author | author-then-series`を持つ。

- series: `series_id`単位。既定の代表は最終巻。
- author: 正規化した作者集合単位。
- author-then-series: 作者、series、個別本の3階層drilldown。
- 1冊だけのgroupは集約しない。
- group cardの選択は全memberを1回のstate更新で選択・解除する。

### 代表pin

series / authorの代表書籍は`meta2.db.group_pins`を`/api/prefs`経由で保存する。
初回だけ旧localStorageからDBへ移行し、以後はQuery cacheを正本とする。

### 選択mode

- `s`キーまたはheader操作で開始する。入力中とreader表示中はshortcutを抑制する。
- 一括作者、genre、series、hidden、削除、結合、thumbnail再生成を提供する。
- 成功時だけ選択modeを解除し、失敗時は選択を残して再試行可能にする。
- 完全削除はhidden一覧に限定し、`ConfirmDialog danger`を経由する。

---

## 3. LibraryHeader

Headerは次の3段構成とする。

1. 現在地、breadcrumbs、source selector。
2. 検索、filter、grouping、read state、hidden、sort、tools、選択mode。
3. 選択mode中だけ表示する件数と一括操作。

通常操作と一括操作を同じ段へ混在させない。狭幅では折り返しを許容し、
操作を端末種別で禁止しない。

---

## 4. スクロール位置

path、source、author、series、選択書籍からscroll keyを作り、一覧階層ごとに保持する。
URL変更前のclick capture phaseで`window.scrollY`を保存し、復帰時はlayout確定後の
`requestAnimationFrame`で`window.scrollTo`する。

ブラウザー標準のscroll restorationと競合しないよう、初回mountでは強制復元しない。

---

## 5. Readerの責務分割

```text
ReaderPanel（JSX orchestration）
  └─ useReaderState
      ├─ document / image state
      ├─ page navigation
      ├─ spread mode
      ├─ UI visibility
      ├─ edit mode
      ├─ search
      ├─ read progress
      └─ related books / volume navigation
```

- `ReaderPanel`はsubcomponentを組み合わせ、工程ロジックを持たない。
- `ReaderPageView`はPDF worker、document、画像またはPDF page描画を担当する。
- `ReaderHeader`、`ReaderPageView`、shortcut dialogは`ReaderContext`を
  field selectorで購読する。
- 書籍切替時は旧requestをcancelし、page、search、related page、edit stateをresetする。

`novel`の画像本文は`NovelReaderPage`が担当し、OCR本文は`novel.db`を参照する。

---

## 6. ページnavigation

### 読み方向

- LTR: 右側操作で次へ、左側操作で戻る。
- RTL: 左側操作で次へ、右側操作で戻る。
- keyboardの左右矢印、click zone、swipeは同じ意味へ変換する。

### 見開き

`auto | spread | single`の3modeを持つ。

- autoは縦長pageを見開き候補とし、横長pageを検出したpairはsingle表示にする。
- RTL spreadは表紙1を単独、以降を`2, 4, 6...`開始とする。
- LTR spreadは`1, 3, 5...`開始とする。
- slider jumpと前後移動は同じ純粋なpage正規化規則を使う。

### 画面操作

contentを左右・中央の3zoneへ分ける。

- 読み方向上の前zone: 前page。
- 中央: headerとsliderの表示切替。
- 次zone: 次page。

入力中、dialog表示中、edit overlay中はglobal navigationを抑制する。

---

## 7. 画像・PDF表示

`useBookImages`が画像URL一覧を取得し、画像がある場合はimage mode、
ない場合はPDF modeを使用する。

- URLには画像mtime由来の`v`を含め、同名再撮影後のbrowser cache混在を防ぐ。
- versionだけの再取得では前の一覧をplaceholderとして維持する。
- 書籍、path、sourceが変わった場合は旧一覧を引き継がない。
- image一覧がpage countより先に縮む一時状態では、PDF描画へ誤fallbackせず
  End placeholderを表示する。

---

## 8. 編集mode

`PageGridOverlay`で全page thumbnailを表示し、削除と並べ替えを行う。

- clickで選択、Shift+clickで範囲選択。
- drag handleだけをDnD起点とし、card clickとの競合を防ぐ。
- 複数選択dragは相対順を保つ。
- 並べ替えは即時API送信し、失敗時にvisual orderをrollbackする。
- 削除は確認後に実行し、成功後にdocument versionを更新する。
- page順変更後も選択状態を新page番号へ追従させる。

---

## 9. 読書状態と巻間移動

- 書籍を開いたとき`POST /api/meta/view`を呼び、未読はreadingへ遷移する。
- 最終page / 最終spread到達時にdoneを1回だけ設定する。
- selected book変更時に多重発火guardをresetする。
- 同一folder・同一seriesの`series_index`から前巻・次巻を求める。
- 次巻buttonと上下矢印shortcutは同じ遷移処理を使い、遷移先は1page目から開始する。

---

## 10. 関連書籍仮想page

最終pageからさらに次へ進んだ場合、候補があれば実pageではない関連書籍pageを表示する。

- 同series: 自分を除き`series_index`順。
- 同作者: 自分と同seriesを除く。
- 候補0件なら最終pageに留まる。
- 戻る操作で最終pageへ復帰する。
- 仮想page中はpage indicatorとsliderを非表示にする。
- 書籍選択時は閲覧記録後に対象書籍の先頭へ移動する。

---

## 11. 不変条件と確認

- LTR/RTL、single/spread、先頭/末尾でpageを飛ばさない。
- 検索中のgrouping抑制とbreadcrumbsを維持する。
- mutation失敗時に選択、並び順、metaを失わない。
- 同名画像置換後に旧画像と新画像を混在させない。
- desktop、iPad相当幅、light/dark、keyboard、touchで主要閲覧操作を確認する。
