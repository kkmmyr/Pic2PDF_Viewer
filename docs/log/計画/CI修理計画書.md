# CI 修理計画書（frontend / backend / docs の 3 job を green に戻す）

対象リポジトリ: `D:\61.tool\Pic2PDF_Viewer`（GitHub: 同名リポジトリ、workflow は `.github/workflows/ci.yml` の `CI`、jobs = `frontend` / `backend` / `docs`）

**出自と検証状態**: 本計画書は 2026-07-04 の調査（読み取り専用 + リポジトリ本体無改変の隔離コピーでの修正検証）に基づく草稿を、初見レビュアーの指摘 4 件（PR 作成手順の欠落 / 除外リスト追加と設計コメントの矛盾 / 前提ツール確認の欠落 / テスト数絶対値による判定）を反映して 2026-07-06 に正式化したもの。frontend / backend の修正は隔離コピーで実行して green を確認済み。docs はスクリプト読解 + 差分の突き合わせで原因特定済み（詳細は §1）。**本計画書の作成時点で実装は未着手**（リポジトリは無改変のまま）。

実行者はこの計画書とコード以外の文脈を持たない前提で書かれている。読みながら「なぜ」を推測する必要がないよう、判断の根拠は全てこの文書内に書き出してある。

---

## 目次（判断の揮発性順 — 上ほど「別判断もあり得た」重い判断、下ほど機械的・揺るがない事実）

1. [§3-3 FE-1 判断 a] frontend の eslint 衝突の直し方＝**eslint を 9 系へ降格**（`--legacy-peer-deps` や jsx-a11y 側の対応待ちではなく）
2. [§3-3 FE-1 判断 b] typescript/openapi-typescript 衝突の直し方＝**`overrides` で吸収**（typescript 本体を 5 系へ降格するのではなく）
3. [§3-2 BE-1 判断] backend のバグの直し方＝**本番コード（`search.py`）の呼び出し順序を直す**（テストにモックを足すだけで済ませない）
4. [§3-1 DOCS-1 判断] docs job のバグの直し方＝**生成スクリプトの除外リストに `.coverage` を追加し、設計コメントの方針記述も同時に改訂する**（対症療法でその場だけ再生成しない）
5. [§3-1 DOCS-1 完了条件] 修理成功の証拠の選び方＝**「ドキュメントから `.coverage` 行が消える」を主証拠にする**（ローカルの `--check` exit 0 は環境依存で弁別力が無い場合がある）
6. [§1 全体] 3 job の失敗原因の切り分け（frontend は原因が 2 つ、docs は「未特定」ではなく特定済み）
7. [§3 全体] 3 項目の実行順序（DOCS-1 → BE-1 → FE-1。相互依存はなく、順序自体に強い理由はない）
8. [§3 各所] 具体的なバージョン番号・行番号・コマンド（2026-07-04 調査時点の事実。npm レジストリの最新版や行番号が変わっていたら数値だけ読み替える）

---

## §1. 現状理解（CI が何を検査しているか）

`.github/workflows/ci.yml` は `push`（branches: `master`）と `pull_request`（対象 `master`）で 3 job を並列実行する。
**⚠ 重要: feature ブランチを push しただけでは CI は起動しない**（push トリガーは master 限定）。作業ブランチの CI を回すには **PR の作成が必須**（§5 手順 7）。

### frontend job（`.github/workflows/ci.yml:50-72`）
1. `actions/setup-node@v4`（Node 22、`frontend/package-lock.json` を鍵に npm キャッシュ）
2. `npm ci`（`frontend/` で実行）
3. `npm run lint`（= `eslint .`）
4. `npm run test:ci`（= `tsc -b && vitest run`）

### backend job（`.github/workflows/ci.yml:13-45`）
1. `astral-sh/setup-uv@v4`（Python 3.12）
2. `sudo apt-get install -y libgl1`（opencv-python 用）
3. `uv sync`（リポジトリルート、`pyproject.toml` の workspace = `backend` / `kindle-pdf` / `common/llm`）
4. `backend/` で `ruff check .` → `ruff format --check .` → `basedpyright` → `pytest -q --cov --cov-fail-under=65`

### docs job（`.github/workflows/ci.yml:77-101`）
1. `uv sync`（ルート）
2. `uv run python scripts/maintenance/check_docs.py`（docs 間リンク切れ・変更履歴肥大化・mkdocs nav 同期・design 文書サイズ/status ヘッダ・ファイルマップ注釈切れの 6 ルールを検査。Rule 4 のみ warn、他はブロッキング）
3. `uv run python scripts/maintenance/generate_file_map.py --check`（`docs/design/詳細設計/詳細設計書_{フロントエンド,バックエンド}_ファイルマップ.md` 内の `<!-- GENERATED:FILE_MAP:START/END -->` マーカー間を、実ディレクトリ構成から再生成した ASCII ツリーと比較。差分があれば exit 1。**書き込みはしない**）
4. `pip install mkdocs mkdocs-material mkdocs-mermaid2-plugin`
5. `mkdocs build --strict`（`mkdocs.yml` の `validation:` で `links.not_found` / `anchors` / `unrecognized_links` は `info` に格下げ済みなので、リンク切れ等は `--strict` を落とさない。落ちるのは真の `WARNING` レベルのみ）

### 失敗原因（2026-07-04 調査で特定済み）

**frontend — ERESOLVE は原因が 2 つ重なっている（1 つ目を直すと 2 つ目が表面化する）:**

- 原因 A: `frontend/package.json` の `"eslint": "^10.4.1"` と `"eslint-plugin-jsx-a11y": "^6.10.2"` の peerDependencies（`"eslint": "^3 || ^4 || ^5 || ^6 || ^7 || ^8 || ^9"`）が競合。2026-07-04 時点の npm レジストリで `eslint-plugin-jsx-a11y` の最新は 6.10.2 のままで、eslint 10 対応版はまだ存在しない（`npm view eslint-plugin-jsx-a11y versions` で確認済み）。
- 原因 B: 原因 A だけを直す（eslint を 9 系へ降格する）と、`npm install` は別の ERESOLVE で再度失敗する。`"typescript": "^6.0.3"` と `"openapi-typescript": "^7.13.0"` の peerDependency（`"typescript": "^5.x"`）が競合するため。この衝突は現在の package.json にも既に存在するが、npm が先に原因 A を報告するため隠れていた（`npm install --package-lock-only` を隔離コピーで実行し、原因 A のみ直した状態で再現・確認済み）。`openapi-typescript` は `"generate:types"` スクリプト専用（`npm run lint` / `npm run test:ci` では一切実行されない devDependency）なので、実行時の型互換性は CI の green/red に影響しない。
- この 2 つを両方直した状態で `npm install` → `npm run lint`（0 errors, 18 warnings）→ `npm run test:ci`（tsc -b + vitest 全 pass）まで、隔離コピー上で実地確認済み（Node v24.13.0 環境。CI は Node 22 のため最終確認は実際の CI 実行で行う）。

**backend:**

- 失敗テスト: `backend/tests/test_novel_db_search_summary.py::test_search_book_summaries_handles_empty_table`
- 直接の例外: `services.novel_db.embedder.EmbeddingError: Ollama embed API request failed: [Errno 111] Connection refused`（CI ランナーに Ollama が無いため）
- 根本原因: `backend/services/novel_db/search.py` の `search_book_summaries()` が **`table.count_rows() == 0` の空判定より先に `embed_batch()` を無条件に呼んでいる**。同じファイル内の姉妹関数 `find_similar_books()` は「先に空判定 → 空なら embed を呼ばず return」という順序になっており、`search_book_summaries()` だけがこの順序になっていない。空テーブルに対して embedding API を呼ぶこと自体が本来無駄（ローカルで実 Ollama を使っている開発者には気づかれなかった）。
- ローカルで実 Ollama（`http://localhost:11434`）が動いていると 5 passed になり再現しない。`NOVEL_DB_OLLAMA_BASE_URL` を到達不能なアドレスに差し替えると CI と同じ 1 failed を再現できることを確認済み。隔離コピーで §3-2 の修正を適用し、同条件でバックエンド全 pytest スイートを実行 → **0 failed**（調査時点では 848 passed。ruff check / ruff format --check も pass）。

**docs:**

- 失敗している実際のステップは `generate_file_map.py --check`（`check_docs.py` は 0 blocking violations で pass、`mkdocs build --strict` も現状の内容で exit 0 まで確認済み。つまり docs job のブロッカーはこの 1 ステップだけ）。
- CI ログ（run `28702238003`）: `[DIFF] docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md: 差分あり（--check のため書き込みません）`
- 根本原因: `backend/.coverage`（`pytest --cov` 実行時に生成される、`.gitignore` で無視されているカバレッジ計測ファイル）が `scripts/maintenance/generate_file_map.py` の `EXCLUDED_FILE_NAMES`（89 行、現状 `frozenset({".DS_Store"})` のみ）に含まれていない。過去に開発者がローカルで `pytest --cov` を実行して `backend/.coverage` が存在する状態のまま `generate_file_map.py`（書き込みモード）を実行し、ASCII ツリーに `├── .coverage` の行が紛れ込んだまま `docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md` へコミットされた。CI はクリーンチェックアウトのため `backend/.coverage` が存在せず、生成ツリーにこの行が無い → コミット済みドキュメントと差分が生じ `--check` が exit 1 になる。
- 検証: `EXCLUDED_FILE_NAMES` に `.coverage` を加えた状態でツリーを再生成すると、現在のコミット済みドキュメントとの差分は **`├── .coverage` の 1 行が消えるだけ**（他の差分は一切無し）であることを確認済み。

---

## §2. 安全網の構築（項目 0 — 最初に必ず実行する）

**目的**: 作業中に何かを壊しても即座に元へ戻せる状態を作り、前提ツールの欠落で途中停止しないことを先に保証する。この項目を飛ばして §3 の作業に入らないこと。

1. **前提ツールの確認**。以下がすべて exit 0 で応答することを確認する。1 つでも欠けていたら作業を開始せず人間に報告する。
   ```
   git --version
   uv --version
   node --version
   npm --version
   gh --version
   gh auth status
   ```
   - `node --version` について: CI は Node 22 を使う。ローカルのメジャーバージョンが異なっていても作業は可能だが、その場合ローカル green は参考値であり、**最終判定は必ず実機 CI（§5 手順 7-8）で行う**。
2. カレントディレクトリが `D:\61.tool\Pic2PDF_Viewer` であることを確認する。
3. 作業前の状態を確認する。
   ```
   git status
   git branch --show-current
   ```
   - `git status` に今回の作業と無関係の変更が表示された場合は、そのまま §3 へ進まず、まず人間に確認を取ること（計画書作成時点では `frontend/.env` にローカル変更が存在することを確認済み。**このファイルは今回のコミットに一切含めない**）。
   - 現在ブランチが `master` であることを確認する。
4. 作業用ブランチを作成する（`master` へ直接コミットしない）。
   ```
   git checkout -b fix/ci-green
   ```
5. ベースラインを記録する。
   ```
   git rev-parse HEAD
   ```
   この SHA と `fix/ci-green` というブランチ名を控える。切り戻したくなった場合は
   ```
   git checkout master
   git branch -D fix/ci-green
   ```
   で作業ブランチごと破棄すれば `master` は無傷のまま。
6. 現在の CI の赤状態を GitHub 上でも確認する（推奨）。
   ```
   gh run list --limit 5
   ```
   直近の run が `failure` になっていることを確認する（=本計画書の前提が今も成立していることの確認）。

**この項目の完了条件**: 前提ツール 6 コマンドすべて exit 0 / `fix/ci-green` ブランチ上におり、`frontend/.env` 以外に未コミット変更が無く、HEAD の SHA を控えている。

---

## §3. 作業項目リスト（実行順: DOCS-1 → BE-1 → FE-1）

### ITEM: DOCS-1 — docs job のファイルマップ再生成漏れを修正

- **対象**:
  - `scripts/maintenance/generate_file_map.py:86-89`（設計コメント + `EXCLUDED_FILE_NAMES`）
  - `docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md`（スクリプト実行で自動更新。手編集しない）
- **何が問題か**: §1 docs 節のとおり。なお現状の 86-88 行の設計コメントは「拡張子ベースのフィルタは行わない（`.coverage` 等も実ファイルとして存在すれば表示される）。`.DS_Store` のみ例外的に除外」と明記しており、**`.coverage` を除外リストへ足すことはこのコメントの方針記述と正面から矛盾する**。コードだけ変えてコメントを残すと、次にこのファイルを読む人が「コメントと実装のどちらが正か」で迷うため、コメントも同時に改訂する。
- **どう変えるか**:
  1. `scripts/maintenance/generate_file_map.py:86-89` を編集する。
     - Before:
       ```python
       # ファイル名の完全一致で除外するもの。方針: ディレクトリレベルのノイズのみを
       # 除外し、拡張子ベースのフィルタは行わない（.tsbuildinfo / .pyc / .coverage 等も
       # 実ファイルとして存在すれば表示される）。macOS の .DS_Store のみ例外的に除外。
       EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})
       ```
     - After:
       ```python
       # ファイル名の完全一致で除外するもの。方針: ディレクトリレベルのノイズのみを
       # 除外し、拡張子ベースのフィルタは行わない（.tsbuildinfo / .pyc 等は
       # 実ファイルとして存在すれば表示される）。例外はここに完全一致で個別列挙する:
       # - .DS_Store: macOS のノイズ
       # - .coverage: gitignore 対象の実行時生成物。ローカルの汚れた状態で生成した
       #   ツリーが CI のクリーンチェックアウトと恒常的にドリフトした実績があるため
       #   （2026-07 CI修理計画書 DOCS-1）
       EXCLUDED_FILE_NAMES = frozenset({".DS_Store", ".coverage"})
       ```
  2. リポジトリルートで下記を実行し、ドキュメントを再生成する（**書き込みモード。`--check` を付けない**）。
     ```
     uv run python scripts/maintenance/generate_file_map.py
     ```
     - **注意**: このスクリプトは「書き込みモードで実際に変更を書き込んだ場合、exit code 1 を返す」仕様（`generate_file_map.py:331-334`）。これは失敗ではない。exit code ではなく標準出力のメッセージで判定すること。
     - 期待する出力に `[UPDATED] docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md: マーカーブロックを更新しました` という行が含まれていること。
- **完了条件**（すべて満たすこと。この順で実行する）:
  1. **主証拠（これが最も弁別力が高い）**:
     ```
     git diff -- "docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md"
     ```
     の差分が **`├── .coverage` の行 1 行の削除のみ**であること。それ以外の行が変化していたら、想定外のドリフトが他にもあることを意味するので、**その場で判断せず作業を中断し人間に報告すること**（§5 手順 5 の中断ルール）。
  2. `--check` をクリーン状態で通す。**⚠ 弁別力の罠**: ローカルに `backend/.coverage` が実在すると、修正**前**でも生成ツリーに `.coverage` 行が入って既存ドキュメントと一致し `--check` は exit 0 になる（=修正の成否を判定できない）。そのため先に生成物の有無を確認し、あれば削除してから実行する（`backend/.coverage` は pytest --cov が再生成する使い捨てファイルなので削除してよい）:
     ```powershell
     if (Test-Path backend/.coverage) { Remove-Item backend/.coverage }
     uv run python scripts/maintenance/generate_file_map.py --check
     ```
     が **exit code 0** で `変更なし` と表示されること。
  3. ```
     uv run python scripts/maintenance/check_docs.py
     ```
     が exit code 0 で終わる（既存の Rule 4 warn＝`詳細設計書_フロントエンド編.md` の行数超過は元々あるもので今回と無関係。「ブロッキング違反なし」なら良い。warn 以外が増えていたら中断）。
  4. （任意）`uv run mkdocs build --strict` が exit code 0（mkdocs 等未導入の環境ではスキップ可。CI で最終確認されるため）。
- **リスクと失敗した場合の戻し方**: 影響範囲はドキュメント 1 ファイル + スクリプトのコメント/1 行のみで、実行コードのロジックには触れない。完了条件を満たせない場合は
  ```
  git checkout -- scripts/maintenance/generate_file_map.py "docs/design/詳細設計/詳細設計書_バックエンド_ファイルマップ.md"
  ```
  で当該 2 ファイルだけ元に戻せる。
- **依存**: ITEM-0（§2）完了後であること。他項目への依存なし。
- **コミット**: この項目の変更（上記 2 ファイル）のみで 1 コミットする。

---

### ITEM: BE-1 — backend の空テーブル時の不要な embedding 呼び出しを修正

- **対象**: `backend/services/novel_db/search.py`（関数 `search_book_summaries`、調査時点で 250-261 行付近）
- **何が問題か**: 空の LanceDB summaries テーブルに対しても `embed_batch()`（Ollama への実 HTTP 呼び出し）を先に実行してしまうため、Ollama が到達不能な環境（CI ランナー）でテスト `test_search_book_summaries_handles_empty_table` が `EmbeddingError` で落ちる。姉妹関数 `find_similar_books` は「先に空判定 → 空なら return」の順序になっており、`search_book_summaries` だけがこの順序になっていないのが根本原因。
- **どう変えるか**: `table.count_rows() == 0` の判定ブロックを `emb = embed_batch([query])[0]` より前へ移動する（3 行のブロックを丸ごと上に移すだけ。ロジックの追加・削除は無い）。
  - Before:
    ```python
        book_names = _resolve_book_names(scope)
        if book_names is not None and not book_names:
            return []

        emb = embed_batch([query])[0]

        table = get_summaries_table()
        if table.count_rows() == 0:
            return []

        k = max(top * 2, 22) if book_names is not None else top
        query_builder = table.search(emb).limit(k).select(["book_name"])
    ```
  - After:
    ```python
        book_names = _resolve_book_names(scope)
        if book_names is not None and not book_names:
            return []

        table = get_summaries_table()
        if table.count_rows() == 0:
            return []

        emb = embed_batch([query])[0]

        k = max(top * 2, 22) if book_names is not None else top
        query_builder = table.search(emb).limit(k).select(["book_name"])
    ```
  - 判断が入る余地は無い（単純な行の並べ替え。呼び出し先のシグネチャ・返り値は一切変えない）。
  - **他の関数（`vec_search` / `find_similar_books` など）には手を出さない。** `vec_search` も同様に embed を先に呼ぶ構造だが、今回の CI 失敗の再現範囲に含まれておらず、対象外（§4 参照）。
- **完了条件**:
  1. `backend/` で pytest を実行し、**failed が 0 件**であること（判定は「0 failed」で行う。passed の絶対数はテスト追加で変動するため判定基準にしない。参考: 調査時点では 848 passed / 元は 1 failed, 847 passed）。特に `test_search_book_summaries_handles_empty_table` が passed に転じていること。
     ```
     uv run pytest -q --cov --cov-fail-under=65
     ```
     - **手元に実 Ollama が動いている場合、この修正をしなくても該当テストは通ってしまう**（バグを再現できない）。その場合は到達不能な URL を一時指定して CI と同条件で確認すること:
       ```powershell
       $env:NOVEL_DB_OLLAMA_BASE_URL = "http://127.0.0.1:1"
       uv run pytest -q --cov --cov-fail-under=65
       Remove-Item Env:NOVEL_DB_OLLAMA_BASE_URL
       ```
       （bash なら `NOVEL_DB_OLLAMA_BASE_URL="http://127.0.0.1:1" uv run pytest -q --cov --cov-fail-under=65`。環境変数はこの実行にのみ影響させ、恒久設定として残さない）
  2. `backend/` で以下がともに exit code 0 であること。
     ```
     uv run ruff check .
     uv run ruff format --check .
     ```
  3. `uv run basedpyright`（`backend/` で実行）のエラー件数が作業前から増えていないこと（型注釈に影響しない並べ替えなので新規エラーは出ないはずだが、機械的に確認する）。
- **リスクと失敗した場合の戻し方**: 変更は 1 ファイル・1 関数内の並べ替えのみ。振る舞いは「空テーブル時に無駄な embedding API 呼び出しをしなくなる」点のみ変わり、非空テーブル時の挙動・返り値は完全に同一。戻す場合:
  ```
  git checkout -- backend/services/novel_db/search.py
  ```
- **依存**: ITEM-0 完了後であること。ITEM-DOCS-1 とは独立。
- **コミット**: `backend/services/novel_db/search.py` の変更のみで 1 コミットする。

---

### ITEM: FE-1 — frontend の npm ERESOLVE を解消

- **対象**:
  - `frontend/package.json`（`"@eslint/js"` / `"eslint"` の 2 行 + 新規 `"overrides"` キー）
  - `frontend/package-lock.json`（`npm install` で自動再生成。手編集しない）
- **何が問題か**: `npm ci` が ERESOLVE で 2 段階に失敗する（§1 frontend 節）。(a) `eslint@10.4.1` × `eslint-plugin-jsx-a11y@6.10.2` の peer 不一致。(b) (a) を直すと表面化する `typescript@6.0.3` × `openapi-typescript@7.13.0` の peer 不一致。
- **どう変えるか**（判断が入る箇所なので、選定理由も書く）:

  **(a) eslint を 9 系へ降格する。**
  - `eslint-plugin-jsx-a11y` は 2026-07-04 時点のレジストリ最新（6.10.2）でも peer は `eslint <= 9` までしか宣言していない。他の eslint 関連 devDependency（`typescript-eslint@8.59.2` / `eslint-plugin-react-hooks@7.1.1` / `eslint-config-prettier@10.1.8` / `eslint-plugin-react-refresh@0.5.2`）は eslint 9/10 両対応のため、eslint 本体だけ 9 系へ戻せば矛盾なく揃う。
  - `--legacy-peer-deps` のような一括抑制を選ばない理由: peer チェック全体が無効化され、他のパッケージ間で将来本物の非互換が起きても検知できなくなる。
  - Before（`frontend/package.json`）:
    ```json
        "@eslint/js": "^10.0.1",
    ```
    ```json
        "eslint": "^10.4.1",
    ```
  - After:
    ```json
        "@eslint/js": "^9.39.4",
    ```
    ```json
        "eslint": "^9.39.4",
    ```
  - `9.39.4` は 2026-07-04 時点の 9 系最新。作業時点でより新しい 9.x があればそれを使ってよいが、**10.x 系は指定しないこと**。9.x 以外を選ぶ場合は `npm view eslint-plugin-jsx-a11y@6.10.2 peerDependencies` でレンジに収まることを確認してから決める。
  - 隔離環境で `eslint@9.39.4` + `@eslint/js@9.39.4` へ揃えた状態で `npm install` → `npm run lint`（0 errors, 18 warnings。既存の `jsx-a11y/*` warn と `react-refresh/only-export-components` warn で、既存の eslint.config.js の意図通り）→ `npm run test:ci`（全 pass）まで確認済み。

  **(b) `openapi-typescript` の `typescript` peer 要求を `overrides` で吸収する。**
  - `openapi-typescript` は `"generate:types"` スクリプト専用の devDependency で、CI が実行する `npm run lint` / `npm run test:ci` のどちらからも呼ばれない。純粋に npm のインストール時 peer チェックだけの問題。
  - `typescript` 本体を 5 系へ格下げする代替案を採らない理由: (1) `typescript-eslint@8.59.2` の peer は `">=4.8.4 <6.1.0"` で 6.0.3 を許容しており、下げる技術的必然性が無い。(2) typescript のダウングレードは `tsc -b` の型チェック結果に影響しうるため影響範囲が大きい。`overrides` は npm 標準機能で影響範囲が最小。
  - Before（`frontend/package.json` 末尾付近）:
    ```json
        "vite": "^8.0.16",
        "vitest": "^4.1.5"
      }
    }
    ```
  - After:
    ```json
        "vite": "^8.0.16",
        "vitest": "^4.1.5"
      },
      "overrides": {
        "openapi-typescript": {
          "typescript": "$typescript"
        }
      }
    }
    ```
  - `"$typescript"` は npm 公式の記法で「トップレベルの `typescript` 依存が解決したバージョンをそのまま使う」の意（バージョン文字列を二重管理しない）。この記法で ERESOLVE が解消することを隔離環境の `npm install --package-lock-only` で検証済み。

  (a)(b) を両方適用したら、`frontend/` でロックファイルを再生成する:
  ```
  npm install
  ```
  `package-lock.json` の書き換わった内容は手で編集しない（npm に任せる）。
- **完了条件**（`frontend/` で以下を順に実行）:
  1. `npm ci` が ERESOLVE エラー無しで成功すること（`npm install` 直後に打つことで「package.json と lock が一致した状態から、CI と同じ `npm ci` で入るか」を検証する）。
  2. `npm run lint` が exit code 0（warning は既存挙動なので問題ない。`error` が 1 件でも出たら失敗）。
  3. `npm run test:ci` が exit code 0（`tsc -b` の型エラーも `vitest run` の失敗も 0 件）。
- **リスクと失敗した場合の戻し方**: `frontend/package.json` と `frontend/package-lock.json` のみが対象。`eslint.config.js` やソースには触れない。戻す場合:
  ```
  git checkout -- frontend/package.json frontend/package-lock.json
  ```
  （戻した後に `npm ci` を再実行して `node_modules` を lock と一致させておく。**lock の部分更新は npm ci 即落ちの既知の罠**なので、package.json を変えたら必ず `npm install` でフル再生成する）
- **依存**: ITEM-0 完了後であること。ITEM-DOCS-1 / ITEM-BE-1 とは独立。
- **コミット**: `frontend/package.json` + `frontend/package-lock.json` の変更のみで 1 コミットする（(a)(b) を分けない。(a) 単体は `npm ci` がまだ失敗する中間状態のため）。

---

## §4. やらないことリスト（先回りで禁止する）

以下は今回のタスク（CI を green に戻すこと）に必要ないので、**善意であっても行わないこと**。気づいたことがあれば着手せず報告のみ行う。

- **frontend**:
  - `.github/workflows/ci.yml` を編集すること（`--legacy-peer-deps` や `--force` フラグの追加を含む）。今回の 3 項目だけで green になることを確認済み。
  - eslint と typescript/openapi-typescript 以外の devDependencies・dependencies のバージョンを上げる/下げること。
  - `eslint.config.js` のルール内容を変更すること。既存 18 件の warning は意図通りの挙動であり、消す必要はない。
  - `npm audit fix` やその他の「ついでの」依存更新。
  - `frontend/.env` のローカル変更に触れる・コミットに含めること（§2 手順 3）。
- **backend**:
  - `search_book_summaries` 以外の関数（`vec_search` / `find_similar_books` / `hybrid_search` 等）の実装を変更すること。
  - `tests/test_novel_db_search_summary.py` にテストを追加・変更すること（修正だけで既存テストが全て通ることを確認済み）。
  - `--cov-fail-under=65` のしきい値や pytest 設定を変更すること。
  - CI に Ollama サービスコンテナを追加する、`embed_batch` を全面モック化する conftest フィクスチャを新設するなど、今回のバグの外側まで踏み込んだ「本格的な対策」。
- **docs**:
  - `詳細設計書_バックエンド_ファイルマップ.md` の GENERATED マーカーの外側（手書きセクション）を編集すること。
  - `詳細設計書_フロントエンド編.md` の行数超過（Rule 4 warn）を「ついでに」分割・整理すること。
  - `EXCLUDED_FILE_NAMES` に `.coverage` 以外の名前（`.coverage.*` / `coverage.xml` 等）を先回りで追加すること。実際にドリフトの原因と確認できたのは `.coverage` のみ。将来別の生成物が紛れ込んだら、その時に同じ手順で対処する。
  - `mkdocs.yml` の `validation:` 設定を変更すること。
- **全体**:
  - 3 項目以外の「ついでに見つけた」改善（コードスタイル、コメント追加、typo 修正等）。
  - `master` へ直接コミットすること、`git push --force`、PR の自分でのマージ。

---

## §5. 実行者への指示文（そのままコピペして渡す）

```
このリポジトリ（D:\61.tool\Pic2PDF_Viewer）の CI（frontend / backend / docs の 3 job）を
green に戻す作業をお願いします。手順は下記の計画書に全て書いてあります。

計画書: docs/log/計画/CI修理計画書.md

進め方:
1. まず §2「安全網の構築」を実行してください（前提ツール確認 → 作業用ブランチ作成）。
2. §3 の作業項目を DOCS-1 → BE-1 → FE-1 の順に、1 項目ずつ実施してください。
3. 各項目は「どう変えるか」に書いてある通りに変更し、「完了条件」に書いてあるコマンドを
   実行して、書いてある通りの結果になることを確認してください。
4. 完了条件を満たしたら、その項目の対象ファイルだけをステージして 1 コミットを作成し、
   次の項目に進んでください（1 項目 = 1 コミット）。
5. いずれかの項目で完了条件を満たせなかった場合は、自己判断で別の直し方を試さず、
   そこで作業を中断し、どの完了条件がどう満たせなかったか（実行したコマンドと実際の出力）
   を報告してください。
6. §4「やらないことリスト」に書かれていることは、良かれと思っても行わないでください。
7. 3 項目すべてのコミットが終わったら、ブランチを push し、PR を作成してください:
     git push -u origin fix/ci-green
     gh pr create --base master --title "fix(ci): frontend/backend/docs の 3 job を green に修理" \
       --body "計画書 docs/log/計画/CI修理計画書.md に基づく修理。詳細は計画書参照。"
   ※ この CI は push:master / pull_request:master でのみ起動します。ブランチを push した
     だけでは CI は走らないため、PR の作成が必須です。
8. PR 上で CI の 3 job がすべて green（success）になることを gh pr checks で確認してから
   完了報告してください。ローカル確認は Node 22 / Ubuntu の実 CI 環境と完全一致しないため、
   最終判定は実機 CI の結果で行います。PR のマージは行わないでください（人間のレビュー後）。
```
